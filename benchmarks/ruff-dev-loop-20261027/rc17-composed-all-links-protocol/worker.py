"""Clone authenticated states and collect a fresh, untimed native cohort on H5."""
import collections
import fcntl
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wild import R, STOCK, WILD, digest, read, sha, write

P = R.parent
W = P/'ruff-evaluation-v2'
SOURCE = R/'source'
K = P/'protocol-v3'
G = P/'wall-protocol-v2'
F = P/'early-scheduler-wall-rc17-v2/02-2-B'
PHASES = ('seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed')
HIST = {'seed-repeat1':(48,48),'seed-repeat2':(48,48),'selected-observer':(51,50),
        'repeat-observer':(50,50),'selected-composed':(50,50),'repeat-composed':(50,50)}
SRC = 'e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11'
NREF = 'a75e5f17c07081cfcc9fabfcccd7a5022528641b'
ROLES = ('observer','composed')


def load(f):
    spec = importlib.util.spec_from_file_location(f.stem, f)
    m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def floor(nbytes=0):
    assert shutil.disk_usage(P).free > 38*2**30 + nbytes, 'storage reserve'


def role_kind(jobs, target):
    full = [j for j in jobs if j['kind']=='full' and Path(target).parent==Path(j['argv'][j['argv'].index('--out-dir')+1])
            and Path(target).name.startswith(j['target']+'-')]
    cut = [j for j in jobs if j['kind']=='link-only' and target+'.rlink' in j['argv']]
    assert bool(full) != bool(cut), (target,len(full),len(cut))
    return 'full' if full else 'link-only'


def relative(target):
    return str(Path(target).relative_to(W/'canonical'))


def jobs_for(phase):
    return read(W/phase/'physical.json')


def original():
    ledger={};allkeys=set()
    for tag in PHASES:
        jobs=jobs_for(tag)
        assert all(j['exit']==0 for j in jobs)
        links=[dict(target=relative(j['target']),kind=role_kind(jobs,j['target']),exec_sha256=j['raw'],
                    argv_sha256=digest(j['argv']),exit=j['exit']) for j in jobs if j['kind']=='wild']
        assert (len(links),len({j['target'] for j in links}))==HIST[tag]
        ledger[tag]=links
        allkeys.update(j['target'] for j in links)
    assert len(allkeys)==50 and all(j['target'] in allkeys for rows in ledger.values() for j in rows)
    return ledger


def attach(ns, env, receipt, stock, phase, extra=()):
    pos=ns.index('--chdir')
    ns[pos:pos]=['--bind',str(R),str(R),*extra,'--ro-bind',str(R/'wild-wrapper'),str(stock)]
    env['WILD_PHASE']=phase
    assert not set(env)&{'RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','LD_PRELOAD','RAYON_NUM_THREADS','WILD_EXPERIMENT'}
    return ns,env


def past_wild(phase):
    return collections.Counter((j['target'],j['kind']) for j in original()[phase])


def direct(n, stock, phase, target, expected):
    floor(6*2**30)
    (R/'captures'/phase).mkdir()
    d=R/'commands'/phase;d.mkdir()
    (d/'trace').mkdir()
    state=F/'private-state'
    rows=read(F/'unchanged/physical.json')
    job,=[j for j in rows if j['kind']=='link-only' and target+'.rlink' in j['argv']]
    rec=Path(target+'.rlink')
    src=n.actual(str(rec.parent),state);before=sha(src/rec.name)
    assert before==expected['recipe']['rlink']
    subprocess.run(['cp','-a','--reflink=auto','--',src,d/'private-out'],check=True)
    assert sha(d/'private-out'/rec.name)==before
    tmp=d/'tmp';tmp.mkdir()
    ns,env,_=n.invocation(state,'observer',True,d)
    for i,v in enumerate(ns):
        if v=='--bind' and Path(ns[i+1]).is_relative_to(state):ns[i]='--ro-bind'
    ns,env=attach(ns,env,d,stock,phase,['--bind',str(d/'private-out'),str(rec.parent),'--bind',str(tmp),str(n.can/'tmp')])
    with (d/'stdout').open('xb') as so, (d/'stderr').open('xb') as se:
        result=subprocess.run([*ns,'strace','-ff','-q','-s','1048576','-e','trace=execve','-o',d/'trace/exec',*job['argv']],
                              env=env,stdout=so,stderr=se,timeout=1200)
    assert result.returncode==0
    rows=n.trace_jobs(d/'trace')
    assert collections.Counter(j['kind'] for j in rows)=={'wild':1,'link-only':1} and all(j['exit']==0 for j in rows)
    write(d/'physical.json',rows)
    assert sha(src/rec.name)==before
    cube,=(R/'captures'/phase).iterdir();capture=read(cube/'capture.json')
    vals={x['plain_sha256'] for x in capture['widths']}
    assert capture['target']==target and read(SOURCE/'failed-native-fields.json')['fields'][Path(target).name]['failed-unchanged']['sha256'] in vals
    write(d/'gate.json',{'job_source':job['raw'],'rlink_sha256':before,'rlink_bytes':(src/rec.name).stat().st_size,
                         'kind':'separate native reconstruction from immutable failed rlink','raw':sorted(vals)})


