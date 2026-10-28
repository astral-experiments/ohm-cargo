"""Resume unchanged worker phases from a retained, independently checked seed copy."""
import fcntl, hashlib, json, os, shutil, socket, subprocess, sys, traceback
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
OLD=P/'whole-wild-width-v1';NEW=P/'whole-wild-width-v2';HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(OLD/'source'))
from records import check_wire, compare
import worker
from wild import R,STOCK,WILD,digest,read,sha,write
from worker import F,G,HIST,K,PHASES,SOURCE,W,attach,floor,load
from verify import verify


def qualification(phase,product,state,expected):
    d=R/'commands'/phase
    current=check_wire(product,(d/'products.json').read_bytes())
    old=read(W/phase/'products.json'); registry=read(d/'registry-native.json')
    compare(phase,current,old,registry,expected)
    if not phase.startswith('seed'):
        assert registry==read(W/phase/'registry-native.json') and sha(d/'e2e-list')==sha(W/phase/'e2e-list')
    count=len(list((R/'captures'/phase).glob('*/capture.json')));assert count==HIST[phase][0]
    print('qualified command',phase,count,flush=True)


def run():
    assert socket.gethostname()=='charlie-ohm-c5-check-1025' and OLD.samefile(NEW) and R==OLD
    reg=read(NEW/'continuation-registration.json');assert len(reg['continuation_ref'])==len(reg['stopped_evidence_ref'])==40
    assert reg['original_ref']=='5b9490236f0557fb748a7b7e527e45452002904b'
    assert reg['original_protocol_sha256']==sha(SOURCE/'SHA256SUMS')=='d116e7b75a81b1a5b8664248ab26425cc6ed4912abf7631e8cccdb4a14c7ead7'
    assert reg['continuation_sha256']==sha(HERE/'SHA256SUMS')
    for directory in (SOURCE,HERE):
        for line in (directory/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ');assert sha(directory/name)==h
    frozen=read(HERE/'stopped-source-binding.json')
    for p,key in [(R/'failure.txt','traceback'),(R/'exit','exit'),(R/'seed.json','seed'),(R/'commands/seed-repeat1/products.json','seed_617_products')]:
        assert sha(p)==frozen[key]
    assert sha(SOURCE/'worker.py')==frozen['worker'] and sha(STOCK)==WILD
    assert read(R/'tree-before-resume.json')['seed_state'] and not (R/'commands/seed-repeat2').exists()
    n=load(K/'ruff_worker.py');g=load(G/'guards.py');n.source()
    true_seed=read(R/'seed.json');assert g.tree(n.seed)==true_seed
    assert g.tree(R/'states/seed')==read(R/'tree-before-resume.json')['seed_state']
    targets=read(R/'targets.json');stock=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    base=n.invocation;assert sha(stock)==WILD; os.sched_setaffinity(0,set(range(16)))
    # All previous captured sources and raw receipts remain untouched at the old
    # physical root. The outer namespace binds only their distinct copy here.
    for phase,k in frozen['native_control_index'].items():
        captures={q.parent.name:sha(q) for q in (R/'captures'/phase).glob('*/capture.json')}
        assert len(captures)==k['targets'] and digest(captures)==k['capture_tree']
        assert sha(R/'commands'/phase/'physical.json')==k['job_file']
    qualification('seed-repeat1',read(R/'commands/seed-repeat1/products.json'),R/'states/seed',targets)
    for color in ('seed','observer','composed'):
        state=R/'states'/color
        if color!='seed':
            floor(true_seed['unique_file_bytes']+6*2**30);assert not state.exists()
            subprocess.run(['cp','-a','--reflink=never','--',n.seed,state],check=True)
            assert g.tree(state)==true_seed
            ids={(s.st_dev,s.st_ino) for f in state.rglob('*') if f.is_file() and not f.is_symlink() and (s:=f.stat())}
            for other in [n.seed,*(q for q in (R/'states').iterdir() if q!=state)]:
                assert not any((s.st_dev,s.st_ino) in ids for f in other.rglob('*') if f.is_file() and not f.is_symlink() and (s:=f.stat()))
        todo=['seed-repeat2'] if color=='seed' else ['selected-'+color,'repeat-'+color]
        for phase in todo:
            floor(6*2**30);directory=R/'commands'/phase;(R/'captures'/phase).mkdir()
            role='observer' if color=='seed' else color
            def inv(st,arm,ed,out):
                ns,env,h=base(st,arm,ed,out);ns,env=attach(ns,env,out,stock,phase);return ns,env,h
            n.invocation=inv
            try:product=n.build(state,role,n.excluded if color=='seed' else n.selected,color!='seed',directory,True)
            finally:n.invocation=base
            qualification(phase,product,state,targets)
    assert g.tree(n.seed)==true_seed
    verify() # Original published v1 independent protocol for all 299 occurrences.


if __name__=='__main__':
    with (P/'combined-native-measure.lock').open('r') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:run()
        except BaseException:
            (R/'continuation-failure.txt').write_text(traceback.format_exc());raise
