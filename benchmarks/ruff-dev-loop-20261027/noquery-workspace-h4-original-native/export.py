"""Extract typed native evidence while retaining the private raw files and publishing only input identities."""
import collections,hashlib,io,json,re,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]);p=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');target=p/'native-target';build=p/'shared';src=Path.home()/'code/oss/ruff-ohm-empty-test-h4-20261027'
assert (root/'native.rc').read_text().strip()=='1' and not (root/'scored').exists()
assert not (root/'native-admission.json').exists() and 'AssertionError: roster' in (root/'native.log').read_text()
sha=lambda b:hashlib.sha256(b).hexdigest();load=lambda f:json.loads(f.read_bytes())
def scope(value):
    path=Path(value)
    for base,name in [(p/'rustup/toolchains/ohm','sdk'),(p/'frozen-toolchain','sdk'),(target,'target'),(build,'build'),(src,'ruff')]:
        if path.is_relative_to(base):return name+'/'+str(path.relative_to(base))
    if 'registry' in path.parts and 'src' in path.parts:
        rr=list(path.parts);i=rr.index('registry');assert rr[i+1]=='src' and len(rr)>i+3
        return 'registry-source/'+'/'.join(rr[i+3:])
    raise AssertionError(('unrecognized receipt input class',path.name))
def safe_rows(stdout):
    data=[]
    for line in stdout.read_bytes().splitlines():
        x=json.loads(line)
        if x.get('reason')!='compiler-artifact':continue
        pid=x['package_id'];assert pid.startswith(('registry+','path+'))
        pv=pid.rsplit('#',1)[-1];assert re.fullmatch('[A-Za-z0-9@.+_-]+',pv)
        data.append([pv,'workspace' if pid.startswith('path+') else 'registry',x['target']['name'],x['target']['kind'],x['features'],x['profile']['test'],x['fresh'],Path(x['executable']).name if x['executable'] else None,[Path(n).name for n in x['filenames']]])
    return data
def full_typed_rows(path):
    units=[]
    for line in path.read_bytes().splitlines():
        r=json.loads(line)
        if r.get('reason')!='compiler-artifact':continue
        u={k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')}
        pid=u['package_id'];assert pid.startswith(('registry+','path+'))
        package=pid.rsplit('#',1)[-1];assert re.fullmatch('[A-Za-z0-9@.+_-]+',package)
        u['package_id']={'sourced_as':'registry' if pid.startswith('registry+') else 'workspace','package':package,'exact_sha256':sha(pid.encode())}
        for k,v in [(u,'manifest_path'),(u['target'],'src_path')]:
            item=k[v];k[v]=dict(scope=scope(item),exact_sha256=sha(item.encode()))
        u['filenames']=[scope(v) for v in u['filenames']]
        if u['executable'] is not None:u['executable']=scope(u['executable'])
        units.append(u)
    return units
def dump(n,obj):buf[n]=json.dumps(obj,sort_keys=True,indent=2).encode()+b'\n'
buf={}
register=load(root/'protocol/subject-binding.json')
rs={arm:load(root/'results'/('unscored-'+arm)/'complete.json') for arm in 'OABC'}
b=load(root/'results/unscored-B/first/observer/proof.json');c=load(root/'results/unscored-C/cold/observer/proof.json')
summary={'mode':'Original four-arm native roster rejection','scored':0,'native_commands':sum(len(v['phases']) for v in rs.values()),'workspace_timing_eligible':False,'plan_sha256':sha((root/'protocol/plan.json').read_bytes()),'runner_sha256':sha((root/'protocol/SHA256SUMS').read_bytes()),'actual_first_optional_inputs_equal_independent_explicit_inputs':c['optional_inputs']==b['regular_inputs'],'first_failure':(root/'native.log').read_text().strip().splitlines()[-1],'failure_log_sha256':sha((root/'native.log').read_bytes()),'exit_code':int((root/'native.rc').read_text()),'independent_arm_native_receipts':{a:sha((root/'results'/('unscored-'+a)/'complete.json').read_bytes()) for a in 'OABC'}}
assert summary['native_commands']==16
summary['products']={k:{a:{n:y[n] for n in ('source','sha256')} for a,y in v.items()} if k=='cargo' else {n:v[n] for n in ('source','sha256')} for k,v in register.items() if k in ('cargo','old_driver','new_driver')}
summary['sdk_files']=register['sdk_files'];summary['separate_binary_contract']='4fa4cc2e5f3256b57e5b6e7b1c70ce0d32456061';summary['plan']='679c93366ba5d9a80361da08a6ab27e380ccac42';summary['independent_dirty_leaf']='869cb9b4d76cf2864efaa32e60f60c31b7ac0969'
dump('admission.json',summary)
for arm in 'OABC':
    d=root/'results'/('unscored-'+arm)
    for phase in ('cold','first','settled','settled2'):
        folder=d/phase;c=load(folder/'record.json');assert c==rs[arm]['phases'][phase];prefix=arm+'/'+phase+'/'
        record={k:v for k,v in c.items() if k!='public_executables'};record['executables']=[scope(x) for x in c['public_executables']];dump(prefix+'summary.json',record)
        dump(prefix+'cargo-rows.json',safe_rows(folder/'stdout'))
        dump(prefix+'full-typed-rows.json',full_typed_rows(folder/'stdout'))
        n=load(folder/'raw-native.json');dump(prefix+'native.json',{scope(k):s for k,s in n.items()})
        phy=load(folder/'native-processes.json')
        dump(prefix+'processes.json',{'jobs':phy['jobs'],'linkers':[[pid,w,Path(dst).name,rc,sig,Path(exe).name] for pid,w,dst,rc,sig,exe in phy['linkers']],'queries':phy['rustc_queries'],'observer_queries':phy['first_observer_capability_queries'],'cargo':phy['cargo'],'counts':phy['counts']})
        traces=load(folder/'trace-files.json');assert all(sha((folder/'trace'/k).read_bytes())==s for k,s in traces.items());dump(prefix+'trace-commitments.json',traces)
        if phase in ('cold','first'):
            detail=load(folder/'elf.json');dump(prefix+'elf.json',{scope(k):v for k,v in detail.items()})
            old=load(folder/'observer/proof.json');out=dict(old)
            for k in ('regular_inputs','optional_inputs','effective_inputs'):
                val=old[k];out[k]=[[scope(n),sha(n.encode()),algo,h,len_] for n,algo,h,len_ in val] if val is not None else None
            out['host_artifact_commitments']={f.name:sha(f.read_bytes()) for f in (folder/'observer').iterdir() if f.is_file()};dump(prefix+'proof.json',out)
        dump(prefix+'raw-host.json',{f:sha((folder/f).read_bytes()) for f in ('stdout','stderr','native-processes.json','trace-files.json','record.json','raw-native.json')})
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
    for n,data in sorted(buf.items()):
        assert len(data)<5*2**20;item=tarfile.TarInfo(n);item.size=len(data);item.mode=0o644;t.addfile(item,io.BytesIO(data))
