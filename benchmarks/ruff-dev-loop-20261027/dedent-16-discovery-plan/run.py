"""Discover work caused by the latest Ruff trivia edit on the distributed compiler."""
from collections import Counter
from pathlib import Path
import ast
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import traceback

root = Path(__file__).resolve().parent
P = Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
release = P.parent / 'ohm-packaged-16-macro-20261027'
sdk = release / 'installed-sdk'
repo = P / 'source'
W = root / 'source'
plan = json.loads((root/'plan.json').read_bytes())
assert socket.gethostname() == 'charlie-ohm-relink-perf-1024' and not sys.flags.optimize
os.sched_setaffinity(0, set(range(16, 24)))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def room(min_gib=8): assert shutil.disk_usage(root).free > min_gib * 2**30
def git(*args):
    return subprocess.check_output(['git','-C',repo,*args],env=dict(os.environ,GIT_OPTIONAL_LOCKS='0'))
def gate(state):
    for rel,row in plan['source'].items():
        p=W/rel
        assert (sha(p) if p.is_file() else None) == row['reversed' if state=='reversed' else 'original'],(state,rel)
def adjust(state):
    args=['git','apply',*(['--reverse'] if state=='reversed' else [])]
    subprocess.run([*args,'--check',str(root/'historical.patch')],cwd=W,check=True)
    subprocess.run([*args,str(root/'historical.patch')],cwd=W,check=True)
    gate(state)
def child(cmd,env,cwd,out):
    with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
        isolated=['bwrap','--die-with-parent','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(root),str(root),'--chdir',str(cwd),'--']
        p=subprocess.Popen(isolated+cmd,env=env,cwd=cwd,stdout=so,stderr=se,start_new_session=True)
        try:
            while p.poll() is None:
                room()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
        except BaseException:
            if p.poll() is None: os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30)
            raise
    save(out/'exit.json',{'returncode':p.returncode})
    assert p.returncode==0,(out,(out/'stderr').read_bytes()[-1800:])
def native_trace(out):
    jobs=[]; links=[]; counts=Counter(); paths=set()
    for f in sorted(out.glob('exec.*')):
        for l in f.read_bytes().splitlines():
            m=re.fullmatch(rb'execve\((".*?"), (\[.*\]), .*\)\s+= 0',l)
            if not m:continue
            path=Path(ast.literal_eval(m[1].decode()));a=ast.literal_eval(m[2].decode())
            if path.resolve()==(sdk/'bin/cargo').resolve():counts['cargo']+=1
            if path.resolve()==(sdk/'bin/rustc').resolve() and '--crate-name' in a and not any(v.startswith('--print') for v in a):
                jobs.append([a[a.index('--crate-name')+1],'link-only' if any(v in ('-Zlink-only','link-only') for v in a) else 'full'])
            if path.name=='ld.bfd' and path.parent.name=='wild-ld':
                assert sha(path)==plan['wild']
                links.append(Path(a[a.index('-o')+1]).name if '-o' in a else None)
            if path.name=='collect2':counts['collect2']+=1
            paths.add(str(path))
    assert counts['cargo']==1 and counts['collect2']==len(links),(counts,links)
    return dict(jobs=jobs,wild=links,counts=dict(counts),process_paths=sorted(paths))
def witness(out,env,art,state):
    dependencies=set(); versions=set()
    for msg in art:
        for path in map(Path,msg['filenames']):
            if path.suffix in ('.rlib','.so','.rmeta'): dependencies.add(path.parent)
            if msg['target']['name']=='ruff_python_trivia' and path.suffix=='.rlib':versions.add(path)
    if len(versions)>1:
        # Dev and test may select different features. Require a real matching diagnostic from every producer.
        assert len(versions)<=3
    assert versions
    printed=[]
    for i,lib in enumerate(sorted(versions)):
        f=out/('ordinary-'+str(i));f.mkdir();app=f/'dedent'
        args=['rustc','+ohm','--edition=2024',str(root/'ordinary.rs'),'--extern','ruff_python_trivia='+str(lib)]
        for directory in sorted(dependencies):args+=['-L','dependency='+str(directory)]
        args+=['-o',str(app)];save(f/'argv.json',args)
        child(args,env,W,f);v=subprocess.run([app],env=env,capture_output=True)
        (f/'native.stdout').write_bytes(v.stdout);(f/'native.stderr').write_bytes(v.stderr)
        assert v.returncode==0 and not v.stderr and v.stdout.decode()==plan['oracles'][state],(lib,state,v.stdout,v.stderr)
        printed.append(dict(exe_sha256=sha(app),library_sha256=sha(lib),stdout=v.stdout.decode()))
    return printed
