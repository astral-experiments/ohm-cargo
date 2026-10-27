"""Paired Ruff check episodes. The native timer wraps only actual Cargo execution."""
from pathlib import Path
import collections, fcntl, hashlib, json, os, shutil, signal, subprocess, sys, time, traceback, zipfile

HERE = Path(__file__).resolve().parent
X = Path.home()/'.cache/ohm-233-position-qualified-20261027'
PRODUCT = X/'build-script-cargo-release-v1/packaged-v5'
Q = X/'build-script-generation-timing-v1'
RAM = Path('/dev/shm/ohm-build-script-generation-timing-v1')
DONOR = X/'cfg-library-first-v1-campaign/state/check'
sys.path[:0] = [str(X/'first-occurrence-worker-v2'), str(X/'nonparser-whole-inputs-impl-v1')]
from common import P, RUFF, FROZEN, CARGO_HOME, SONAME, TARGET, env, git, load, dump, sha
from namespace import skeleton, spawn_args
from process_scan import parse

PLAN = load(HERE/'plan.json')
ORDER = load(HERE/'order.json')
PRIMARY = PLAN['primary_source']
HOLDOUT = load(HERE/'holdout.json')
DRIVER = X/'drivers'/('driver-'+PLAN['fixed_rustc_driver'])
ROOT_CRATES = {Path(f).parts[1] for f in PRIMARY['files']}
CMD = PLAN['command']
GIB = 2**30

def available():
    return {'home':shutil.disk_usage(X).free, 'ram':shutil.disk_usage(RAM.parent).free}

def floor(extra=0):
    values=available()
    assert values['home'] >= 25*GIB and values['ram'] >= 10*GIB+extra, (extra,values)
    return values

def copy_state(src,dst):
    assert not dst.exists()
    dst.parent.mkdir(parents=True,exist_ok=True)
    size=int(subprocess.check_output(['du','-sb',src]).split()[0])
    floor(size+GIB//4)
    subprocess.run(['cp','-a','--reflink=auto','--',src,dst],check=True)
    for part in ('target','shared','registry-home','rustup'):
        assert (src/part).is_dir() and not (src/part).samefile(dst/part), (src,dst,part)
    floor()

def initialize_sources():
    for kind,selection,patch in [('main',PRIMARY,'main.patch'),('holdout',HOLDOUT,'pydantic.patch')]:
        for view in ('original','edited'):
            dest=Q/'fixture'/kind/view
            for f in selection['files']:
                dst=dest/f; dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(RUFF/f,dst)
            if view=='edited':
                subprocess.run(['git','apply','-R','--no-index','--whitespace=nowarn',HERE/patch],cwd=dest,check=True)
            check_source(dest,selection,view)

def check_source(where,selection,view):
    values={f:sha(where/f) for f in selection['files']}
    assert all(value==selection['files'][f][view+'_sha256'] for f,value in values.items()),(view,values)
    return values

def change(physical,kind,view):
    selection=PRIMARY if kind=='main' else HOLDOUT
    for f in selection['files']:
        # Keep the already-mounted inode. Never rewrite an unchanged input.
        p=physical/f; value=(Q/'fixture'/kind/view/f).read_bytes()
        if p.read_bytes()!=value:p.write_bytes(value)
    return check_source(RUFF,selection,view)

def command(d,traced,elapsed=False):
    d.mkdir()
    e=env()
    for name in ('CARGO_LOG','RUSTC_LOG','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'):e.pop(name,None)
    args=['strace','-qq','-ff','-s','1048576','-e','trace=execve,execveat','-o',str(d/'exec'),*CMD] if traced else CMD
    assert not (traced and elapsed)
    with (d/'cargo.stdout').open('wb') as out, (d/'cargo.stderr').open('wb') as err:
        before=time.monotonic_ns()
        proc=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=RUFF,env=e)
        after=time.monotonic_ns()
    if elapsed:dump(d/'elapsed.json',{'start_monotonic_ns':before,'finish_monotonic_ns':after,'ns':after-before})
    assert proc.returncode==0,(d,proc.returncode,(d/'cargo.stderr').read_text()[-1400:])
    return d

