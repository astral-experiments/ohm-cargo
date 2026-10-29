"""Exercise a real ordinary binary with an assembly input and a used Rust dependency."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ORIGINAL = b'#[inline(never)]\npub fn observed(x: u8) -> u8 { x ^ 5 }\n'
EDIT = ORIGINAL.replace(b'x ^ 5', b'x ^ 9')
BINARY = r'''use core::arch::global_asm;
global_asm!(concat!(
    ".pushsection .rodata.ohm_assembly_input,\"a\",@progbits\n",
    ".globl ohm_assembly_input\n",
    ".type ohm_assembly_input,@object\n",
    "ohm_assembly_input:\n",
    ".incbin \"", env!("CARGO_MANIFEST_DIR"), "/payload.bin\"\n",
    ".size ohm_assembly_input,.-ohm_assembly_input\n",
    ".popsection\n"
));
unsafe extern "C" { static ohm_assembly_input: u8; }
fn main() {
    let byte = unsafe { core::ptr::read_volatile(&raw const ohm_assembly_input) };
    println!("native={byte},rust={}", producer::observed(std::hint::black_box(3)));
}
'''
def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def sha(data):
    return hashlib.sha256(data).hexdigest()
def trace(out, asset):
    jobs, opens, parents, execs, hashed = [], [], {}, {}, set()
    for path in sorted(out.glob('trace.*')):
        pid = int(path.name.split('.')[-1])
        for line in path.read_text(errors='replace').splitlines():
            if 'execve(' in line and line.endswith('= 0'):
                m = re.search(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)', line)
                if not m:
                    raise ValueError(line)
                exe, argv = Path(ast.literal_eval(m[1])), ast.literal_eval(m[2])
                unit = argv[argv.index('--crate-name')+1] if '--crate-name' in argv else ''
                execs[pid] = (exe.name, unit)
                if exe.name == 'rustc' and unit in ('reader', 'producer'):
                    link = '-Zlink-only' in argv or 'link-only' in argv
                    jobs.append(dict(kind='rustc', unit=unit, link_only=link,
                                     public_hash='-Zpublic-api-hash' in argv,
                                     no_link='no-link' in argv or '-Zno-link' in argv,
                                     incremental=any(x.startswith('incremental=') for x in argv),
                                     argv=sha(json.dumps(argv,separators=(',',':')).encode()), exe=digest(exe)))
                    if unit == 'reader':
                        directory = Path(argv[argv.index('--out-dir')+1])
                        ext = next(x.split('=',1)[1] for x in argv if x.startswith('extra-filename='))
                        hashed.add(directory / ('reader'+ext))
                elif exe.name in ('cc','gcc','collect2','ld','ld.bfd','ld.lld','rust-lld','wild') and '-o' in argv:
                    final = Path(argv[argv.index('-o')+1]).name
                    if final == 'reader' or final.startswith('reader-'):
                        jobs.append(dict(kind='driver' if exe.name in ('cc','gcc','collect2') else 'linker',
                                         file=exe.name,exe=digest(exe), argv=sha(line.encode())))
                continue
            if re.search(r'\b(?:clone3?|vfork|fork)\(|<\.\.\. (?:clone3?|vfork|fork) resumed>',line):
                child = re.search(r'=\s*(\d+)\s*$', line)
                if child:
                    parents[int(child[1])] = pid
            if 'open' in line and f'"{asset}"' in line and re.search(r'\bopen(?:at2?)?\(',line):
                opens.append(dict(tid=pid, acquired=bool(re.search(r'=\s*\d+\s*$',line)),
                                  missing='ENOENT' in line,row=sha(line.encode())))
    for item in opens:
        p = item.pop('tid'); seen = set()
        while p not in seen and p:
            seen.add(p)
            if p in execs and execs[p][0] == 'rustc':
                item['rustc_unit'] = execs[p][1]
                break
            p = parents.get(p)
    return jobs, opens, hashed

def case(root, sdk, setting):
    assert os.geteuid() == 1000 and Path('/').stat().st_uid == 0
    assert os.sched_getaffinity(0) == {24,25,26,27}
    root.mkdir(mode=0o700)
    work = root/'workspace'; src = work/'src'; libsrc = work/'producer/src'
    for d in (src,libsrc,root/'home',root/'rustup/toolchains'):
        d.mkdir(parents=True)
    (root/'rustup/toolchains/ohm').symlink_to(sdk,target_is_directory=True)
    (work/'Cargo.toml').write_text('[package]\nname="reader"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nproducer={path="producer"}\n')
    (work/'producer/Cargo.toml').write_text('[package]\nname="producer"\nversion="0.1.0"\nedition="2024"\n')
    binary=src/'main.rs'; binary.write_text(BINARY)
    lib=libsrc/'lib.rs'; lib.write_bytes(ORIGINAL)
    asset=work/'payload.bin'; asset.write_bytes(bytes([17]))
    env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO_')) and k not in ('LD_LIBRARY_PATH','LIBRARY_PATH','LD_PRELOAD','GCC_EXEC_PREFIX','COMPILER_PATH')}
    env.update(RUSTUP_HOME=str(root/'rustup'),CARGO_HOME=str(root/'home'),CARGO_NET_OFFLINE='true',CARGO_INCREMENTAL='0',CARGO_TERM_COLOR='never')
    shim=str(Path.home()/'.cargo/bin/cargo')
    args=[shim,'+ohm','--config','build.rustflags=["-Zpublic-api-hash"]']
    if setting == 'relink':
        args.append('-Zrelink-only')
    args += ['build','--offline','-j2','--bin','reader','--message-format=json']
    versions={}
    for tool in ('cargo','rustc'):
        text=subprocess.check_output([str(Path.home()/'.cargo/bin'/tool),'+ohm','-Vv'],env=env,cwd=work)
        (root/(tool+'-version')).write_bytes(text); versions[tool]=sha(text)
    (root/'help').write_bytes(subprocess.check_output([shim,'+ohm','-Zhelp'],env=env,cwd=work))
    if setting=='parent':
        p=subprocess.run([shim,'+ohm','-Zrelink-only','build','--offline'],env=env|{'CARGO_TARGET_DIR':str(root/'unused-flag-state/target'),'CARGO_BUILD_BUILD_DIR':str(root/'unused-flag-state/shared')},cwd=work,capture_output=True)
        (root/'unsupported-stderr').write_bytes(p.stderr)
        assert p.returncode==101 and b'unknown' in p.stderr.lower() and b'relink-only' in p.stderr, (p.returncode,p.stderr)
    if setting=='relink':
        assert b'relink-only' in (root/'help').read_bytes()
    collected={}; known=set()
    def run(name, state='trained'):
        assert shutil.disk_usage(root).free>65*2**30
        st=root/state; empty=not st.exists()
        out=root/name; out.mkdir()
        env1=env|{'CARGO_TARGET_DIR':str(st/'target'),'CARGO_BUILD_BUILD_DIR':str(st/'shared')}
        cmd=['strace','-ff','-qq','-s','131072','-e','trace=execve,open,openat,openat2,clone,clone3,vfork,fork','-o',str(out/'trace'),*args]
        with (out/'stdout').open('xb') as o,(out/'stderr').open('xb') as e:
            p=subprocess.run(cmd,env=env1,cwd=work,stdout=o,stderr=e)
        messages=[json.loads(row) for row in (out/'stdout').read_bytes().splitlines() if row.startswith(b'{')]
        arts=[v for v in messages if v['reason']=='compiler-artifact']
        jobs,opens,hashset=trace(out, asset)
        rjobs=[v for v in jobs if v['kind']=='rustc']
        assert all(v['public_hash'] and not v['incremental'] for v in rjobs)
        assert not any(v['reason']=='build-script-executed' for v in messages)
        for h in hashset:
            assert h.resolve().is_relative_to(st)
        if state=='trained': known.update(hashset)
        result={'status':p.returncode,'empty':empty,'phase':name,'source':digest(lib),'binary_source':digest(binary),
                'asset':digest(asset) if asset.exists() else None,'jobs':jobs,'asset_opens':opens,
                'typed':[(v['target']['name'],v['fresh']) for v in arts],
                'missing_diagnostic':any(b'payload.bin' in line and (b'Could not find incbin file' in line or b'could not find' in line.lower() or b'no such file' in line.lower()) for line in (out/'stdout').read_bytes().splitlines()+(out/'stderr').read_bytes().splitlines())}
        dep={}
        for h in hashset:
            d=h.with_name(h.name+'.d')
            if d.is_file():
                raw=d.read_bytes();dep[d.name]={'sha256':sha(raw),'source':b'src/main.rs' in raw,'payload':b'payload.bin' in raw}
        result['depinfo']=dep
        result['public_api_files']={str(f.relative_to(st)):json.loads(f.read_bytes()) for f in st.rglob('*.public-api-hash') if f.is_file()}
        result['archives']={str(f.relative_to(st)):digest(f) for f in st.rglob('libproducer-*.rlib') if f.is_file()}
        result['assembly_object']=[]
        for f in st.rglob('reader-*.rlink-cache.json'):
            if not f.is_file():
                continue
            doc=json.loads(f.read_bytes())
            with tempfile.TemporaryDirectory(dir=out) as t:
                for i,m in enumerate(doc['objects']):
                    obj=Path(m['path']); assert obj.resolve().is_relative_to(st)
                    if not obj.is_file():continue
                    sec=Path(t)/str(i)
                    subprocess.run(['objcopy','-O','binary','--only-section=.rodata.ohm_assembly_input',obj,sec],check=True,capture_output=True)
                    if sec.is_file() and sec.stat().st_size:
                        result['assembly_object'].append({'name':obj.name,'bytes':sec.read_bytes().hex(),'sha256':digest(obj),'manifest_sha256':digest(f)})
        if p.returncode==0:
            x,=[Path(v['executable']) for v in arts if v.get('executable') and v['target']['name']=='reader']
            assert x.is_file() and not x.is_symlink() and x.resolve().is_relative_to(st)
            ck=subprocess.run([x],capture_output=True,cwd=work,env=env1,check=True)
            mt=re.fullmatch(rb'native=(\d+),rust=(\d+)\n',ck.stdout); assert mt,ck.stdout
            result['native'],result['rust']=map(int,mt.groups())
            result['elf']=digest(x); (out/'program.stdout').write_bytes(ck.stdout)
            if state=='trained': known.add(x)
        result['raw']={f.name:digest(f) for f in sorted(out.iterdir()) if f.is_file()}
        save(out/'result.json',result);collected[name]=digest(out/'result.json')
        print(root.name,name,p.returncode,result.get('native'),result.get('rust'),[(v.get('unit'),v.get('link_only')) for v in rjobs],[(o.get('rustc_unit'),o['acquired'],o['missing']) for o in opens],flush=True)
        return result
    def hold(name):
        dest=root/'retained'/name; dest.mkdir(parents=True); evidence={}
        for f in sorted(known):
            for suff in ('','.rlink','.rlink-cache.json'):
                p=f.with_name(f.name+suff)
                if p.is_file():
                    assert p.resolve().is_relative_to(root/'trained') and not p.is_symlink()
                    rel=p.relative_to(root/'trained');target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True); evidence[str(rel)]=digest(p);p.rename(target)
        save(dest/'receipt.json',evidence)
    def pair(x,n,r): return x.get('native')==n and x.get('rust')==r and x['status']==0
    def opened(x):return any(o.get('rustc_unit')=='reader' and o['acquired'] for o in x['asset_opens'])
    original=run('01-cold');assert pair(original,17,6) and opened(original),original
    noop=run('02-unchanged');assert pair(noop,17,6) and not noop['jobs']
    lib.write_bytes(EDIT);asset.write_bytes(bytes([29]))
    change=run('03-private-edit-and-payload');assert change['status']==0 and change['rust']==10
    clean=run('04-independent-edited','empty-edited');assert clean['empty'] and pair(clean,29,10) and opened(clean)
    hold('edited'); forced=run('05-forced-current-codegen');assert pair(forced,29,10) and opened(forced)
    lib.write_bytes(ORIGINAL);asset.unlink()
    missing=run('06-source-restored-missing-payload');assert missing['status'] in (0,101)
    missing_clean=run('07-independent-missing','empty-missing');assert missing_clean['empty'] and missing_clean['status']==101 and missing_clean['missing_diagnostic'] and any(o.get('rustc_unit')=='reader' and o['missing'] for o in missing_clean['asset_opens'])
    hold('missing'); miss_forced=run('08-forced-current-missing');assert miss_forced['status']==101 and miss_forced['missing_diagnostic']
    asset.write_bytes(bytes([17]))
    restored=run('09-recovery-with-restored-payload');assert pair(restored,17,6) and opened(restored)
    ref=run('10-independent-restored','empty-restored');assert ref['empty'] and pair(ref,17,6) and opened(ref)
    save(root/'terminal.json',{'setting':setting,'cargo':digest(sdk/'bin/cargo'),'rustc':digest(sdk/'bin/rustc'),'versions':versions,'phases':collected,
                               'cargo_relink_supported':b'relink-only' in (root/'help').read_bytes()})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('sdk',type=Path);p.add_argument('setting',choices=['parent','relink','head-off'])
    a=p.parse_args();case(a.root.resolve(),a.sdk.resolve(strict=True),a.setting)
