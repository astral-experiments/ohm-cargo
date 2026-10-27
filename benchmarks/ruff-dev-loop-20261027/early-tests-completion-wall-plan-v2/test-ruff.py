"""Prepare and validate an actual first test selection against the packaged Cargo."""
from pathlib import Path
import collections
import hashlib
import json
import os
import shutil
import socket
import subprocess
import traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
src=Path('/home/dev-user/code/oss/ruff-early-completion-20261027')
lab=p/'ruff-native-v1'
c=p/'ruff-canonical-v1'
sdk=p/'official/sdk'
pin='93526150df078af7dd8fc4226cdcc469539d2001'
index='fc84f15ac7401cd9bdc362e4574c6d395529766c16be2e6b032ac47fa63d21cd'
binding='ba5ad71b4d01b570f1c6c4a1cce46e29b9afd52bb243bc3a7d315f76a45ddf2f'
file=Path('crates/ty_server/tests/e2e/inlay_hints.rs')
original='a025b90170c496d6336023fa8857c4d2cb2ef77c2e601bf119e9feb3c1a71624'
reversed_='24d443ea2c65e5879884b32e761fea2d5e0f3cd198fd0ea9a44bd27e52078fad'
seed=['test','--no-run','--workspace','--exclude','ty_server']
select=['test','--no-run','--workspace']

def sha(f):
    with f.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def put(f,obj):
    f.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')

def source_gate():
    def git(*args):return subprocess.check_output(['git','--no-optional-locks','-C',src,*args])
    assert git('rev-parse','HEAD').decode().strip()==pin and not git('status','--porcelain','-z')
    assert hashlib.sha256(git('ls-files','-s','-z')).hexdigest()==index and sha(src/file)==original

def state(t):
    t.mkdir(mode=0o700);[(t/n).mkdir(mode=0o700) for n in ('target','shared','cargo','home')]
    ref=json.loads((p/'inputs/subject.json').read_bytes());r=t/'cargo/registry'
    name,=[d.name for d in (p/'cargo-home/registry/index').iterdir() if hashlib.sha256(d.name.encode()).hexdigest()=='85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381']
    idx=r/'index'/name;cache=r/'cache'/name;idx.mkdir(parents=True);cache.mkdir(parents=True)
    srcconfig=p/'cargo-home/registry/index'/name/'config.json'; assert sha(srcconfig)=='b53c1616e30600e72868bee2d214fd7a5495759368db642698f2af5f38f714d6'
    shutil.copy2(srcconfig,idx/'config.json')
    for kind,mapping in [('crates',ref['crates']),('index',ref['index'])]:
        for rel,h in mapping.items():
            item=p/'inputs'/rel;assert sha(item)==h
            out=cache/item.name if kind=='crates' else idx/'.cache'/Path(rel).relative_to('index')
            out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,out)
    assert sha(p/'inputs/subject.json')==binding
    assert not any((t/'target').iterdir()) and not any((t/'shared').iterdir())

