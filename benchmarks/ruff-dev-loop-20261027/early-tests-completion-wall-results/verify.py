"""Rebuild the paired study from the 72 measured process clocks and their native witnesses."""
from pathlib import Path
import gzip
import hashlib
import json
import subprocess
import sys
import tarfile

root=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
if (root/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
idx=json.loads(gzip.decompress((root/'inventory.json.gz').read_bytes()))
def archive(path):
    files={}
    with tarfile.open(path) as a:
        for m in a:
            assert m.isfile() and m.name in idx and m.name not in files
            raw=a.extractfile(m).read()
            old,h,original,size,n=idx[m.name]
            assert sha(raw)==h and len(raw)==size and (n or (old==h and size==original))
            files[m.name]=raw
    return files
control=archive(root/'controls.tar.gz'); seen=set(control)
read=lambda data,n:json.loads(data[n])
plan=read(control,'protocol/plan.json')
assert idx['protocol/SHA256SUMS'][0]=='cd93b8a8a44333efc970e8522525b74201c6ddbdbd0a4c81e185e87708b4376e'
assert control['protocol/outer.exit']==b'0' and not control['protocol/outer.stderr']
assert read(control,'protocol/grant.json')['manifest']==idx['protocol/SHA256SUMS'][0]
assert read(control,'trial/complete.json')['commands']==72 and plan['scored']==72
assert plan['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001'
rows={};previous_stop=0;follow_count=0
for w,n in (('selection',24),('cold',12)):
    rows[w]=[];roster=None
    for i,order in enumerate(plan['orders'][w],1):
        data=archive(root/(w+'-'+str(i).zfill(2)+'.tar.gz'))
        assert not seen.intersection(data);seen.update(data)
        ns={}
        for a in order:
            k=w+'/'+str(i).zfill(2)+'-'+a+'/'
            ref='native/'+w+'-'+a+'/'
            native=read(control,ref+'product.json')
            v=read(data,k+'verified.json'); clock=read(data,k+'ordinary/clock.json')
            assert v['workflow']==w and v['arm']==a and v['subject']==plan['cargo'][a] and v['source_untouched']
            assert v['original_reference']==idx[ref+'product.json'][0]
            assert v['input']==(plan['edited_sha256'] if w=='selection' else plan['source_sha256'])
            assert clock['returncode']==0 and clock['argv']==plan['command']
            assert v['ns']==clock['elapsed_ns']==clock['stop']-clock['start']>0
            assert clock['start']>previous_stop
            previous_stop=clock['stop'];ns[a]=v['ns']
            assert not data[k+'ordinary/stdout'] and b'Finished' in data[k+'ordinary/stderr']
            assert b'Blocking waiting' not in data[k+'ordinary/stderr']
            assert v['stdout']==idx[k+'ordinary/stdout'][0] and v['stderr']==idx[k+'ordinary/stderr'][0]
            assert data[k+'ordinary/test-list.stdout']==control[ref+'test-list.stdout']
            assert data[k+'ordinary/test-list.stderr']==control[ref+'test-list.stderr']
            assert b'inlay_hints::default_inlay_hints: test' in data[k+'ordinary/test-list.stdout']
            assert set(v['initial_native'])==set(native['native']) and len(native['native'])==110
            same={f for f,h in v['initial_native'].items() if native['native'][f]==h}
            diff=set(v['initial_native'])-same
            assert v['as_built']['exact']==len(same) and set(v['as_built']['allowed'])==diff
            for left,right in v['as_built']['allowed'].values():
                assert left['normalized']==right['normalized'] and left['bytes']==right['bytes']
            assert v['followups'] and not v['followups'][-1]['dirty'] and v['roster']==native['roster']
            assert len(v['followups'])==1 if w=='selection' else len(v['followups'])<=3
            for j,check in enumerate(v['followups'],1):
                fk=k+'follow-'+str(j)+'/';cmd=read(data,fk+'command.json');prod=read(data,fk+'product.json')
                assert cmd['exit']==0 and not cmd['trace'] and cmd['source']==plan['ruff'] and cmd['cargo']==plan['cargo'][a]
                assert cmd['stdout']==idx[fk+'stdout'][0] and cmd['stderr']==idx[fk+'stderr'][0]
                messages=[json.loads(line) for line in data[fk+'stdout'].splitlines()]
                assert messages[-1]=={'reason':'build-finished','success':True}
                units=[x for x in messages if x['reason']=='compiler-artifact']
                assert len(units)==prod['units']==619
                assert len({x['executable'] for x in units if x['executable']})==len(prod['executables'])==102
                dirty=[[x['target']['name'],x['target']['kind']] for x in units if not x['fresh']]
                assert dirty==check['dirty']==prod['dirty'] and check['roster']==prod['roster']==v['roster']
                assert check['same']+len(check['other'])==110 and prod['native'].keys()==native['native'].keys()
                keys=('package_id','manifest_path','target','profile','features','filenames','executable')
                current=sorted(json.dumps({s:x[s] for s in keys},sort_keys=True) for x in units)
                if roster is None:roster=current
                else:assert current==roster
                follow_count+=1
        rows[w].append(dict(order=order,ns=ns))
    assert len(rows[w])==n and rows[w]==read(control,'trial/ledger-'+w+'.json')
assert seen==idx.keys() and rows==read(control,'trial/all.json')
assert sha(control['protocol/analyze-wall.py'])==plan['fixed_inputs']['analyze-wall.py']
sys.path.insert(0,str(root))
import importlib.util
spec=importlib.util.spec_from_file_location('registered_stats',root/'analyze-wall.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert sha((root/'analyze-wall.py').read_bytes())==sha(control['protocol/analyze-wall.py'])
result=module.analyze(plan,rows);assert result==read(control,'trial/result.json')
print(json.dumps(dict(commands=72,pairs={w:len(v) for w,v in rows.items()},followup_commands=follow_count,results=result),sort_keys=True))
