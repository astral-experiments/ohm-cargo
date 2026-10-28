"""Retain and diagnose the failed raw archive gate on an independent on-disk copy before any clock."""
from pathlib import Path
import importlib.util,json,os,shutil,subprocess,sys,traceback
h=Path(__file__).resolve().parent;p=h.parent;k=p/'member-build-matched-protocol-v1'
sys.path.insert(0,str(k));sys.path.insert(0,str(h))
spec=importlib.util.spec_from_file_location('native_member',k/'matched_members.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from member_archive import witness
from member_reader import search_args,validate
q=m.q
read=lambda f:json.loads(f.read_bytes())
def main():
    case,=sys.argv[1:];assert case in ('Bwasm','Cwasm','Bproject','Cproject')
    pkg='ty_wasm' if case.endswith('wasm') else 'ty_project';image=case[0]
    source=m.o/(case+'-'+pkg)
    baseline=source/('restore-repeat-two' if pkg=='ty_wasm' else 'repeat-two')
    assert (baseline/'product.json').is_file()
    own=p/('member-archive-diag-v1-'+case);assert not own.exists() and shutil.disk_usage(p).free>85*2**30
    os.sched_setaffinity(0,{12,13,14,15});own.mkdir(mode=0o700)
    assert not (p/'member-build-wall-v1').exists()
    st=own/'state';subprocess.run(['cp','-a','--reflink=auto','--',source/'state',st],check=True)
    vis=own/'visible-functools.pyi';shutil.copy2(source/'visible-functools.pyi',vis)
    loc=read(k/'locations.json');bind=read(source/'binding.json');drv=next(Path(n).name for n in bind['hashes'] if 'librustc_driver-' in n)
    env=q.opts(st,q.sdk/'bin/cargo')[1]
    env.update(HOME=str(m.canonical/'home'),CARGO_TARGET_DIR=str(m.target),CARGO_BUILD_BUILD_DIR=str(m.canonical/'shared'),CARGO_HOME=str(m.canonical/'cargo'),RUSTUP_HOME=str(m.o/('view-'+case)/'rustup'),CARGO_BUILD_JOBS='4')
    br=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(m.images/loc['common']),str(m.sdk),
        '--ro-bind',str(m.images/loc[image]['cargo']),str(m.sdk/'bin/cargo'),'--ro-bind',str(m.images/loc[image]['driver']),str(m.sdk/'lib'/drv)]
    for n in ('target','shared','home','cargo'):br+=['--bind',str(st/n),str(m.target if n=='target' else m.canonical/n)]
    def run(argv,dot):return subprocess.run([*br,'--ro-bind',str(vis),str(q.src/m.stub),'--bind',str(dot),str(dot),'--chdir',q.src/'crates'/pkg,'--',*argv],env=env,capture_output=True,stdin=subprocess.DEVNULL)
    cmd=['cargo','+ohm','build','--locked','--offline','-j4','--message-format=json']
    raw=read(baseline/'product.json');names=raw['outputs'];search=search_args(source/'cold',pkg)
    snap=lambda:{n:q.sha(st/'target'/n) for n in names}
    assert snap()==names
    steps=[('anchor','original'),('unchanged-one','original'),('unchanged-two','original')]
    if pkg=='ty_wasm':steps+=[('edit','reversed'),('edit-repeat','reversed'),('restore','original'),('restore-repeat','original')]
    history=[];raw_rejected=[];current='original';known={}
    for tag,kind in steps:
        dot=own/tag;dot.mkdir()
        if current!=kind:
            old=vis.stat().st_mtime_ns;vis.write_bytes((k/('stub-'+kind+'.pyi')).read_bytes());assert vis.stat().st_mtime_ns>old;current=kind
        if tag!='anchor':
            cp=run(cmd,dot);(dot/'stdout').write_bytes(cp.stdout);(dot/'stderr').write_bytes(cp.stderr)
            assert cp.returncode==0,(tag,cp.stderr[-1000:])
            rows=[json.loads(v) for v in cp.stdout.splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
        seq=snap();w={n:witness(st/'target'/n) for n in seq if n.endswith('.rlib')}
        typed={n:w[n]['typed'] if n in w else v for n,v in seq.items()}
        for n,v in w.items():assert v['raw']==seq[n]
        # Changed archive names are retained in each witness. Each position still binds the whole object.
        oracle=validate(pkg,dot,run,m.target,seq,search,(k/'reader.rs').read_bytes(),vis.read_bytes())
        q.put(dot/'witness.json',dict(tag=tag,input=kind,raw=seq,typed=typed,archives=w,caller=oracle))
        if kind not in known:known[kind]=typed
        if known[kind]!=typed:q.put(dot/'typed-failure.json',dict(expected=known[kind],got=typed))
        if kind=='original' and seq!=names:raw_rejected.append(tag)
        history.append(dict(tag=tag,input=kind,raw=seq,typed=typed,caller=oracle['sha256'],matches_anchor=known[kind]==typed))
        q.put(own/'progress.json',history)
    q.put(own/'complete.json',dict(case=case,raw_rejected=raw_rejected,history=history,clocks=0))
if __name__=='__main__':
    try:main()
    except BaseException:
        (h/('failure-'+sys.argv[1]+'.txt')).write_text(traceback.format_exc());raise