def init():
    assert socket.gethostname()=='charlie-ohm-c5-check-1025' and Path(__file__).resolve().parent==SOURCE
    os.sched_setaffinity(0,set(range(16)))
    check=read(R/'registration.json')
    assert check['protocol']==sha(SOURCE/'SHA256SUMS') and len(check['commit'])==40
    for line in (SOURCE/'SHA256SUMS').read_text().splitlines():
        h,name=line.split('  ',1);assert sha(SOURCE/name)==h
    assert sha(K/'ruff_worker.py')=='9c2e4138072679b8ffff20d417fffad8f6bcd3cba1b0dd15309e2d935cbc0813'
    sys.path.insert(0,str(G))
    n=load(K/'ruff_worker.py');g=load(G/'guards.py');n.source()
    stock=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    assert sha(stock)==WILD and sha(G/'elf.py')==read(SOURCE/'failed-native-fields.json')['native_verifier_sha256']
    for name in ['captures','bodies','targets','commands','gates','states']:(R/name).mkdir()
    for k in range(3):(R/'gates'/str(k)).touch(exist_ok=False)
    shutil.copy2(stock,STOCK);assert sha(STOCK)==WILD
    wrapper=R/'wild-wrapper';wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 -IB '+str(SOURCE/'wild.py')+' "$0" "$@"\n');wrapper.chmod(0o700)
    hist=original();write(R/'historical.json',hist)
    targets=sorted({str(n.can/j['target']) for v in hist.values() for j in v})
    assert len(targets)==50
    write(R/'targets.json',targets)
    write(R/'qualification-source.json',{'native':sha(K/'ruff_worker.py'),'elf':sha(G/'elf.py'),'wild':sha(STOCK),
                 'past':{t:sha(W/t/'physical.json') for t in PHASES},'sdk':read(P/'sdk.json')['tools'],
                 'source':read(P/'ruff.json')['pin'],'cargo':{r:n.sealed_file(r)[1] for r in ROLES}})
    failed=read(SOURCE/'failed-native-fields.json')
    for ix,name in enumerate(sorted(failed['fields'])):
        choice,=[k for k in targets if k.endswith('/'+name)]
        direct(n,stock,'failure-'+str(ix+1),choice,failed['actual_bound_recipe'][name]['failed-unchanged'])
        print('failed raw replayed',name,flush=True)
    seed=g.tree(n.seed)
    assert seed==read(P/'early-scheduler-wall-admission-v2.json')['seed']
    # Each independent branch starts from the same released physical state. The
    # pristine seeds, failed state, first archived files and prior outputs are read only.
    write(R/'seed.json',seed)
    base_inv=n.invocation
    colors=['seed','observer','composed']
    for color in colors:
        floor(seed['unique_file_bytes']+6*2**30)
        state=R/'states'/color
        subprocess.run(['cp','-a','--reflink=never','--',n.seed,state],check=True)
        assert g.tree(state)==seed
        for d in ['seed','observer','composed']:
            other=n.seed if d=='seed' else R/'states'/d
            if other.is_dir() and other!=state:
                a={(s.st_dev,s.st_ino) for f in state.rglob('*') if f.is_file() and not f.is_symlink() and (s:=f.stat())}
                assert not any((s.st_dev,s.st_ino) in a for f in other.rglob('*') if f.is_file() and not f.is_symlink() and (s:=f.stat()))
        phases=[p for p in PHASES if (p.startswith('seed') if color=='seed' else p.endswith(color))]
        assert len(phases)==2
        for phase in phases:
            floor(6*2**30)
            d=R/'commands'/phase;(R/'captures'/phase).mkdir()
            role='observer' if color=='seed' else color
            def inv(st, arm, ed, out):
                ns,env,h=base_inv(st,arm,ed,out);ns,env=attach(ns,env,out,stock,phase);return ns,env,h
            n.invocation=inv
            try: product=n.build(state,role,n.excluded if color=='seed' else n.selected,color!='seed',d,True)
            finally:n.invocation=base_inv
            assert product==read(d/'products.json')
            old=read(W/phase/'products.json')
            for key in ['fresh','units','counts','roster','diagnostics','exes','e2e','ty_server']:assert product[key]==old[key],(phase,key)
            if color=='seed':
                original_registry=read(d/'registry-native.json')
                assert len(original_registry)==78 and all(old['native'][key]==h for key,h in original_registry.items())
                assert set(product['native'])==set(old['native'])-set(original_registry)
            else:assert set(product['native'])==set(old['native'])
            for key in set(product['native'])-set(targets):assert product['native'][key]==old['native'][key]
            if color!='seed':
                assert read(d/'registry-native.json')==read(W/phase/'registry-native.json')
                assert sha(d/'e2e-list')==sha(W/phase/'e2e-list')
            count=len(list((R/'captures'/phase).glob('*/capture.json')));assert count==HIST[phase][0]
            print('qualified command',phase,count,flush=True)
    assert g.tree(n.seed)==seed


if __name__=='__main__':
    with (P/'combined-native-measure.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:init()
        except BaseException:
            (R/'failure.txt').write_text(traceback.format_exc());raise