def command(mode,phase,env,state,trace=False,probe=False):
    gate(state); out=root/'records'/mode/phase;out.mkdir(parents=True)
    args=['cargo','+ohm',mode,*(['--no-run'] if mode=='test' else []),'-p','ruff_python_parser','--locked','--offline','-j8','--message-format=json']
    save(out/'argv.json',args)
    prefix=['strace','-ff','-qq','-e','trace=execve','-s','100000','-o',str(out/'exec')] if trace else []
    child(prefix+args,env,W,out)
    msgs=[json.loads(l) for l in (out/'stdout').read_bytes().splitlines()]
    assert msgs[-1]==dict(reason='build-finished',success=True)
    art=[m for m in msgs if m['reason']=='compiler-artifact']
    assert art and any(m['target']['name']=='ruff_python_parser' for m in art)
    outputs={}
    for m in art:
        for s in [*m['filenames'],*([m['executable']] if m.get('executable') else [])]:
            p=Path(s);assert p.is_file()
            outputs[str(p)]=sha(p)
    result=dict(total=len(art),fresh=sum(m['fresh'] for m in art),dirty=[m['target']['name'] for m in art if not m['fresh']],artifacts=outputs,elf={m['executable']:outputs[m['executable']] for m in art if m.get('executable')})
    if trace:result['processes']=native_trace(out)
    if probe:result['ordinary']=witness(out,env,art,state)
    save(out/'receipt.json',result);return result
def study():
    room(15)
    assert sha(root/'historical.patch')==plan['patch_sha256']
    assert git('rev-parse','HEAD').decode().strip()==plan['ruff'] and not git('status','--porcelain').strip()
    assert sha(sdk/'bin/cargo')==plan['cargo'] and sha(sdk/'bin/rustc')==plan['frontend']
    drv,=(sdk/'lib').glob('librustc_driver-*.so');assert sha(drv)==plan['driver']
    assert sha(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')==plan['wild']
    assert not W.exists();W.mkdir()
    archive=subprocess.Popen(['git','-C',repo,'archive',plan['ruff']],stdout=subprocess.PIPE)
    untar=subprocess.run(['tar','-x','-C',W],stdin=archive.stdout);archive.stdout.close();assert archive.wait()==untar.returncode==0;gate('original')
    cache=root/'registry-home';cache.mkdir()
    subprocess.run(['cp','-a','--reflink=auto','--',str((P/'registry-home/registry').resolve()),cache/'registry'],check=True)
    room(12)
    for p in ('config','config.toml','git'):
        src=P/'registry-home'/p
        if src.exists():(cache/p).symlink_to(src)
    env={'HOME':str(Path.home()),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PATH':str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin','RUSTUP_HOME':str(release/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(cache),'GIT_OPTIONAL_LOCKS':'0','CARGO_NET_OFFLINE':'true'}
    for mode in ('build','test'):
        env.update(CARGO_BUILD_BUILD_DIR=str(root/'build-dir'/mode),CARGO_TARGET_DIR=str(root/'target'/mode))
        print('starting',mode,flush=True); gate('original')
        cold=command(mode,'cold',env,'original',probe=True);assert cold['fresh']==0
        for i in range(1,5):
            r=command(mode,'train-'+str(i),env,'original',trace=True)
            if r['total']==r['fresh']:break
        assert r['total']==r['fresh'] and not r['processes']['jobs'] and not r['processes']['wild']
        for state in ('reversed','restored'):
            adjust(state);c=command(mode,state,env,state,trace=True,probe=True)
            assert c['total']==cold['total'] and c['fresh']<c['total']
            f=command(mode,state+'-fresh',env,state,trace=True)
            assert f['total']==f['fresh']==c['total'] and f['artifacts']==c['artifacts']
            assert not f['processes']['jobs'] and not f['processes']['wild']
    assert not git('status','--porcelain').strip();save(root/'complete.json',dict(ruff=plan['ruff'],timed_samples=0,phases=2))
with (P/'native-measure.lock').open('a') as handle:
    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try: study()
    except BaseException: (root/'failure.txt').write_text(traceback.format_exc()); raise