def inspect(d,traced):
    rows=[json.loads(l) for l in (d/'cargo.stdout').read_bytes().splitlines()]
    arts=[a for a in rows if a['reason']=='compiler-artifact']
    msgs=[a for a in rows if a['reason']=='compiler-message']
    assert len(arts)==520 and sum(a['reason']=='build-finished' and a['success'] for a in rows)==1, (d,len(arts))
    assert not msgs,(d,len(msgs))
    key=lambda a:[a['package_id'],a['target']['name'],a['target']['kind'],a['profile']['test']]
    roster=sorted(key(a) for a in arts)
    out={'units':len(arts),'fresh':sum(a['fresh'] for a in arts),'dirty':[key(a) for a in arts if not a['fresh']],
         'rust_warnings':msgs,'unit_roster_sha256':hashlib.sha256(json.dumps(roster,sort_keys=True).encode()).hexdigest(),
         'stdout_sha256':sha(d/'cargo.stdout'),'stderr_sha256':sha(d/'cargo.stderr')}
    if traced:
        parse(d,'cold'); p=load(d/'processes.json')
        out['totals']=p['typed_invocations'];out['unknown']=p['unclassified'];out['traces_sha256']=sha(d/'exec-traces.tar.zst')
        out['rustc']=[{k:x.get(k) for k in ('kind','crate','pid','exec_sha256','image_sha256')} for x in p['typed'] if x['kind'].startswith('rustc')]
        out['scripts']=[{'pid':pid,'path':s,'package':Path(s).parents[2].name,'sha256':sha(s)} for pid,s in p['exec-images'] if Path(s).name.startswith(('build-script-','build_script_')) and Path(s).is_file()]
    dump(d/'receipt.json',out)
    return out,rows

def physical_snapshot(rows,kind):
    result={};metadata={};generated_zips=0
    for a in rows:
        name=a.get('package_id','').split('#',1)[0].rsplit('/',1)[-1]
        if a['reason']=='compiler-artifact' and name in ROOT_CRATES and a['target']['kind'] in (['lib'],['cdylib','rlib']):
            for f in a['filenames']:
                if f.endswith('.rmeta'):metadata[name]={'path':f,'sha256':sha(f)}
        if a['reason']=='build-script-executed' and name in ROOT_CRATES:
            od=Path(a['out_dir']); raw=od.parent/'run/stdout'
            assert raw.is_file() and not any(od.iterdir()),(name,od,raw)
            result[name]={'stdout_sha256':sha(raw),'lines':raw.read_text().splitlines(),'out_dir':str(od),'out_entries':[]}
        if kind=='holdout' and a['reason']=='build-script-executed' and name=='ty_vendored':
            path=Path(a['out_dir'])/'zipped_typeshed.zip'
            with zipfile.ZipFile(path) as z:data=z.read('stdlib/ty_extensions/pydantic.pyi')
            source=(RUFF/'crates/ty_vendored/ty_extensions/pydantic.pyi').read_bytes()
            assert data==source,(path,len(data),len(source))
            generated_zips+=1
            result[str(path)]={'archive_sha256':sha(path),'source_member_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    assert ROOT_CRATES<=result.keys() and (kind=='main' or generated_zips>0) and set(metadata)==ROOT_CRATES,(result.keys(),metadata.keys())
    result['library_metadata']=metadata
    return result

def remove_three():
    dest=X/'build-script-targets-study-v2/check/baseline-1/workspace.json'
    chosen=[Path(f) for f,v in load(dest).items() if f.endswith('.rmeta') and v['crate'] in ROOT_CRATES and (v['kind']==['lib'] or v['kind']==['cdylib','rlib'])]
    assert len(chosen)==3 and all(p.is_file() and p.is_relative_to(TARGET) for p in chosen),chosen
    receipt={str(p):{'sha256':sha(p),'mtime_before':p.stat().st_mtime_ns} for p in chosen}
    for p in chosen:p.unlink()
    return receipt

def nsinside(mode,stage,arm,direction,kind):
    d=Path(stage); physical=d/'active';selection=PRIMARY if kind=='main' else HOLDOUT
    begin,end=('original','edited') if direction=='reverse' else ('edited','original')
    subjects=load(PRODUCT/'pair.json')
    selected=subjects['raw'][arm] if mode=='trace-raw' else subjects[arm]
    assert sha(FROZEN/'bin/cargo')==selected and sha(FROZEN/'bin/rustc')==PLAN['fixed_rustc_frontend'] and sha(FROZEN/'lib'/SONAME)==PLAN['fixed_rustc_driver']
    baseline=check_source(RUFF,selection,begin)
    if mode=='seed':
        if begin=='edited':dump(d/'forced-three.json',remove_three())
        for i in range(4):
            info,rows=inspect(command(d/('settle-'+str(i)),True),True)
            if info['fresh']==520 and not info['totals'].get('rustc-full',0) and not info['totals'].get('rustc-link-only',0) and not info['totals'].get('wild',0) and not info['scripts']:break
        else:raise RuntimeError(('unable to establish a 520 fresh zero-compiler seed',d))
        dump(d/'seed.json',{'starting_source':baseline,'physical':physical_snapshot(rows,kind),'settled':info,'tools':subjects})
        return
    trace=mode!='timed';preinfo,rows=inspect(command(d/'preflight',trace),trace)
    assert preinfo['fresh']==520 and (not trace or not any(preinfo['totals'].get(k,0) for k in ('rustc-full','rustc-link-only','wild')) and not preinfo['scripts']),(d,preinfo)
    states=[(end,'change')] if kind=='main' else [(end,'change'),(begin,'restore')]
    snapshots={'before':physical_snapshot(rows,kind)} if trace else {}
    for view,tag in states:
        current=change(physical,kind,view)
        labels=(tag,tag+'-next',tag+'-next-2')
        # No checksum, trace, or parsing work between the three measured invocations.
        runs=[command(d/name,trace,mode=='timed') for name in labels]
        checks=[inspect(x,trace) for x in runs]
        receipts=[x[0] for x in checks]
        assert all(r['unit_roster_sha256']==preinfo['unit_roster_sha256'] for r in receipts)
        if kind=='main':
            for i,r in enumerate(receipts):
                expected=({'rustc-full':8,'wild':3},{'rustc-full':3 if arm=='parent' else 0,'wild':0},{'rustc-full':3 if arm=='parent' else 0,'wild':0})[i]
                if trace:assert all(r['totals'].get(k,0)==v for k,v in expected.items()) and r['totals'].get('rustc-link-only',0)==0 and ([s['package'] for s in sorted(r['scripts'],key=lambda s:s['package'])]==sorted(ROOT_CRATES) if i==0 else not r['scripts']),(d,i,r['totals'],r.get('scripts'))
                if i:assert r['fresh']==(514 if arm=='parent' else 520),(d,i,r['fresh'])
        if trace:snapshots[tag]=physical_snapshot(checks[-1][1],kind)
        dump(d/(tag+'-family.json'),{'source':current,'units':[r['units'] for r in receipts],'fresh':[r['fresh'] for r in receipts],
              'ns':[load(x/'elapsed.json')['ns'] for x in runs] if mode=='timed' else None,'unit_roster_sha256':preinfo['unit_roster_sha256']})
    if trace:dump(d/'physical-snapshots.json',snapshots)

def run(root,mode,d,sm,arm,direction,kind):
    binds=PRIMARY['files'] if kind=='main' else HOLDOUT['files']
    cargo=PRODUCT/(('raw-cargo-' if mode=='trace-raw' else 'cargo-')+arm)
    args=spawn_args(root,Q,sm,sm/'registry-home',[],cargo,DRIVER)
    ix=args.index('--')
    mounts=[v for f in binds for v in ('--ro-bind',str(d/'active'/f),str(RUFF/f))]
    cmd=[*args[:ix],*mounts,*args[ix:],sys.executable,'-B',str(HERE/'replay.py'),'inside',mode,str(d),arm,direction,kind]
    p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,start_new_session=True)
    try:
        while p.poll() is None:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:floor()
        assert p.returncode==0,(mode,d,p.returncode)
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
        raise

