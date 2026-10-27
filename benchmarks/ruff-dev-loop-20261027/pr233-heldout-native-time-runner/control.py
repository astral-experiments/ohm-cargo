"""Take the exclusive native lane and run every registered Ruff transition in its fixed order."""
from pathlib import Path
import collections, fcntl, json, os, shutil, signal, subprocess, sys, time, traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import ARENA, BASE, BOUND, HERE, ORIGIN, P, PLAN, PLAN_SHA, PREREG, RELEASE, SOURCE, capacity, load, need, dump, sha, validate_host, verify_origin
from novel_state import set_source, source_binds, verify_input
from namespace import skeleton, spawn_args
from state import source_clean

def atomic_json(path, value):
    tmp=path.with_suffix('.partial')
    dump(tmp,value)
    tmp.replace(path)

def run(argv):
    capacity()
    p=subprocess.Popen(argv,start_new_session=True)
    try:
        while True:
            try:
                rc=p.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                capacity()
        need(rc==0,('nonzero child',rc,[str(v) for v in argv[-7:]]))
        capacity()
    except BaseException:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        raise

def original(mode,arm):return ORIGIN/'state'/mode/arm
def state(mode,arm):return ARENA/'state'/mode/arm

def idle():
    mine=os.getpid()
    # Verify process CPU use on the timed CPUs over a real admission window. Short
    # processes in other sessions, including rustc/ld/workers, also fail if sampled.
    def sample():
        result={}
        for q in Path('/proc').iterdir():
            if not q.name.isdecimal():continue
            pid=int(q.name)
            try:
                line=(q/'stat').read_text();p=line.rindex(')');fields=line[p+2:].split()
                if pid==mine or fields[0] in ('Z','I') or not (q/'cmdline').read_bytes():continue
                if not (set(os.sched_getaffinity(pid)) & set(range(24))):continue
                result[pid]=[int(fields[11])+int(fields[12]),line[line.index('(')+1:p]]
            except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        return result
    before=sample();t=time.monotonic();time.sleep(4);after=sample();duration=time.monotonic()-t
    busy={p:[name,round((ticks-before[p][0])/os.sysconf('SC_CLK_TCK')/duration,3)] for p,(ticks,name) in after.items() if p in before and (ticks-before[p][0])> duration*0.10*os.sysconf('SC_CLK_TCK')}
    comp=[(p,name) for p,(_,name) in {**before,**after}.items() if name in ('rustc','cargo','cc1','cc1plus','collect2','ld.bfd','wild','rust-lld')]
    need(not busy and not comp,('competing work on timing CPUs',busy,comp))
    return {'sampling_seconds':duration,'busy':busy,'compilers':comp,'affinity':sorted(os.sched_getaffinity(0))}

def clone_states():
    need(not ARENA.exists(),'refusing previous timing arena');ARENA.mkdir(mode=0o700)
    refs=verify_origin();dump(ARENA/'references.json',refs)
    footprint=int(subprocess.check_output(['du','-s','-B1',str(ORIGIN/'state')]).split()[0])
    need(capacity()[str(P)]>footprint+25*2**30,('disk for independent copies',footprint))
    copied={}
    for mode in ('build','test'):
        (ARENA/'state'/mode).mkdir(parents=True)
        for arm in 'BC':
            src=original(mode,arm);dst=state(mode,arm)
            need(not dst.exists() and src.stat().st_dev!=ARENA.stat().st_dev,('cross-volume clone',src,dst))
            run(['cp','-a','--reflink=auto','--',src,dst])
            for rel in ('target','shared','registry-home','rustup','inputs','source-state'):
                p,q=src/rel,dst/rel
                need(q.exists() and p.stat().st_dev!=q.stat().st_dev and not p.samefile(q),('physical separation',p,q))
            need((dst/'rustup/toolchains/ohm').resolve()==(src/'rustup/toolchains/ohm').resolve(),'same rustup selector')
            escape=[]
            for base,dirs,files in os.walk(dst,followlinks=False):
                for n in [*dirs,*files]:
                    f=Path(base)/n
                    if f.is_symlink() and f.resolve().is_relative_to(ORIGIN):escape.append(str(f))
            need(not escape,('writable original-state aliases',escape[:10]))
            verify_input('original',dst/'inputs',load(ORIGIN/'fixture/manifest.json'))
            copied[mode+'/'+arm]={'parent_dev':src.stat().st_dev,'copy_dev':dst.stat().st_dev,'parent_inode':src.stat().st_ino,'copy_inode':dst.stat().st_ino}
    dum={'preregistered':PREREG,'time_plan':PLAN_SHA,'subject_manifest':sha(ORIGIN/'complete.json'),'fixture_manifest':sha(ORIGIN/'fixture/manifest.json'),'native_reference_sha256':sha(ARENA/'references.json'),'store_bytes':footprint,'copies':copied}
    dump(ARENA/'copied.json',dum)
    return skeleton(ARENA)

def namespace_again():
    # Namespaces themselves are new for each command. Reuse the same sealed mount
    # argument list, preserving physical copies and all canonical Cargo paths.
    mounts=load(ARENA/'mounts.json')
    need(mounts[:3]==['bwrap','--ro-bind',str(ARENA/'secure-root')], 'prepared private root')
    return mounts

