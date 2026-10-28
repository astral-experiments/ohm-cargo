"""Run an untimed ordinary admission, or a separately authorized complete H2 wall block."""
from pathlib import Path
import argparse
import fcntl
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import checks as g

R=Path('/dev/shm/ohm-text-size-first-selection-20261028')
LOCK=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-measure.lock')
SEED=R/'seed'
ADMIT=R/'wall-admission-v1'
RESULT=R/'wall-result-v1'
BIND=R/'wall-launch-v1'
FIELDS=('home','tmp','cargo','target','shared')


def native_worker():
    assert g.manifest(R/'protocol')==g.P['native_registration']['sha256']
    path=R/'protocol/worker.py';assert g.sha(path)==g.P['native_worker_sha256']
    spec=importlib.util.spec_from_file_location('frozen_package_worker',path)
    n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
    assert n.root==R and n.plan['command']==g.P['command'] and n.plan['cpus']==g.P['cpus']
    return n


def register():
    assert HERE==R/'wall-protocol-v1'
    reg=g.read(BIND/'registration.json')
    assert g.dig(g.read(HERE/'declared-native.json'))==g.P['declared_raw_sha256']
    assert set(reg)=={'wall_ref','wall_sha256','native_result_ref','native_result_sha256','native_plan_ref','native_plan_sha256'}
    assert reg['wall_sha256']==g.manifest(HERE) and g.REF.fullmatch(reg['wall_ref'])
    assert reg['native_result_ref']==g.P['native_result_ref'] and reg['native_result_sha256']==g.P['native_result_sha256']
    assert reg['native_plan_ref']==g.P['native_source_ref'] and reg['native_plan_sha256']==g.P['native_registration']['sha256']
    assert len({reg['wall_ref'],reg['native_plan_ref'],reg['native_result_ref']})==3
    assert g.sha(HERE/'ci-exact-heads.json')==g.P['ci_sha256']
    for path in (HERE/'ci-exact-heads.json',BIND/'ci-current.json'):
        g.ci(g.read(path))
    return reg


def sdk_and_source(n):
    assert n.git('rev-parse','HEAD').decode().strip()==g.P['ruff']
    assert n.git('rev-parse','HEAD^{tree}').decode().strip()==g.P['tree']
    n.git('diff','--quiet','HEAD','--')
    assert not n.git('ls-files','--others','--exclude-standard'), 'unexpected untracked Ruff source'
    assert all(g.sha(path)==g.P['after'] for path in (n.src/n.plan['path'],n.protocol/'after-range.rs',R/'active-range.rs'))
    assert (R/'rustup/toolchains/ohm').resolve()==n.sdk.resolve()
    pairs={'rustc':n.sdk/'bin/rustc','cargo':n.sdk/'bin/cargo','wild':n.linker}
    pairs['driver'],=n.sdk.glob('lib/librustc_driver-*.so')
    sdk={name:g.sha(f) for name,f in pairs.items()}
    arms={a:g.sha(R/(a+'-cargo')) for a in 'BC'}
    assert sdk==g.P['sdk'] and arms==g.P['cargo']
    assert g.read(R/'plan-registration.json')==g.P['native_registration']
    assert (R/'native.exit').read_text()=='0' and not (R/'native-failure.txt').exists()
    sdk_tree,_=g.tree(n.sdk)
    return dict(sdk=sdk,arms=arms,sdk_tree=sdk_tree,source=g.P['tree'],edited=g.P['after'],
                rustup=g.sha(Path(shutil.which('rustup')).resolve()))


def proc_memory():
    row={k:int(v.split()[0])*1024 for k,v in (l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())}
    counters={name:int(val) for name,val in (l.split() for l in Path('/proc/vmstat').read_text().splitlines()) if name in ('pswpin','pswpout')}
    return dict(available=row['MemAvailable'],tmpfs_free=shutil.disk_usage(R).free,
                swap_used=row['SwapTotal']-row['SwapFree'],counters=counters)


