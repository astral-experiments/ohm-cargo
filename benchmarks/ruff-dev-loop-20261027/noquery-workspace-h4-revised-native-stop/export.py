"""Seal the three complete native arms and the first incomplete native trace without retrying it."""
import collections,hashlib,io,json,re,sys,tarfile
from pathlib import Path
root=Path.home()/'.cache/ohm-noquery-full-native-h4-20261028-v2'
h=lambda b:hashlib.sha256(b).hexdigest()
def hf(f):
    with f.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
J=lambda f:json.loads(f.read_bytes())
def safe_scope(s):
    p=Path(s)
    anchors={'native-target':'target','shared':'build','ruff-ohm-empty-test-h4-20261027':'ruff','frozen-toolchain':'sdk'}
    for n,alias in anchors.items():
        if n in p.parts:return alias+'/'+str(Path(*p.parts[p.parts.index(n)+1:]))
    if 'rustup' in p.parts and 'toolchains' in p.parts:
        j=p.parts.index('toolchains');return 'sdk/'+str(Path(*p.parts[j+2:]))
    if 'registry' in p.parts and 'src' in p.parts:
        i=p.parts.index('registry');assert p.parts[i+1]=='src';return 'registry-source/'+str(Path(*p.parts[i+3:]))
    raise AssertionError(p.name)
def units(raw):
    rows=[json.loads(l) for l in raw.splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
    rr=[]
    for r in rows:
        if r['reason']!='compiler-artifact':continue
        pid=r['package_id'];pv=pid.rsplit('#',1)[-1];assert re.fullmatch(r'[A-Za-z0-9@.+_-]+',pv) and pid.startswith(('path+','registry+'))
        rr.append({'crate':pv,'kind':r['target']['kind'],'target':r['target']['name'],'features':r['features'],'profile':r['profile'],'fresh':r['fresh'],'executable':safe_scope(r['executable']) if r['executable'] else None,'outputs':list(map(safe_scope,r['filenames']))})
    assert len(rr)==619
    return rr
def witness(data):
    logs=[];pending=None
    for txt in data.splitlines():
        _,_,line=txt.partition(b' ');image=None;event='other'
        if line.startswith((b'execve(',b'execveat(')):
            m=re.match(rb'execve\("([^"]+)"',line)
            if m:
                image=Path(m[1].decode()).name
                if not re.fullmatch(r'[a-zA-Z0-9_.+ -]+',image):image='<other>'
            if line.endswith(b'<unfinished ...>'):
                assert pending is None;pending=h(txt);event='exec unfinished'
            else:event='complete exec'
        elif re.match(rb'^<\.\.\. (?:execve|execveat) resumed>',line):
            assert pending;pending=None;event='exec resumed'
        elif line.startswith(b'+++ exited with '):event='exited '+re.search(rb'\d+',line)[0].decode()
        elif re.search(rb'superseded|pid changed',line):event='strace task boundary'
        else:event=line.split(None,1)[0][:34].decode(errors='replace') if line and line[:1] in (b'+',b'-',b'?') else 'other'
        logs.append({'event':event,'image_basename':image,'raw_line_sha256':h(txt)})
    return pending,logs
assert (root/'native.rc').read_text().strip()=='1' and not (root/'native-admission.json').exists() and not (root/'scored').exists()
lines=(root/'native.log').read_text().splitlines();at=lines.index('AssertionError');assert lines[at-2].strip()=='assert pending is None' and 'processes.py", line 34' in lines[at-3]
phases={};notclosed={};files={};commitments={}
for arm in 'COAB':
    case=root/'results'/('unscored-'+arm);folders=[p for p in ('cold','first','settled','settled2') if (case/p).is_dir()];assert len(folders)==(1 if arm=='B' else 4)
    phases[arm]={}
    for ph in folders:
        p=case/ph;status=J(p/'status.json');assert status['rc']==0 and status['elapsed_ns'] is None
        paths=sorted((p/'trace').glob('exec.*'));hashes={f.name:hf(f) for f in paths};assert hashes
        raws={'stdout':hf(p/'stdout'),'stderr':hf(p/'stderr'),'status':hf(p/'status.json'),'raw_trace_files':hashes}
        rs=units((p/'stdout').read_bytes());matched=arm!='B'
        rec={'cargo_rc':0,'instrumented':True,'elapsed_ns':None,'fresh':sum(r['fresh'] for r in rs),'unit_count':len(rs),'declared_executables':sum(bool(r['executable']) for r in rs),'completed_native_verifier':matched}
        if matched:
            n=J(p/'record.json');assert J(p/'trace-files.json')==hashes and n==J(case/'complete.json')['phases'][ph]
            full=J(p/'native-processes.json');assert not full['first_observer_capability_queries']
            native=J(p/'raw-native.json');rec.update(counts=n['processes'],actual_elf_count=len(native),listing_and_cli=n['cli'],diagnostics=n['diagnostics'])
            files[f'{arm}/{ph}/raw-elf.json']={safe_scope(k):v for k,v in native.items()}
            files[f'{arm}/{ph}/processes.json']={'jobs':full['jobs'],'linkers':[[pid,wild,Path(out).name,rc,hh,Path(image).name] for pid,wild,out,rc,hh,image in full['linkers']],'rustc_queries':full['rustc_queries'],'cargo':full['cargo']}
            if ph in ('cold','first'):
                obs=J(p/'observer/proof.json')
                for k in ('regular_inputs','optional_inputs','effective_inputs'):
                    if obs[k] is not None:obs[k]=[[safe_scope(path),h(path.encode()),algo,dig,size] for path,algo,dig,size in obs[k]]
                files[f'{arm}/{ph}/proof.json']=obs
        else:
            assert not (p/'record.json').exists() and not (p/'native-processes.json').exists()
            for f in paths:
                rem,ev=witness(f.read_bytes())
                if rem:notclosed[f.name]={'open_exec_line_sha256':rem,'events':ev,'complete_trace_file_sha256':hashes[f.name]}
            assert notclosed
        phases[arm][ph]=rec
        files[f'{arm}/{ph}/cargo.json']=rs;files[f'{arm}/{ph}/raw.json']=raws
files['failure.json']={'failed':True,'reason':'processes.py line 34 required every unfinished exec in every pid trace file to have a matching resume','native_log_sha256':hf(root/'native.log'),'runtime_sha256sums':hf(root/'protocol/SHA256SUMS'),'registered_native_verifier_sha256':hf(root/'protocol/processes.py'),'incomplete_traces':notclosed,'phases':phases,'full_workspace_wall_rows':0,'arm_B_user_command':{'cargo_result':'success','native_phases_remaining_after_cold':3,'blocked_at':'reading actual process traces'},'no_admission_published':True}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
    for n,v in sorted(files.items()):
        data=json.dumps(v,sort_keys=True,separators=(',',':')).encode()+b'\n';i=tarfile.TarInfo(n);i.size=len(data);i.mode=0o644;t.addfile(i,io.BytesIO(data))
