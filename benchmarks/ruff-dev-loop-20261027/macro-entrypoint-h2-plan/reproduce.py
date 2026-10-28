"""Run the fixed Ruff macro edit sequence and validate both affected macro entry points."""
from pathlib import Path
import argparse
import ast
import collections
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
cfg=json.loads((HERE/'plan.json').read_bytes())
def sha(f):
    with f.open('rb') as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
def put(f,data):
    tmp=f.with_suffix('.pending');tmp.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n');os.replace(tmp,f)

def processes(trace,sdk):
    results=[];invoke=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$')
    for pid in sorted(trace.glob('exec.*')):
        lines=pid.read_bytes().splitlines()
        for line in lines:
            m=invoke.match(line)
            if not m:
                assert not (line.startswith(b'execve(') and line.endswith(b'= 0')),pid
                continue
            binary=Path(ast.literal_eval(m[1].decode()));argv=ast.literal_eval(m[2].decode());kind=None
            if binary.name=='rustc' and binary.samefile(sdk/'bin/rustc') and '--crate-name' in argv and argv[argv.index('--crate-name')+1] not in ('___','__'):
                kind='link-only' if any(a=='link-only' or a.startswith('-Zlink-only') for a in argv) else 'full'
                name=argv[argv.index('--crate-name')+1]
            elif binary.name in ('ld.bfd','ld','ld.lld','wild','wild-ld','rust-lld','mold') and '-o' in argv:
                kind='wild' if binary.samefile(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd') else 'other-linker';name=argv[argv.index('-o')+1]
            if kind:
                terminal=re.search(rb'\+\+\+ exited with (\d+) \+\+\+',lines[-1]);assert terminal,(pid,kind)
                results.append(dict(pid=pid.name,kind=kind,name=name,exe=str(binary),argv=argv,exit=int(terminal[1]),raw=hashlib.sha256(line).hexdigest()))
    return results

def main(arg):
    sdk,ruff,cache,state=[p.resolve() for p in (arg.sdk,arg.ruff,arg.cargo_cache,arg.scratch)]
    assert not state.exists() and all(' ' not in str(p) for p in (sdk,state,ruff)) and not state.is_relative_to(ruff) and not state.is_relative_to(cache)
    assert shutil.disk_usage(state.parent).free>6*2**30
    driver,=(sdk/'lib').glob('librustc_driver-*.so');bins={'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','driver':driver,'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
    assert {k:sha(v) for k,v in bins.items()}==cfg['tools'] and (sdk/'.ohm-version').read_text().strip()==cfg['sdk']
    def git(*args):return subprocess.check_output(['git','-C',ruff,*args])
    def check_source():
        assert git('rev-parse','HEAD').decode().strip()==cfg['ruff'] and not git('status','--porcelain=v1','-z')
        for key,p in cfg['source'].items(): assert sha(ruff/p)==sha(HERE/(key+'.rs'))
    check_source();lock=arg.lock.open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state.mkdir(mode=0o700);arg.created=True
    for n in ('target','shared','tmp','home','cargo/registry','rustup/toolchains','receipts','view'):(state/n).mkdir(parents=True)
    (state/'rustup/toolchains/ohm').symlink_to(sdk)
    for sub in ('cache','index'):subprocess.run(['cp','-a','--reflink=auto',cache/'registry'/sub,state/'cargo/registry'/sub],check=True)
    for sub in ('config.toml','config'):
        if (cache/sub).is_file():shutil.copy2(cache/sub,state/'cargo'/sub)
    if (cache/'git').is_dir():subprocess.run(['cp','-a','--reflink=auto',cache/'git',state/'cargo/git'],check=True)
    proxy=Path(shutil.which('rustup')).parent
    env=dict(HOME=str(state/'home'),PATH=str(proxy)+':/usr/local/bin:/usr/bin:/bin',USER=os.environ.get('USER','dev-user'),RUSTUP_HOME=str(state/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(state/'cargo'),CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',LC_ALL='C.UTF-8',LANG='C.UTF-8',CARGO_TERM_COLOR='never',TMPDIR=str(state/'tmp'),GIT_OPTIONAL_LOCKS='0')
    receipts=state/'receipts';roster=None;history=[];previous=None;last_listing=None
    for phase,variant in cfg['phases']:
        assert shutil.disk_usage(state).free>3*2**30
        dest=receipts/phase;dest.mkdir();(dest/'trace').mkdir()
        ns=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(state),str(state),'--ro-bind',str(ruff),str(ruff)]
        for key,path in cfg['source'].items():
            input_name=cfg['variants'][variant].get(key,key+'.rs');view=state/'view'/(key+'.rs');actual=(HERE/input_name).read_bytes()
            if not view.exists() or view.read_bytes()!=actual:view.write_bytes(actual)
            ns.extend(['--ro-bind',str(view),str(ruff/path)])
        ns+=['--chdir',str(ruff),'--']
        def run(args):return subprocess.run(ns+list(map(str,args)),env=env,capture_output=True)
        def noted(name,args,code):
            r=run(args);(dest/(name+'.stdout')).write_bytes(r.stdout);(dest/(name+'.stderr')).write_bytes(r.stderr)
            assert r.returncode==code,(phase,name,r.returncode,r.stderr[-2500:]);return r
        for key,path in cfg['source'].items(): assert run(['sha256sum',ruff/path]).stdout.decode().split()[0]==sha(state/'view'/(key+'.rs'))
        assert run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()==str(sdk)
        args=['cargo','+ohm',*cfg['commands'][arg.mode],'--locked','--offline','-j4','--message-format=json']
        cargo=noted('cargo',['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',dest/'trace/exec',*args],0)
        stream=[json.loads(line) for line in cargo.stdout.splitlines()];assert stream[-1]=={'reason':'build-finished','success':True}
        rows=[r for r in stream if r['reason']=='compiler-artifact'];assert rows
        signature=sorted(json.dumps({k:r[k] for k in ('target','profile','package_id','features','filenames','executable','manifest_path')},sort_keys=True) for r in rows)
        if roster is None:roster=signature
        assert roster==signature
        native=processes(dest/'trace',sdk);put(dest/'native.json',native)
        assert all(p['exit']==0 for p in native) and not any(p['kind']=='other-linker' for p in native),(phase,[(p['kind'],p['name'],p['exit']) for p in native if p['exit'] or p['kind']=='other-linker'])
        targets=[r for r in rows if r['package_id'].startswith('path+'+ruff.as_uri()+'/')]
        products={p:sha(Path(p)) for r in targets for p in r['filenames']+([r['executable']] if r['executable'] else [])};assert products
        dso,={p for r in rows if r['target']['name']=='ruff_macros' and r['target']['kind']==['proc-macro'] for p in r['filenames'] if p.endswith('.so')}
        base=['rustc','+ohm','--edition=2024','-C','debuginfo=0']; extern=['--extern','ruff_macros='+dso]
        direct=dest/'direct-consumer';noted('direct-compile',[*base,HERE/'direct.rs',*extern,'-o',direct],0)
        expected=b'4294967293\n' if variant=='used' else b'4294967294\n';assert noted('direct-run',[direct],0).stdout==expected
        neg=noted('negative-compile',[*base,'--emit=metadata',HERE/'reject.rs',*extern,'-o',dest/'rejected.rmeta'],1)
        want=b'expected prefix string to be non-blank' if variant=='diagnostic' else b'expected prefix string to be non-empty';assert want in neg.stderr and not (dest/'rejected.rmeta').exists()
        if arg.mode=='build':
            lib,={p for r in rows if r['target']['name']=='ruff_index' for p in r['filenames'] if p.endswith('.rlib')}
            search=sorted({str(Path(p).parent) for r in rows for p in r['filenames'] if p.endswith(('.so','.rlib','.rmeta'))});path=dest/'reexport-consumer'
            noted('reexport-compile',[*base,HERE/'reexport.rs','--extern','ruff_index='+lib,*(a for p in search for a in ('-L','dependency='+p)),'-o',path],0)
            assert noted('reexport-run',[path],0).stdout==expected
        else:
            test,={r['executable'] for r in rows if r['target']['name']=='ruff_index' and r['profile']['test'] and r['executable']};listing=noted('test-list',[test,'--list'],0).stdout
            assert listing.count(b': test\n')==5 and (last_listing is None or listing==last_listing);last_listing=listing
        changes=[] if previous is None else sorted(p for p in products if products[p]!=previous[p]);previous=products
        put(dest/'products.json',products);note=dict(phase=phase,variant=variant,units=len(rows),fresh=sum(r['fresh'] for r in rows),physical=dict(collections.Counter(p['kind'] for p in native)),changed=changes,dso=products[dso],native=sha(dest/'native.json'),products=sha(dest/'products.json'))
        put(dest/'result.json',note);history.append(note);put(receipts/'progress.json',history)
        print(arg.mode,phase,note['units'],note['fresh'],note['physical'],len(changes),flush=True)
    check_source();put(receipts/'complete.json',dict(mode=arg.mode,phases=history,plan=sha(HERE/'plan.json'),tools=cfg['tools']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('sdk','ruff','cargo-cache','scratch','lock'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--mode',choices=('build','test'),required=True);args=parser.parse_args()
    try:main(args)
    except BaseException:
        if getattr(args,'created',False):(args.scratch/'failure.txt').write_text(traceback.format_exc())
        raise