def capacity(copy_bytes=0):
    m=proc_memory()
    assert m['available']>g.P['minimum_ram_available']+copy_bytes
    assert m['tmpfs_free']>g.P['minimum_tmpfs_free']+copy_bytes+g.P['per_copy_extra_allowance']
    return m


def cpu_reading():
    lines=[s.split() for s in Path('/proc/stat').read_text().splitlines() if s.startswith('cpu')]
    return {key:list(map(int,nums[:8])) for key,*nums in lines if key in {'cpu'+str(i) for i in g.P['cpus']}}


def quiet_gate():
    cfg=g.P['quiet'];start=time.monotonic()
    attempts=0
    while True:
        attempts+=1
        before=cpu_reading();time.sleep(cfg['sample_seconds']);after=cpu_reading()
        assert len(before)==len(after)==8 and set(before)==set(after)
        dt={k:sum(after[k])-sum(before[k]) for k in before}
        idle={k:after[k][3]-before[k][3] for k in before}
        assert min(dt.values())>0
        per_cpu={k:idle[k]/dt[k] for k in before}
        idle_all=sum(idle.values())/sum(dt.values())
        if min(per_cpu.values())>=cfg['minimum_idle_each'] and idle_all>=cfg['minimum_idle_all']:
            return dict(attempts=attempts,average=idle_all,per_cpu=per_cpu)
        assert time.monotonic()-start<cfg['max_wait_seconds'],('busy before command',per_cpu,idle_all)


def live_namespace(n,state,arm,rec):
    ns,env=n.namespace(state,arm,rec)
    assert set(env)=={'PATH','HOME','CARGO_HOME','RUSTUP_HOME','RUSTUP_AUTO_INSTALL','CARGO_TARGET_DIR','CARGO_BUILD_BUILD_DIR',
                      'CARGO_NET_OFFLINE','CARGO_BUILD_JOBS','CARGO_TERM_COLOR','TMPDIR','LC_ALL','LANG'}
    assert env['CARGO_BUILD_JOBS']=='8' and env['CARGO_NET_OFFLINE']=='true'
    for path,expected in ((n.sdk/'bin/cargo',g.P['cargo'][arm]),(n.src/n.plan['path'],g.P['after'])):
        assert subprocess.check_output([*ns,'sha256sum',path],env=env,text=True).split()[0]==expected
    assert sorted(os.sched_getaffinity(0))==g.P['cpus']
    return ns,env


def anchor_native(n):
    assert g.read(R/'outcome.json')==g.A['outcome'] and g.A['outcome']['admitted'] is True
    assert {q.name for q in (R/'receipts').iterdir() if q.is_dir()}==set(g.A['receipts'])
    all_files=[];typed=None;model=None
    for phase,expected in sorted(g.A['receipts'].items()):
        rec=R/'receipts'/phase
        for name,sha in expected['files'].items():assert g.sha(rec/name)==sha,(phase,name)
        traces={f.name:g.sha(f) for f in (rec/'trace').glob('exec.*')}
        assert len(traces)==expected['trace_count'] and g.dig(traces)==expected['trace_sha256']
        if not phase[0].isdigit():continue
        i,arm,step=phase.split('-');assert n.plan['order'][int(i)-1]==arm
        current=g.events((rec/'cargo.stdout').read_bytes());g.compare_model(current,1 if step=='first' else 11)
        identity={k:current[k] for k in ('typed','roster','units','files','targets','diag')}
        if typed is None:typed=identity
        assert identity==typed
        g.listing(rec,current)
        jobs=n.jobs(rec/'trace',set(current['targets'].values()));assert jobs==g.read(rec/'jobs.json')
        if step=='repeat':
            assert not jobs
            inv=g.trace_inventory(rec/'trace',set(current['targets'].values()))
            assert not inv['tools'],('physical compiler/link invocation during the original fresh repeat',inv['tools'])
        else:
            assert g.read(rec/'products.json')['work']==({'full':14,'wild':10} if arm=='B' else {'full':10,'wild':6})
            state=R/f'state-{i}-{arm}'
            all_files.append(g.files(current,lambda name:n.host_path(name,state)))
            model=current
    assert len(all_files)==4
    for item in all_files:
        g.validate_files(item,all_files[0])
    assert (R/'receipts/after-build/api-run.stdout').read_bytes()==b'1..4\n'
    assert b'E0599' in (R/'receipts/before-build/api-rustc.stderr').read_bytes()
    return model,all_files[0]


