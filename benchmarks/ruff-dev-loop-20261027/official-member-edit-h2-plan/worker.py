"""Verify both release installations on a real Ruff edit, then time the frozen unchanged builds."""
from pathlib import Path
import fcntl,hashlib,importlib.util,json,mmap,os,shutil,socket,subprocess,sys,tempfile,traceback,zipfile
k=Path(__file__).resolve().parent
r=k.parent/'published-r16-r17-member-target-space-h2-v2'
sys.path.insert(0,str(k))
spec=importlib.util.spec_from_file_location('released_member_control',r/'worker.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from analysis import analyze
from member_archive import witness
q=m.q
J=lambda f:json.loads(f.read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
P=lambda f,v:f.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
TT=m.T
O=k.parent/'official-member-edit-h2-output-v1'
dyn=m.q.WT/'crates/ty_vendored/vendor/typeshed'/m.STUB
plan=J(k/'plan.json')
argv=['cargo','+ohm','build','--locked','--offline','-j4']
def run(args,env):
    return subprocess.run(args,cwd=m.MEMBER,env=env,stdin=subprocess.DEVNULL,capture_output=True)
def stats(names):
    return {n:[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns] for n in names for s in [(m.TARGET/n).stat()]}
def digests(names):
    raw={n:q.sha(m.TARGET/n) for n in names}
    records={n:witness(m.TARGET/n) for n in names if n.endswith('.rlib')}
    assert all(raw[n]==desc['raw'] for n,desc in records.items())
    return raw,{n:records[n]['typed'] if n in records else v for n,v in raw.items()},records

def inside(ver,stage,action,record):
    q.T=m.C;env=q.environment();env['CARGO_TARGET_DIR']=str(m.TARGET)
    data=(k/('stub-'+stage+'.pyi')).read_bytes();assert dyn.read_bytes()==data and str(q.WT).find(' ')<0
    golden=J(r/('observations-'+ver)/'complete.json');end=golden['cold_and_three_unchanged'][-1]
    d=Path(record);d.mkdir(parents=True)
    orig_names=end['products'].keys();assert len(orig_names)==5
    if action=='binding':
        driver,=(m.SDK/'lib').glob('librustc_driver-*.so')
        files={'cargo':m.SDK/'bin/cargo','rustc':m.SDK/'bin/rustc','driver':driver,'wild':m.SDK/m.WILD}
        assert {n:q.sha(f) for n,f in files.items()}==golden['tool']
        assert run(['rustc','+ohm','--print','sysroot'],env).stdout.decode().strip()==str(m.SDK)
        P(d/'bound.json',dict(tool=golden['tool'],archive=golden['archive'],roster=end['roster'],native_gold=golden['cold_and_three_unchanged'][-1]['products']));return
    before=stats(orig_names)
    if action=='score':
        timings={}
        for phase in ('edit','repeat'):
            dot=d/phase;dot.mkdir()
            if phase=='repeat':prior=stats(orig_names)
            proc=run(['/usr/bin/python3','-B',str(k/'member_clock.py'),str(dot)],env)
            assert proc.returncode==0 and not proc.stdout and not proc.stderr,(phase,proc.returncode,proc.stderr[-500:])
            clock=J(dot/'clock.json');assert clock['argv']==argv and clock['ns']==clock['stop']-clock['start']>0 and clock['code']==0
            assert not (dot/'stdout').read_bytes() and b'Finished' in (dot/'stderr').read_bytes() and b'Blocking waiting' not in (dot/'stderr').read_bytes()
            timings[phase]=clock['ns']
        later=stats(orig_names)
        if ver=='17':assert prior==later
        P(d/'repeat-stats.json',dict(before=prior,after=later))
        P(d/'pair-clocks.json',timings)
        dirty=None
    else:
        (d/'trace').mkdir()
        trace=['strace','-q','-ff','-ttt','-s','1048576','-e','trace=execve,execveat','-e','signal=SIGCHLD','-o',str(d/'trace/exec')]
        q.watch([*trace,*argv,'--message-format=json'],m.MEMBER,env,d)
        rows=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()]
        assert rows[-1]=={'reason':'build-finished','success':True} and b'Blocking waiting' not in (d/'stderr').read_bytes()
        arts=[v for v in rows if v['reason']=='compiler-artifact']
        cols=('package_id','manifest_path','target','profile','features','filenames','executable')
        assert len(arts)==304 and not any(v['profile']['test'] for v in arts)
        roster=sorted(json.dumps({key:v[key] for key in cols},sort_keys=True) for v in arts)
        assert q.digest(roster)==end['roster'] and q.digest([v for v in rows if v['reason']=='compiler-message'])==end['diagnostics']
        p=q.processes(d,m.SDK,set());jobs=sorted((v[1],v[2]) for v in p['jobs'])
        if action!='prime':
            work=action=='edit' or ver=='16'
            assert jobs==([('ty_vendored','full'),('ty_wasm','full')] if work else []) and p['counts']['wild']==int(work)
            assert p['counts']['queries']==p['counts']['system']==0 and sum(not v['fresh'] for v in arts)==(6 if work else 0)
        dirty=sorted(v['target']['name'] for v in arts if not v['fresh'])
    after=stats(orig_names);raw,typed,archives=digests(orig_names)
    gold_template=J(k/'bound-states.json')['zips'][ver] if (k/'bound-states.json').is_file() else None
    source_root=O/'zips'/ver
    if source_root.is_file():
        archive=m.C/source_root.read_text().strip()
    else:
        archive,=[f for root in (m.C/'shared',m.TARGET) for f in root.rglob('zipped_typeshed.zip')]
        source_root.parent.mkdir(exist_ok=True);source_root.write_text(str(archive.relative_to(m.C)))
    if gold_template is not None:assert archive.relative_to(m.C).as_posix()==gold_template
    z=archive.read_bytes()
    with zipfile.ZipFile(archive) as zipin:assert m.read_stub(zipin,m.STUB)==data
    offsets={}
    for n in orig_names:
        if 'libty_vendored-' not in Path(n).name:continue
        with (m.TARGET/n).open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapped:
            pos=mapped.find(z);assert pos>=0;offsets[n]=pos
    assert len(offsets)==2
    native_search=m.search_args(r/('observations-'+ver)/'phase-0',J(r/('observations-'+ver)/'phase-0/native-processes.json'))
    assert len(native_search)==420
    with tempfile.TemporaryDirectory(dir=m.C/'tmp') as scratch:
        td=Path(scratch)
        caller=m.real_caller('ty_wasm',td,lambda args,dot:run(args,env),m.TARGET,raw,native_search,(k/'reader.rs').read_bytes(),data)
        for f in td.glob('reader.*'):
            if f.is_file():shutil.copy2(f,d/f.name)
    assert caller['sha256']==sha(data) and caller['search_dirs']==210 and not (d/'reader.stderr').read_bytes()
    if stage=='original':
        assert raw['debug/libty_wasm.so']==end['products']['debug/libty_wasm.so']
        assert sha(z)==end['compressed_zip']['sha256']
    if action!='prime':
        bound=J(k/'bound-states.json')['contracts'][ver][stage]
        assert typed==bound['typed'] and sha(z)==bound['zip'] and caller['sha256']==bound['stub']
    P(d/'archives.json',archives)
    P(d/'product.json',dict(release=ver,stage=stage,action=action,raw=raw,typed=typed,zip=sha(z),offsets=offsets,stub=sha(data),caller=caller,dirty=dirty,before=before,after=after))

def outside(mode):
    assert socket.gethostname()=='charlie-ohm-relink-b-1024'
    inputs=J(k/'inputs.json');assert inputs['archives']==plan['releases']==m.ARCH
    assert q.validate_source()['commit']==plan['source'] and dyn.read_bytes()==(k/'stub-original.pyi').read_bytes()
    assert q.sha(r/'complete.json')==inputs['original_completion'] and q.sha(Path(inputs['rewarm_path']))==inputs['rewarm_sha']
    current=q.version_and_alias();q.capacity();os.sched_setaffinity(0,set(plan['affinity']))
    states={v:Path(x) for v,x in inputs['states'].items()};sdks={v:Path(x) for v,x in inputs['sdks'].items()}
    assert set(states)==set(sdks)=={'16','17'} and states['16'].stat().st_dev==states['17'].stat().st_dev
    assert all(f.is_dir() and not f.is_symlink() for f in states.values())
    assert all(q.sha(r/n)==v for n,v in J(r/'source-files.json').items())
    assert q.sha(k/'SHA256SUMS')==inputs['plan_sha'] and q.sha(k/'worker.py')==inputs['worker']
    assert q.sha(k.parent/'official-member-wall-h2-output-v1/wall-complete.json')==plan['prior_completion']
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=k,check=True)
    def invoke(ver,tag,typ,stage='original'):
        q.capacity();stub=O/('stub-'+ver)
        if not stub.is_file() or stub.read_bytes()!=(k/('stub-'+stage+'.pyi')).read_bytes():
            stub.write_bytes((k/('stub-'+stage+'.pyi')).read_bytes())
        dd=O/tag
        call=['bwrap',*m.BASIC,'--bind',str(states[ver]),str(m.C),'--ro-bind',str(sdks[ver]),str(m.SDK),'--ro-bind',str(stub),str(dyn),'--bind',str(O),str(O),'--','/usr/bin/python3','-IB',str(k/'worker.py'),'in',ver,stage,typ,str(dd)]
        ret=subprocess.run(call,capture_output=True)
        if ret.returncode:
            (O/'inner-error.txt').write_bytes(ret.stderr[-5500:]);raise RuntimeError((tag,ret.returncode,ret.stderr[-1100:]))
        assert not ret.stdout and not ret.stderr,(tag,ret.stdout[-250:],ret.stderr[-250:]);q.capacity();return dd
    with (q.P/'native-measure.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert mode=='wall' and not O.exists();O.mkdir(mode=0o700)
        for v in ('16','17'):
            invoke(v,'preflight/'+v+'/bound','binding');invoke(v,'preflight/'+v+'/prime','prime')
            for tag,typ,stage in [('initial','repeat','original'),('changed','edit','reversed'),('changed-repeat','repeat','reversed'),('restored','edit','original'),('restored-repeat','repeat','original')]:
                invoke(v,'preflight/'+v+'/'+tag,typ,stage)
        ledger={key:[] for key in ('edit','first_unchanged','edit_plus_first')}
        for number,order in enumerate(plan['pair_order'],1):
            stage='reversed' if number%2 else 'original';times={}
            for v in order.split('-'):
                dot=invoke(v,'sample/'+str(number).zfill(2)+'-'+v,'score',stage);t=J(dot/'pair-clocks.json');times[v]=t
            for n,fun in [('edit',lambda a:a['edit']),('first_unchanged',lambda a:a['repeat']),('edit_plus_first',lambda a:a['edit']+a['repeat'])]:
                ledger[n].append(dict(order='BC' if order=='16-17' else 'CB',direction=stage,b=fun(times['16']),c=fun(times['17'])))
            P(O/'progress.json',dict(pairs=number))
        for v in ('16','17'):invoke(v,'final/'+v,'repeat')
        assert q.version_and_alias()==current and q.validate_source()['commit']==plan['source'] and dyn.read_bytes()==(k/'stub-original.pyi').read_bytes()
        q.capacity();P(O/'ledger.json',ledger);P(O/'result.json',analyze(plan,ledger));P(O/'complete.json',dict(commands=96,inputs=q.sha(k/'inputs.json')))

if __name__=='__main__':
    if sys.argv[1]=='in':inside(*sys.argv[2:])
    else:
        try:outside(sys.argv[1])
        except BaseException:
            if O.is_dir():(O/'failure.txt').write_text(traceback.format_exc())
            raise
