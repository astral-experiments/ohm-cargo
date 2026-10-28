"""Physical maintenance on H5, with the frozen original logical root in each native child."""
import collections, fcntl, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028');OLD=P/'whole-wild-width-v1';NEW=P/'whole-wild-width-v2'
G=P/'wall-protocol-v2';CONT=P/'whole-wild-width-v2-protocol';SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(G));sys.path.insert(0,str(OLD/'source'));sys.path.insert(0,str(CONT/'source'))
from worker import HIST,K,W,attach,load
from wild import sha,read
from records import check_wire,compare


def namespace(base,state,arm,edit,receipt,phase):
    # The frozen Cargo runner supplies every original SDK, source and target binding.
    # Only physical sources of these two wildcard-capture binds are updated.
    ns,env,h=base(state,arm,edit,receipt)
    n=load(K/'ruff_worker.py');stock=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    pos=ns.index('--chdir');ns[pos:pos]=['--bind',str(NEW),str(OLD),'--ro-bind',str(NEW/'wild-wrapper'),str(stock)]
    env['WILD_PHASE']=phase
    assert not set(env)&{'RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','LD_PRELOAD','RAYON_NUM_THREADS','WILD_EXPERIMENT'}
    old=lambda arg:str(OLD)+str(arg)[len(str(NEW)):] if str(arg)==str(NEW) or str(arg).startswith(str(NEW)+'/') else str(arg)
    prior,environ,original_h=base(Path(old(state)),arm,edit,Path(old(receipt)))
    prior,environ=attach(prior,environ,receipt,stock,phase)
    assert [old(arg) for arg in ns]==prior and env==environ and h==original_h
    return ns,env,h


def namespaces(read_only=False):
    mode='--ro-bind' if read_only else '--bind'
    return ['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        mode,str(NEW),str(OLD),mode,str(NEW),str(NEW),'--chdir',str(OLD),'--']


def checked(phase,memory,targets):
    directory=NEW/'commands'/phase
    current=check_wire(memory,(directory/'products.json').read_bytes())
    old=read(W/phase/'products.json');registry=read(directory/'registry-native.json')
    compare(phase,current,old,registry,targets)
    if not phase.startswith('seed'):
        assert registry==read(W/phase/'registry-native.json') and sha(directory/'e2e-list')==sha(W/phase/'e2e-list')
    assert len(list((NEW/'captures'/phase).glob('*/capture.json')))==HIST[phase][0]
    print('qualified command',phase,HIST[phase][0],flush=True)


def file_ids(root):
    return {(s.st_dev,s.st_ino) for f in root.rglob('*') if f.is_file() and not f.is_symlink() and (s:=f.stat())}


def run():
    assert not OLD.samefile(NEW) and not (NEW/'commands/seed-repeat2').exists()
    assert not (NEW/'states/observer').exists() and not (NEW/'states/composed').exists()
    n=load(K/'ruff_worker.py');g=load(G/'guards.py');n.source()
    base=n.invocation;targets=read(NEW/'targets.json');seed=read(NEW/'seed.json')
    assert g.tree(n.seed)==seed and g.tree(NEW/'states/seed')==read(NEW/'tree-before-resume.json')['seed_state']
    checked('seed-repeat1',read(NEW/'commands/seed-repeat1/products.json'),targets)
    for color in ['seed','observer','composed']:
        state=NEW/'states'/color
        if color!='seed':
            assert shutil.disk_usage(P).free > 44*2**30+seed['unique_file_bytes'] and not state.exists()
            subprocess.run(['cp','-a','--reflink=never','--',n.seed,state],check=True)
            assert g.tree(state)==seed
            ids=file_ids(state)
            for other in [n.seed,*(r for r in (NEW/'states').iterdir() if r!=state)]:
                assert ids.isdisjoint(file_ids(other))
        todo=['seed-repeat2'] if color=='seed' else ['selected-'+color,'repeat-'+color]
        for phase in todo:
            assert shutil.disk_usage(P).free>44*2**30
            d=NEW/'commands'/phase;(NEW/'captures'/phase).mkdir()
            arm='observer' if color=='seed' else color
            n.invocation=lambda s,a,e,o:namespace(base,s,a,e,o,phase)
            try:product=n.build(state,arm,n.excluded if color=='seed' else n.selected,color!='seed',d,True)
            finally:n.invocation=base
            checked(phase,product,targets)
    assert g.tree(n.seed)==seed
    # Sole namespace for the original independent verifier, which creates its
    # terminal artifacts in physical NEW while reading exact old logical paths.
    subprocess.run(namespaces()+['/usr/bin/python3','-IBu',str(OLD/'source/verify.py')],check=True)