def seed_check(n,model):
    assert {p.name for p in SEED.iterdir()}==set(FIELDS)
    assert not any(n.host_path(path,SEED).exists() for path in model['targets'].values())
    lib,=g.read(R/'receipts/settled-build/products.json')['library']
    assert n.host_path(lib,SEED).is_file()
    ref,_=g.tree(SEED)
    assert ref['unique_file_bytes']==g.P['native_seed_bytes']
    return dict(**ref,edited_library=g.sha(n.host_path(lib,SEED)),edited_library_path=g.path_id(lib))


def run_follow(n,state,arm,rec,model,files):
    rec.mkdir();(rec/'trace').mkdir()
    ns=live_namespace(n,state,arm,rec)
    trace=['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',rec/'trace/exec']
    cmd=[*trace,*g.P['command'],'--message-format=json']
    n.normal(ns,cmd,rec,'cargo')
    got=g.events((rec/'cargo.stdout').read_bytes());g.compare_model(got,11)
    assert all(got[k]==model[k] for k in ('typed','files','targets','diag'))
    selected=set(got['targets'].values())
    inventories=g.trace_inventory(rec/'trace',selected)
    g.save(rec/'inventory.json',inventories)
    g.save(rec/'jobs.json',n.jobs(rec/'trace',selected))
    assert not inventories['tools'] and not g.read(rec/'jobs.json')
    observed=g.files(got,lambda p:n.host_path(p,state));g.save(rec/'files.json',observed);g.validate_files(observed,files)
    list_all(n,ns,rec,got)
    return got,inventories


def list_all(n,ns,rec,model):
    for name,path in sorted(model['targets'].items()):
        n.normal(ns,[path,'--list'],rec,'list-'+name)
    return g.listing(rec,model)


def slot(n,root,model,files,seed,arm,block,slotnum,scored,admission_sha):
    out=root/f'{block:02d}-{slotnum}-{arm}';out.mkdir()
    state=out/'fresh-physical-copy'
    mem=capacity(seed['unique_file_bytes'])
    subprocess.run(['cp','-a','--reflink=never','--',SEED,state],check=True)
    actual,ids=g.tree(state)
    assert actual=={k:seed[k] for k in actual}
    # GNU cp must preserve hardlink groups internally and never share writable files with the parent.
    parent_ids={(s.st_dev,s.st_ino) for f in SEED.rglob('*') if not f.is_symlink() and f.is_file() and (s:=f.stat())}
    assert parent_ids.isdisjoint(ids) and len(ids)==len(parent_ids)==seed['unique_files']
    assert state.stat().st_dev==SEED.stat().st_dev and not any(n.host_path(p,state).exists() for p in model['targets'].values())
    rec=out/'ordinary';rec.mkdir()
    ns,env=live_namespace(n,state,arm,rec)
    readiness=quiet_gate()
    before=capacity()
    g.save(out/'start.json',dict(block=block,slot=slotnum,arm=arm,scored=scored,admission=admission_sha,
          cargo=g.P['cargo'][arm],seed=actual,independent_regular_files=len(ids),cpu=sorted(os.sched_getaffinity(0)),idle=readiness,
          free_before_copy=mem,free_before_command=before,copy='cp -a --reflink=never',seed_device=state.stat().st_dev))
    if scored:
        subprocess.run([*ns,'/usr/bin/python3','-IB',HERE/'clock.py',rec,*g.P['command']],env=env,check=True)
    else:
        with (rec/'stdout').open('xb') as so,(rec/'stderr').open('xb') as se:
            child=subprocess.run([*ns,*g.P['command']],env=env,stdout=so,stderr=se,stdin=subprocess.DEVNULL)
        g.save(rec/'unclocked-exit.json',{'command':g.P['command'],'exit':child.returncode})
        assert child.returncode==0
    after=capacity()
    assert after['counters']==before['counters'],('swap activity across selection',before,after)
    g.ordinary(rec,model)
    first=g.files(model,lambda name:n.host_path(name,state))
    g.save(rec/'files.json',first);g.validate_files(first,files)
    list_all(n,(ns,env),rec,model)
    follow,physical=run_follow(n,state,arm,out/'follow',model,files)
    g.save(out/'verified.json',dict(start=g.sha(out/'start.json'),ordinary_files=g.sha(rec/'files.json'),
               stdout=g.sha(rec/'stdout'),stderr=g.sha(rec/'stderr'),repeat_files=g.sha(out/'follow/files.json'),
               repeat_stdout=g.sha(out/'follow/cargo.stdout'),repeat_stderr=g.sha(out/'follow/cargo.stderr'),
               repeat_traces=g.sha(out/'follow/inventory.json'),repeat_typed=follow['typed'],
               repeat_fresh=follow['fresh'],repeat_tools=physical['tools'],swap_after=after['counters']))
    # Only the new, verified disposable slot may be freed. Every failed state stays intact.
    assert state.parent==out and state.name=='fresh-physical-copy' and state.is_dir() and not state.is_symlink()
    shutil.rmtree(state)

