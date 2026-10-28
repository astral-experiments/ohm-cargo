"""Trace a real equal-width Ruff edit using an installed Linux x86-64 Ohm package."""
import argparse
import ast
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import traceback

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'plan.json').read_text())
TOOLS = {
    'cargo': '4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3',
    'rustc': '7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c',
    'driver': '618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7',
    'wild': '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5',
}


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def put(path, obj):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write('\n')
    os.replace(f.name, path)


def native(directory, sdk):
    jobs, links, configure, other = [], [], [], []
    calls = re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$')
    for f in sorted(directory.glob('exec.*')):
        lines = f.read_bytes().splitlines()
        terminal = re.search(rb'\+\+\+ exited with (\d+) \+\+\+', lines[-1]) if lines else None
        for raw in lines:
            m = calls.match(raw)
            if not m:
                assert not (raw.startswith(b'execve') and raw.endswith(b'= 0')), raw[:80]
                continue
            exe = Path(ast.literal_eval(m[1].decode())); argv = ast.literal_eval(m[2].decode())
            d = dict(pid=int(f.name.split('.')[-1]), exe=str(exe), argv=argv, raw=hashlib.sha256(raw).hexdigest())
            if exe.name == 'rustc' and exe.samefile(sdk / 'bin/rustc') and '--crate-name' in argv and argv[argv.index('--crate-name')+1] not in ('___', '__'):
                d['name'] = argv[argv.index('--crate-name')+1]
                d['kind'] = 'link-only' if any(a in ('link-only','-Zlink-only') or a.startswith('-Zlink-only=') for a in argv) else 'full'
                jobs.append(d)
            elif exe.name in ('ld.bfd','ld.lld','wild','wild-ld','ld','rust-lld','mold') and '-o' in argv:
                d['wild'] = exe.samefile(sdk / 'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')
                d['output'] = argv[argv.index('-o')+1]
                if not d['wild'] and exe.samefile('/usr/bin/ld') and d['output']=='conftest':
                    assert terminal is not None
                    d['exit']=int(terminal[1]); configure.append(d); continue
                links.append(d)
            else:
                other.append((f.name,str(exe),d['raw'])); continue
            assert terminal and terminal[1] == b'0', (f, str(exe))
    return dict(jobs=jobs,links=links,configure=configure,other=other)


def workspace_products(rows, ruff):
    names = {p for r in rows if r['package_id'].startswith('path+' + ruff.as_uri() + '/') for p in r['filenames'] + ([r['executable']] if r['executable'] else [])}
    assert names
    stat_cache, results = {}, {}
    for name in sorted(names):
        f = Path(name); st = f.stat(); key=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if key not in stat_cache: stat_cache[key] = sha(f)
        results[name] = dict(sha=stat_cache[key], stat=key)
    return results


def expected_reader(brand):
    return (f"Poor layout: The formatter wasn't able to pick a good layout for your document. This is an internal {brand} error. Please report if necessary.\n"
            f"Invalid document: End tag of kind Group without matching start tag.\n\n This is an internal {brand} error. Please report if necessary.\n").encode()


