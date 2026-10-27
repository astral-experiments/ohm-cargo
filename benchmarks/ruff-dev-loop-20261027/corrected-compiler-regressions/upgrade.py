"""Run a source-available Cargo workspace across a driver-only metadata upgrade."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def store(path, data):
    path.write_bytes(gzip.compress(data, mtime=0))


def metadata_writer(raw):
    assert raw.startswith(b'rust')
    i = 16
    width = 0
    for shift in range(0, 56, 7):
        byte = raw[i]; i += 1
        width |= (byte & 127) << shift
        if byte < 128:
            break
    assert raw[i+width] == 193
    return raw[i:i+width].decode()


def roster(trace, frontend, units):
    # strace may print a concurrent execve's arguments before its return value.
    pending = {}
    result = {}
    for row in trace.splitlines():
        match = re.match(r'^(\d+) +execve\("([^"]+)", \[(.*?)\], ', row)
        if match and Path(match[2]).name == 'rustc' and Path(match[2]).resolve() == frontend.resolve():
            crate = re.search(r'"--crate-name", "([^"]+)"', match[3])
            if not crate or crate[1] not in units:
                continue
            pid, name = match[1], crate[1]
            assert name not in result
            modes = re.findall(r'"([^" ]*public-api-hash[^" ]*)"', match[3])
            assert modes and modes[-1] == '-Zpublic-api-hash=no', (name, modes)
            entry = {'pid': int(pid), 'link_only': 'link-only' in match[3], 'public_hash_flags': modes}
            if row.endswith('= 0'):
                result[name] = entry
            else:
                assert '<unfinished ...>' in row, row
                pending[pid] = name, entry
        else:
            done = re.match(r'^(\d+) +<\.\.\. execve resumed>.*= ([-0-9]+)', row)
            if done and done[1] in pending:
                name, entry = pending.pop(done[1]); assert done[2] == '0' and name not in result
                result[name] = entry
    assert not pending
    return result


def main():
    p = argparse.ArgumentParser()
    for name in ['sysroot', 'rustup', 'cargo', 'old-driver', 'driver', 'out']:
        p.add_argument('--' + name, required=True, type=lambda v:Path(v).absolute())
    p.add_argument('--cpu', default='0-3')
    a = p.parse_args(); a.out.mkdir(); ws = a.out / 'workspace'; ws.mkdir()
    assert (a.rustup / 'toolchains/ohm').resolve() == a.sysroot.resolve()
    frontend = a.sysroot / 'bin/rustc'; mounted, = (a.sysroot/'lib').glob('librustc_driver*.so')
    units = {'review_producer', 'review_bridge', 'review_consumer'}
    (ws/'Cargo.toml').write_text('cargo-features=["profile-rustflags"]\n[workspace]\nmembers=["review_producer","review_bridge","review_consumer"]\nresolver="3"\n[profile.dev]\ndebug=0\nrustflags=["-Zpublic-api-hash=no"]\n')
    sources = {'review_producer': 'macro_rules! make { () => { pub struct Public(pub u32); } } make!();\n',
               'review_bridge': 'pub use review_producer::Public; #[inline] pub fn get(x: Public)->u32 {x.0}\n',
               'review_consumer': 'fn main(){println!("{}",review_bridge::get(review_bridge::Public(17)));}\n'}
    ordered = ['review_producer','review_bridge','review_consumer']; lock = 'version = 4\n'
    for i, name in enumerate(ordered):
        sub = ws/name; (sub/'src').mkdir(parents=True)
        lib = 'main.rs' if i == 2 else 'lib.rs'; (sub/'src'/lib).write_text(sources[name])
        dep = ordered[i-1] if i else ''
        manifest = f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2024"\n'
        if dep: manifest += f'[dependencies]\n{dep}={{path="../{dep}"}}\n'
        (sub/'Cargo.toml').write_text(manifest)
        lock += f'\n[[package]]\nname="{name}"\nversion="0.1.0"\n'
        if dep: lock += f'dependencies=["{dep}"]\n'
    (ws/'Cargo.lock').write_text(lock)
    def identity():
        return {str(f.relative_to(ws)):digest(f.read_bytes()) for f in sorted(ws.rglob('*')) if f.is_file()}
    known = identity(); rows = {}; ids = {}
    rproxy = Path.home()/'.cargo/bin/rustc'; cproxy = Path.home()/'.cargo/bin/cargo'
    for phase, driver, store_name in [('old-prime',a.old_driver,'active'),('old-fresh',a.old_driver,'active'),
                                        ('upgrade',a.driver,'active'),('new-fresh',a.driver,'active'),('new-cold',a.driver,'cold')]:
        out = a.out/phase; out.mkdir(); target = a.out/(store_name+'-target'); build = a.out/(store_name+'-build')
        env=dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(build),CARGO_HOME=str(a.out/'cargo-home'),
                 RUSTUP_HOME=str(a.rustup),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_BUILD_JOBS='4',GIT_OPTIONAL_LOCKS='0')
        for k in ('RUSTC','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'): env.pop(k,None)
        ns=['taskset','-c',a.cpu,'bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(a.out),str(a.out),
            '--ro-bind',str(a.cargo),str(a.sysroot/'bin/cargo'),'--ro-bind',str(driver),str(mounted),'--chdir',str(ws),'--']
        def run(cmd):return subprocess.run([*ns,*cmd],env=env,capture_output=True)
        key='old' if driver==a.old_driver else 'new'
        if key not in ids:
            ver=run([str(rproxy),'+ohm','-vV']); assert ver.returncode==0,ver.stderr
            # Record what the process namespace resolves, including the driver at the fixed pathname.
            sdk = sorted(p for p in (a.sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/lib').iterdir() if p.is_file())
            assert any(p.name.startswith('libstd-') and p.suffix=='.rlib' for p in sdk)
            hashes=run(['sha256sum',str(a.sysroot/'bin/cargo'),str(frontend),str(mounted),*map(str,sdk)]); assert hashes.returncode==0
            ids[key]={'version':ver.stdout.decode(), 'paths_sha256':dict((name,h)for h,name in (line.split(None,1) for line in hashes.stdout.decode().splitlines()))}
            assert ids[key]['paths_sha256'][str(mounted)]==digest(driver.read_bytes())
        argv=['strace','-f','-qq','-e','trace=execve','-s','16384','-o',str(out/'exec.log'),str(cproxy),'+ohm','build','--locked','--offline','--message-format=json','-p','review_consumer']
        cp=run(argv);store(out/'cargo.stdout.gz',cp.stdout);store(out/'cargo.stderr.gz',cp.stderr)
        tr=(out/'exec.log').read_bytes();store(out/'exec.log.gz',tr);(out/'exec.log').unlink()
        assert cp.returncode==0,(phase,cp.stderr.decode(errors='replace'),cp.stdout[-1500:])
        reports=[json.loads(line)for line in cp.stdout.splitlines() if line.startswith(b'{')]
        artifacts={m['target']['name']:m for m in reports if m.get('reason')=='compiler-artifact'}; assert set(artifacts)==units
        assert b'E0514' not in cp.stderr+cp.stdout
        compiler=roster(tr.decode(),frontend,units)
        exe=Path(artifacts['review_consumer']['executable']); program=run([str(exe)]); assert program.returncode==0 and program.stdout==b'17\n'
        rmeta={}
        for n in ['review_producer','review_bridge']:
            x,=[Path(f) for f in artifacts[n]['filenames'] if f.endswith('.rmeta')]
            raw=x.read_bytes();rmeta[n]={'path':str(x),'writer':metadata_writer(raw),'sha256':digest(raw)}
        contexts={next(part for part in x['path'].split('/')if part.startswith('v2-')) for x in rmeta.values()}; assert len(contexts)==1
        row={'compiler':compiler,'fresh':{n:artifacts[n]['fresh']for n in sorted(units)},'source':identity(),'elf':digest(exe.read_bytes()),'runtime':program.stdout.decode(),
             'metadata':rmeta,'context':contexts.pop(),'workspace_contexts':sorted(x.name for x in (target/'debug/build/workspaces').glob('*/v2-*')),
             'shared_context_locks':sorted(x.name for x in (build/'.ohm-gc-v1').glob('context-v2-*.lock')),'target':str(target),'build':str(build)}
        rows[phase]=row; (a.out/'observations.json').write_text(json.dumps({'toolchains':ids,'rows':rows},indent=2)+'\n')
        expected=set() if phase.endswith('fresh') else units
        assert row['source']==known and {n for n,f in row['fresh'].items()if not f}==set(compiler)==expected,(phase,row)
        assert all(not v['link_only'] for v in compiler.values()), (phase,compiler)
        print(phase,sorted(compiler),row['context'],row['runtime'].strip(),flush=True)
    assert ids['old']['version']==ids['new']['version']
    assert {path for path,h in ids['old']['paths_sha256'].items() if ids['new']['paths_sha256'][path]!=h}=={str(mounted)}
    old,up,after,cold=[rows[p] for p in ['old-prime','upgrade','new-fresh','new-cold']]
    assert old['context']!=up['context']==after['context'] and set(up['workspace_contexts'])=={old['context'],up['context']}
    assert up['shared_context_locks']==['context-'+c+'.lock' for c in sorted(up['workspace_contexts'])]
    for name in ('review_producer','review_bridge'):
        assert '(Ohm metadata ' not in old['metadata'][name]['writer'] and '(Ohm metadata ' in up['metadata'][name]['writer']
    assert up['elf']==after['elf']==cold['elf'] and old['runtime']==up['runtime']==after['runtime']==cold['runtime']


if __name__=='__main__':main()