def operate(n,mode):
    from verify import verify_preflight, all_slots
    root=ADMIT if mode=='admit' else RESULT
    assert not root.exists()
    if mode=='admit':
        assert not RESULT.exists()
    else:
        assert (ADMIT/'admission.json').is_file() and not (ADMIT/'failure.txt').exists()
    root.mkdir()
    try:
        reg=register()
        g.save(root/'registration.json',reg);g.save(root/'ci-current.json',g.read(BIND/'ci-current.json'))
        subjects=sdk_and_source(n)
        assert subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',R],text=True).strip()=='tmpfs'
        model,reference=anchor_native(n);seed=seed_check(n,model)
        frozen=dict(model=model,files=reference,seed=seed,tools=subjects,ci=g.ci(g.read(BIND/'ci-current.json')),
                    native_outcome=g.sha(R/'outcome.json'),state_fs='tmpfs',cpu=sorted(os.sched_getaffinity(0)))
        if mode=='admit':
            g.save(root/'frozen.json',frozen)
            for slotnum,arm in enumerate(g.P['unscored_preflight_order'],1):
                slot(n,root,model,reference,seed,arm,0,slotnum,False,None)
            assert seed_check(n,model)==seed and sdk_and_source(n)==subjects
            g.save(root/'post-condition.json',{'seed':seed,'tools':subjects,'unscored':True,'clocks':0})
            g.save(root/'admission.json',verify_preflight(root))
        else:
            admission=g.read(ADMIT/'admission.json')
            assert admission==verify_preflight(ADMIT) and g.read(ADMIT/'frozen.json')==frozen
            assert g.read(ADMIT/'registration.json')==reg and g.read(ADMIT/'ci-current.json')==g.read(BIND/'ci-current.json')
            grant=g.read(BIND/'grant.json');admission_sha=g.sha(ADMIT/'admission.json')
            g.grant_valid(reg,grant,admission_sha);g.save(root/'grant.json',grant)
            for block,order in enumerate(g.P['order'],1):
                for slotnum,arm in enumerate(order,1):
                    slot(n,root,model,reference,seed,arm,block,slotnum,True,admission_sha)
            assert seed_check(n,model)==seed and sdk_and_source(n)==subjects
            g.save(root/'terminal.json',dict(phase='all_slots_finished',slots=48,admission=admission_sha,
                       grant=g.sha(root/'grant.json'),seed=seed,tools=subjects))
            g.save(root/'result.json',all_slots(root,ADMIT))
    except BaseException:
        (root/'failure.txt').write_text(traceback.format_exc())
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['admit','score'])
    arg=parser.parse_args()
    assert socket.gethostname()==g.P['host']
    with LOCK.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        os.sched_setaffinity(0,set(g.P['cpus']))
        assert not sys.flags.optimize
        operate(native_worker(),arg.mode)