def main(a):
    ruff, sdk, cache, state = [p.resolve() for p in (a.ruff, a.sdk, a.cargo_cache, a.scratch)]
    assert all(' ' not in str(p) for p in (ruff,sdk,state)) and not state.exists()
    assert not state.is_relative_to(ruff) and not state.is_relative_to(cache) and not state.is_relative_to(sdk)
    state.mkdir(mode=0o700)
    a.created_scratch=True
    def run_git(*args): return subprocess.check_output(['git','-C',ruff,*args])
    def source():
        assert run_git('rev-parse','HEAD').decode().strip() == PLAN['ruff'] and not run_git('status','--porcelain=v1','-z')
        assert sha(ruff/PLAN['path']) == PLAN['file_sha256']['original']
    source()
    assert sha(HERE/'edit.patch') == PLAN['patch']
    for k in ('original','reverse'): assert sha(HERE/(k+'.rs')) == PLAN['file_sha256'][k]
    driver, = (sdk/'lib').glob('librustc_driver-*.so')
    tools = dict(cargo=sdk/'bin/cargo',rustc=sdk/'bin/rustc',driver=driver,wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')
    assert {k:sha(f) for k,f in tools.items()} == TOOLS and (sdk/'.ohm-version').read_text().strip() == PLAN['sdk']
    lock = (a.lock or (state/'lock')).open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for p in ('cargo/registry','rustup/toolchains','target','shared','home','tmp','receipts'):
        (state/p).mkdir(parents=True,exist_ok=True)
    (state/'rustup/toolchains/ohm').symlink_to(sdk)
    for name in ('cache','index'):
        subprocess.run(['cp','-a','--reflink=auto',cache/'registry'/name,state/'cargo/registry'/name],check=True)
    for name in ('config.toml','config'):
        if (cache/name).is_file(): shutil.copy2(cache/name, state/'cargo'/name)
    if (cache/'git').is_dir(): subprocess.run(['cp','-a','--reflink=auto',cache/'git',state/'cargo/git'],check=True)
    proxy = Path(shutil.which('rustup')).parent
    env = dict(HOME=str(state/'home'),PATH=str(proxy)+':/usr/local/bin:/usr/bin:/bin',USER=os.environ.get('USER','dev-user'),RUSTUP_HOME=str(state/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(state/'cargo'),CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',LC_ALL='C.UTF-8',LANG='C.UTF-8',CARGO_TERM_COLOR='never',TMPDIR=str(state/'tmp'),GIT_OPTIONAL_LOCKS='0')
    initial=shutil.disk_usage(state).free
    assert initial>12*2**30, initial
    receipt=state/'receipts'; catalog={}; roster=None; caller=None; harness=None; report=[]
    for phase in PLAN['phases']:
        stage = 'reverse' if phase in ('edit','edit-repeat') else 'original'
        d=receipt/phase; d.mkdir(); (d/'trace').mkdir()
        src=state/'source-view.rs'; wanted=(HERE/(stage+'.rs')).read_bytes()
        if not src.exists() or src.read_bytes()!=wanted:
            src.write_bytes(wanted)
        assert sha(src)==PLAN['file_sha256'][stage]
        ns=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(sdk),str(sdk),'--ro-bind',str(ruff),str(ruff),'--ro-bind',str(HERE),str(HERE),'--bind',str(state),str(state),'--ro-bind',str(src),str(ruff/PLAN['path']),'--chdir',str(ruff),'--']
        def run(args, stdin=None):
            return subprocess.run([*ns,*args],env=env,input=stdin,capture_output=True)
        assert run(['sha256sum',str(ruff/PLAN['path'])]).stdout.decode().split()[0]==PLAN['file_sha256'][stage]
        assert run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()==str(sdk)
        cargo=['cargo','+ohm',*PLAN['command'][a.mode],'--locked','--offline','-j4','--message-format=json']
        with (d/'stdout').open('xb') as so,(d/'stderr').open('xb') as se:
            proc=subprocess.Popen([*ns,'strace','-ff','-q','-s','1048576','-e','trace=execve','-o',str(d/'trace/exec'),*cargo],env=env,stdout=so,stderr=se,start_new_session=True)
            try:
                while True:
                    try: proc.wait(5); break
                    except subprocess.TimeoutExpired:
                        if shutil.disk_usage(state).free < 5*2**30: raise RuntimeError('isolated benchmark storage reached its 5 GiB reserve')
            except BaseException:
                import signal
                os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise
        assert proc.returncode==0, (phase,proc.returncode,(d/'stderr').read_text()[-2500:])
        stream=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()];assert stream[-1]=={'reason':'build-finished','success':True}
        rows=[r for r in stream if r['reason']=='compiler-artifact']; assert rows
        signature=sorted(json.dumps({k:r[k] for k in ('target','profile','package_id','features','filenames','executable','manifest_path')},sort_keys=True) for r in rows)
        if roster is None: roster=signature
        assert roster==signature
        phys=native(d/'trace',sdk);put(d/'native.json',phys)
        tracked=workspace_products(rows,ruff);put(d/'products.json',tracked)
        formatter=[Path(f) for r in rows if r['target']['name']=='ruff_formatter' and r['target']['kind']==['lib'] for f in r['filenames'] if f.endswith('.rlib')]
        if caller is None:
            consumers=[j for j in phys['jobs'] if j['name']=='ruff_python_formatter' and '--test' not in j['argv']]
            assert len(consumers)==1, [(j['name'],j['kind']) for j in consumers]
            argv=consumers[0]['argv']; ex=[argv[i+1].split('=',1)[1] for i,v in enumerate(argv) if v=='--extern' and argv[i+1].startswith('ruff_formatter=')]; assert len(ex)==1
            libs=[p for p in formatter if p.stem==Path(ex[0]).stem];assert len(libs)==1,(libs,ex)
            caller=(libs[0],[v for i,x in enumerate(argv) if x=='-L' for v in ('-L',argv[i+1])]);assert caller[1]
        lib,search=caller;assert lib in formatter
        exe=d/'reader'; cc=run(['rustc','+ohm','--edition=2024',str(HERE/'reader.rs'),'--extern','ruff_formatter='+str(lib),*search,'-C','debuginfo=0','-o',str(exe)]);(d/'reader.compile.stderr').write_bytes(cc.stderr)
        assert cc.returncode==0 and not cc.stdout and not cc.stderr,(cc.returncode,cc.stderr[-1500:]);response=run([str(exe)]);(d/'reader.stdout').write_bytes(response.stdout)
        assert response.returncode==0 and not response.stderr and response.stdout==expected_reader('Rome' if stage=='reverse' else 'Ruff'),response
        if a.mode=='build':
            cli,={r['executable'] for r in rows if r['target']['kind']==['bin'] and r['target']['name']=='ruff' and r['executable']}
            sample=run([cli,'format','--isolated','--no-cache','--stdin-filename','example.py','-'],b'x=1\n');assert sample.returncode==0 and sample.stdout==b'x = 1\n' and not sample.stderr,(sample.returncode,sample.stderr[:300])
        else:
            exe,={r['executable'] for r in rows if r['target']['kind']==['lib'] and r['target']['name']=='ruff_python_formatter' and r['executable'] and r['profile']['test']}
            sample=run([exe,'--list']);assert sample.returncode==0 and not sample.stderr and b': test' in sample.stdout
            if harness is None: harness=sample.stdout
            assert sample.stdout==harness
        (d/'behavior.stdout').write_bytes(sample.stdout)
        public={str(f.relative_to(state)):f.read_text().strip() for root in (state/'target',state/'shared') for f in root.rglob('*.public-api-hash') if f.is_file() and f.stat().st_size<4096}
        put(d/'public.json',public)
        changed=[k for k in tracked if k in catalog and tracked[k]['sha']!=catalog[k]['sha']];catalog=tracked
        counted=collections.Counter(j['kind'] for j in phys['jobs'])
        note=dict(phase=phase,stage=stage,units=len(rows),fresh=sum(r['fresh'] for r in rows),physical=dict(counted),wild=sum(v['wild'] for v in phys['links']),all_links=len(phys['links']),configure_probes=len(phys['configure']),workspace_files=len(tracked),changed_files=changed,caller=str(lib),search_directories=len(search)//2,reader=sha(d/'reader.stdout'),behavior=sha(d/'behavior.stdout'),product_sha=sha(d/'products.json'),native_sha=sha(d/'native.json'),available=shutil.disk_usage(state).free)
        put(d/'result.json',note);report.append(note);put(receipt/'progress.json',dict(phases=[z['phase'] for z in report]));print(a.mode, phase, len(rows),note['fresh'],dict(counted),note['wild'],len(changed),flush=True)
    source();put(receipt/'complete.json',dict(mode=a.mode,tools=TOOLS,ruff=PLAN['ruff'],plan=sha(HERE/'plan.json'),phases=report))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('ruff','sdk','cargo-cache','scratch'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--mode',required=True,choices=('build','test'));parser.add_argument('--lock',type=Path)
    args=parser.parse_args()
    try: main(args)
    except BaseException:
        if getattr(args,'created_scratch',False): (args.scratch/'failure.txt').write_text(traceback.format_exc())
        raise