def outer(action):
    assert sha(HERE/'plan.json')=='d792a1c12d8484857843c94695500c7c5b7a0cab06e1a74c8b8d1201ae9d6d1a' and sha(HERE/'order.json')==PLAN['order_sha256']
    assert sha(HERE/'main.patch')==PRIMARY['patch_sha256'] and sha(HERE/'holdout.json')==PLAN['secondary_holdout_sha256'] and sha(HERE/'pydantic.patch')==HOLDOUT['patch_sha256']
    assert git('rev-parse','HEAD')==PRIMARY['ruff'] and not git('status','--porcelain')
    source=load(HERE/'source-binding.json');assert source['git_candidate']=='6b1cdb89253bab0cb26a3400df006ec614b476fb'
    subj=load(PRODUCT/'pair.json')
    assert subj['source']==source['source_3107_each_sha256'] and subj['raw_source_tree']==source['git_parent_tree'] and subj['patch_sha256']==source['patch_sha256'] and subj['packager_verify']==sha(HERE/'verify-package.py')==source['packager_python_sha256']
    for arm in ('parent','candidate','parent-repeat'):
        pack=load(PRODUCT/(arm+'-result.json'))
        assert pack['packager_sha256']==source['packager_executable_sha256'] and pack['LLVM_sha256']==source['packager_llvm_sha256'] and pack['packaged_sha256']==subj[arm]
    assert subj['parent']==subj['parent-repeat'] and subj['candidate']!=subj['parent']
    for arm in ('parent','candidate','parent-repeat'):assert sha(PRODUCT/('cargo-'+arm))==subj[arm]
    for arm in ('parent','candidate','parent-repeat'):assert sha(PRODUCT/('raw-cargo-'+arm))==subj['raw'][arm]
    assert sha(DRIVER)==PLAN['fixed_rustc_driver'] and sha(FROZEN/'bin/rustc')==PLAN['fixed_rustc_frontend']
    floor()
    with (P/'native-measure.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if action=='prepare':
            assert not Q.exists() and not RAM.exists()
            Q.mkdir(mode=0o700);RAM.mkdir(mode=0o700);initialize_sources()
        else:assert (Q/'prepared.json').is_file()
        p=Q/action;p.mkdir(mode=0o700);base=skeleton(p)
        def case(mode,tag,arm,direction,kind='main'):
            start='original' if direction=='reverse' else 'edited'
            seed=RAM/'seeds'/arm/start
            d=p/tag;d.mkdir(parents=True);sd=Q/'prepare'/arm/start
            if mode=='seed':
                sm=seed;copy_state(DONOR,sm);shutil.copytree(Q/'fixture'/kind/start,d/'active',copy_function=shutil.copy2)
                # A fully emitted metadata seed on the historical script source is required.
            else:
                sm=RAM/'episode';copy_state(seed,sm)
                original=sd/'active' if kind=='main' else Q/'fixture'/kind/start
                shutil.copytree(original,d/'active',copy_function=shutil.copy2)
            run(base,mode,d,sm,arm,direction,kind)
            if mode!='seed':
                assert sm==RAM/'episode';shutil.rmtree(sm)
            print('DONE',action,tag,arm,direction,flush=True)
        if action=='prepare':
            for arm in ('parent','candidate'):
                safety=Q/'safety'/arm;safety.mkdir(parents=True)
                subprocess.run([sys.executable,'-B',HERE/'controls.py',safety,arm],check=True)
                subprocess.run([sys.executable,'-B',HERE/'check-controls.py',safety/'check-negative',arm],check=True)
            for arm in ('parent','candidate'):
                for direction,view in [('reverse','original'),('restore','edited')]:case('seed',arm+'/'+view,arm,direction)
            for arm in ('parent','candidate'):
                for direction in ('reverse','restore'):
                    case('trace','calibration/'+arm+'/'+direction,arm,direction)
                    case('trace-raw','raw-calibration/'+arm+'/'+direction,arm,direction)
                    raw=p/'raw-calibration'/arm/direction; packaged=p/'calibration'/arm/direction
                    z={}
                    for label in ('preflight','change','change-next','change-next-2'):
                        ra=load(raw/label/'receipt.json');pa=load(packaged/label/'receipt.json')
                        for field in ('units','fresh','unit_roster_sha256','totals','rust_warnings'):
                            assert ra[field]==pa[field],(raw,label,field)
                        assert sorted(ra['dirty'])==sorted(pa['dirty'])
                        for f,keys in [('rustc',('kind','crate')),('scripts',('package','sha256'))]:
                            select=lambda row: sorted(tuple(v[k] for k in keys) for v in row[f])
                            assert select(ra)==select(pa),(raw,field,label,ra[f],pa[f])
                        z[label]={'fresh':ra['fresh'],'physical':ra['totals'],'unit_roster_sha256':ra['unit_roster_sha256']}
                    assert load(raw/'physical-snapshots.json')==load(packaged/'physical-snapshots.json'),(arm,direction,'scripts, metadata or generated outputs differed')
                    dump(packaged/'raw-packaged-parity.json',z)
                case('trace','pydantic/'+arm,arm,'reverse','holdout')
            dump(Q/'prepared.json',{'subjects':subj,'disk':floor(),'source':git('rev-parse','HEAD'),'runner_sha256':sha(HERE/'replay.py')})
        elif action=='score':
            release=load(HERE/'release-score.json');assert release['subjects']==subj and release['replay']==sha(HERE/'replay.py') and release['source_binding']==sha(HERE/'source-binding.json') and release['analysis']==sha(HERE/'analyze.py') and 'github.com/astral-sh/ohm-cargo' in release['public_binding']
            for block in ORDER:
                for arm in block['arm_order']:case('timed',str(block['order']).zfill(2)+'/'+arm,arm,block['direction'])
            for arm in ('parent','candidate'):
                for direction in ('reverse','restore'):case('trace','final-calibration/'+arm+'/'+direction,arm,direction)
            dump(Q/'complete.json',{'pairs':len(ORDER),'subjects':subj,'release':release,'disk':floor()})
        else:raise ValueError(action)
if __name__=='__main__':
    try:
        if sys.argv[1]=='inside':nsinside(*sys.argv[2:])
        else:outer(sys.argv[1])
    except BaseException:
        error=traceback.format_exc()
        if Q.is_dir():
            dest=Path(sys.argv[3]) if sys.argv[1]=='inside' else Q
            (dest/'failure.txt').write_text(error)
        raise