def opts(t,exe,overlay=None):
    env=dict(HOME=str(c/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
             USER='dev-user',RUSTUP_HOME=str(p/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',
             CARGO_HOME=str(c/'cargo'),CARGO_TARGET_DIR=str(c/'target'),CARGO_BUILD_BUILD_DIR=str(c/'shared'),
             CARGO_BUILD_JOBS='8',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0',LANG='C.UTF-8',LC_ALL='C.UTF-8')
    args=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
    for n in ('target','shared','cargo','home'):args+=['--bind',str(t/n),str(c/n)]
    if exe!=sdk/'bin/cargo':args+=['--ro-bind',str(exe),str(sdk/'bin/cargo')]
    if overlay:
        assert sha(overlay)==reversed_
        args+=['--ro-bind',str(overlay),str(src/file)]
    return args,env

def printed(t,name):
    f=Path(name)
    for k in ('target','shared'):
        if f.is_relative_to(c/k):return t/k/f.relative_to(c/k)
    raise ValueError(name)

def run(t,exe,cmd,out,overlay=None,trace=False):
    out.mkdir(mode=0o700)
    args,env=opts(t,exe,overlay)
    argv=['cargo','+ohm',*cmd,'--locked','--offline','-j8','--message-format=json']
    op=argv
    if trace:
        env['CARGO_LOG']='cargo::compiler::ohm_early_tests=info,cargo::compiler::job_queue=debug'
        (out/'trace').mkdir()
        op=['strace','-q','-ff','-ttt','-s','1048576','-e','trace=execve,execveat','-e','signal=SIGCHLD','-o',str(out/'trace/exec'),*argv]
    args+=['--bind',str(out),str(out),'--chdir',str(src),'--']
    actual=subprocess.check_output([*args,'sha256sum',str(sdk/'bin/cargo')],env=env).split()[0].decode()
    assert actual==sha(exe)
    with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
        rc=subprocess.run([*args,*op],env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se).returncode
    put(out/'command.json',dict(command=argv,exit=rc,cargo=actual,source=pin,input=sha(overlay) if overlay else original,
        stdout=sha(out/'stdout'),stderr=sha(out/'stderr'),trace=trace,affinity=sorted(os.sched_getaffinity(0))))
    assert rc==0,(out,rc)
    rows=[json.loads(l) for l in (out/'stdout').read_bytes().splitlines()]
    assert rows[-1]=={'reason':'build-finished','success':True}
    arts=[r for r in rows if r['reason']=='compiler-artifact']; natives={}; exes=set(); own=[]
    assert len(arts)>600
    for r in arts:
        if not r['package_id'].startswith('path+'):continue
        if r['executable']:exes.add(r['executable'])
        for n in r['filenames']:
            f=printed(t,n)
            if r['target']['name']=='ty_server' and r['target']['kind']==['lib'] and n.endswith('.rlib'):
                own.append(dict(path=n,sha256=sha(f),features=r['features'],fresh=r['fresh']))
            if f.suffix not in ('','.so'):continue
            with f.open('rb') as read:magic=read.read(4)
            if magic==b'\x7fELF':natives[n]=sha(f)
    assert len(own)==1 and exes<=natives.keys()
    target=[r for r in arts if r['package_id'].startswith('path+') and Path(r['manifest_path']).parent.name=='ty_server' and r['target']['name']=='e2e' and r['target']['kind']==['test']]
    rec=dict(units=len(arts),dirty=[(r['target']['name'],r['target']['kind']) for r in arts if not r['fresh']],
             native=natives,executables=sorted(exes),ty_server=own[0],e2e=[x['executable'] for x in target],
             roster=digest(sorted(json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in arts)),
             diagnostics=sorted(json.dumps([r['package_id'],r['target']['name'],r['message']],sort_keys=True) for r in rows if r['reason']=='compiler-message'))
    if cmd==select:
        assert (len(arts),len(exes),len(natives),len(target))==(619,102,110,1)
        assert collections.Counter(bool(r['profile']['test']) for r in arts if r['executable'])=={True:84,False:18}
    else:assert not target
    put(out/'product.json',rec)
    return rec

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024' and (p/'run-product-v2/exit').read_text()=='0'
    assert not lab.exists() and not c.exists() and shutil.disk_usage(p).free>160*2**30
    os.sched_setaffinity(0,set(range(16)))
    source_gate();lab.mkdir(mode=0o700);c.mkdir(mode=0o700)
    for n in ('target','shared','cargo','home'):(c/n).mkdir(mode=0o700)
    t=lab/'official-before-selection';state(t)
    exe=sdk/'bin/cargo';assert sha(exe)=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
    print('training workspace test build excluding ty_server',flush=True)
    first=run(t,exe,seed,lab/'seed-0')
    assert not first['ty_server']['fresh']
    for k in range(1,5):
        stable=run(t,exe,seed,lab/('seed-'+str(k)))
        assert stable['ty_server']['sha256']==first['ty_server']['sha256']
        if not stable['dirty']:break
    else:raise RuntimeError('seed failed to settle')
    print('seed settled, validating real first selection on an independent copy',flush=True)
    s=lab/'official-selection-control'
    subprocess.run(['cp','-a','--reflink=auto','--',str(t),str(s)],check=True)
    original_rlib=printed(t,stable['ty_server']['path']);copy=printed(s,stable['ty_server']['path'])
    assert not original_rlib.samefile(copy) and sha(copy)==sha(original_rlib)
    edited=p/'inputs/ruff-edited-inlay-hints.rs';assert sha(edited)==reversed_
    rec=run(s,exe,select,lab/'official-selection',edited,trace=True)
    assert rec['ty_server']['fresh'] and rec['ty_server']['sha256']==stable['ty_server']['sha256']
    assert not printed(t,rec['e2e'][0]).exists() and printed(s,rec['e2e'][0]).is_file()
    source_gate()
    put(lab/'complete.json',dict(seed_steps=k+1,seed_units=stable['units'],selected_units=rec['units'],
        seed_rlib=stable['ty_server'],selected_rlib=rec['ty_server'],selected_e2e=rec['e2e'],index=index,
        tool=sha(exe),source_unchanged=sha(src/file)==original))
    print('official seed and selection completed',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException:
        if lab.is_dir():(lab/'failure.txt').write_text(traceback.format_exc())
        raise