def call(mount,mode,arm,edit,direction,phase,name):
    st=state(mode,arm);tag=edit if direction=='edit' else 'original'
    if phase=='settle':tag='original'
    set_source(st,ORIGIN/'fixture',tag)
    ref='original-baseline' if phase=='settle' else edit+'-'+direction
    a=BOUND['arms'][arm];args=spawn_args(mount,ARENA,st,st/'registry-home',[],Path(a['cargo']),Path(a['driver']));i=args.index('--')
    run([*args[:i],*source_binds(st),*args[i:],sys.executable,'-B',HERE/'worker.py',mode,arm,tag,ref,phase,name])
    f=ARENA/'receipts'/name/'witness.json'
    return load(f),sha(f)

def controls(mount,phase):
    out={}
    for ep in PLAN['endpoints']:
        mode,edit=ep['mode'],ep['edit']
        for direction in ('edit','restore'):
            for arm in 'BC':
                name='/'.join((phase,mode,edit,direction,arm))
                r,sm=call(mount,mode,arm,edit,direction,phase,name)
                out[name]=dict(proof_sha256=sm,first_native=r['first']['native'],immediate_native=r['immediate']['native'],structure=r['first']['structure'])
            print(phase,mode,edit,direction,'both native/CLI/fresh passed',flush=True)
    need(len(out)==24,'24 native controls')
    return out

def prepared(mount):
    settling={}
    for mode in ('build','test'):
        for arm in 'BC':
            seq=[]
            for index in range(3):
                name='/'.join(('settle',mode,arm,str(index)))
                r,digest=call(mount,mode,arm,'original','restore','settle',name);w=r['first']
                hit=not w['dirty'] and not w['native']['jobs'] and not any(w['native']['native'].values());seq.append([digest,hit])
                if hit:break
            need(hit,('clone never settled',mode,arm,seq))
            settling[mode+'/'+arm]=seq
    raw=controls(mount,'pre')
    need(source_clean()==BOUND['host']['source_index_sha256'],'source index changed')
    dump(ARENA/'prepared.json',{'plan':PLAN_SHA,'copied':sha(ARENA/'copied.json'),'references':sha(ARENA/'references.json'),'mounts':sha(ARENA/'mounts.json'),'settling':settling,'pre_controls':raw,'clocked_observations':0,'remaining':capacity()})

def score(mount,quiet):
    need(not (ARENA/'started.json').exists(),'refusing to resume or repeat a scored family')
    seal=load(RELEASE/'score.json')
    need(seal=={'runner_sha256':sha(HERE/'SHA256SUMS'),'plan_sha256':PLAN_SHA,'prepared_sha256':sha(ARENA/'prepared.json'),'cpu_lane_clear':True},'independent scoring release')
    pre=load(ARENA/'prepared.json')
    need(pre['plan']==PLAN_SHA and len(pre['pre_controls'])==24 and pre['clocked_observations']==0 and pre['references']==sha(ARENA/'references.json') and pre['mounts']==sha(ARENA/'mounts.json'),'admission receipts')
    for m in ('build','test'):
        for a in 'BC':need((state(m,a)/'source-state').read_text()=='original',('unexpected initial view',m,a))
    dump(ARENA/'started.json',{'admission':quiet,'scoring_release':seal,'available':capacity()})
    observations=[]
    for i,s in enumerate(PLAN['sequence']):
        times={};proofs={}
        for a in s['arms']:
            name=f"timed/{i+1:03d}/{a}"
            rec,proofs[a]=call(mount,s['mode'],a,s['edit'],s['direction'],'timed',name)
            times[a]=rec['first']['elapsed_ns'];need(times[a]>0,'clock')
        observations.append(dict(s,elapsed_ns=times,proofs=proofs))
        atomic_json(ARENA/'observations.json',observations)
        print('pair',i+1,'of',len(PLAN['sequence']),s['mode'],s['edit'],s['direction'],'validated',flush=True)
    raw=controls(mount,'post')
    dump(ARENA/'post-controls.json',raw)
    need(source_clean()==BOUND['host']['source_index_sha256'],'unbound Ruff worktree or index changed')
    from time_analyze import analyze
    data=analyze(PLAN,observations);dump(ARENA/'results.json',data)
    dump(ARENA/'complete.json',{'pairs':len(observations),'ordinary_timed_commands':len(observations)*2,'observations_sha256':sha(ARENA/'observations.json'),'results_sha256':sha(ARENA/'results.json'),'pre_sha256':sha(ARENA/'prepared.json'),'post_sha256':sha(ARENA/'post-controls.json'),'real_source_index':source_clean(),'capacity':capacity()})

if __name__=='__main__':
    phase,=sys.argv[1:]
    need(phase in ('prepare','score'),'valid phase');validate_host()
    with (P/'native-measure.lock').open('r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        admission=idle()
        try:
            if phase=='prepare':
                mount=clone_states();dump(ARENA/'mounts.json',mount);dump(ARENA/'prepare-admission.json',admission)
                prepared(mount)
            else:score(namespace_again(),admission)
        except BaseException:
            if ARENA.is_dir():(ARENA/(phase+'-failure.txt')).write_text(traceback.format_exc())
            raise
