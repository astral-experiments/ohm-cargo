"""Reconcile native process receipts, complete Cargo rosters, and raw product identities."""
from pathlib import Path
import ast
import collections
import gzip
import hashlib
import json
import re
import tarfile

root = Path(__file__).resolve().parent
sha = lambda b:hashlib.sha256(b).hexdigest()
idx = json.loads(gzip.decompress((root/'inventory.json.gz').read_bytes()))
assert idx['cache'] == '85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381'
with tarfile.open(root/'observations.tar.gz') as archive:
    members = {m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
assert len(members) == len(idx['members']) == 936 and members.keys() == idx['members'].keys()
for name,value in members.items():
    original, portable, olen, plen, changes = idx['members'][name]
    assert sha(value)==portable and len(value)==plen and value.count(idx['alias'].encode())==changes
    if not changes:
        assert original==portable and olen==plen
get = lambda name:json.loads(members[name])
phases = ['cold','settle','settle2','edit','edit-repeat','restore','restore-repeat']
plans = {'build':'dab9d2b21876fe4c8d8ac6a8482c85ad3559701c','test':'bb3b2ca6854a09f5746900ed20e1aa94b2b1c5ba'}
calls = re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$')
summary={}
for arm,(total,primary,dirty,edited_links) in {'build':(373,377,366,1),'test':(218,219,211,4)}.items():
    terminal=get(arm+'/complete.json');assert terminal['mode']==arm and terminal['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001'
    assert get(arm+'/registration.json')['commit']==plans[arm] and get(arm+'/progress.json')['phases']==phases
    assert [r['phase'] for r in terminal['phases']]==phases
    roster=None; products=None; seen={}; public=None; behavior=None
    for phase,note in zip(phases,terminal['phases'],strict=True):
        base=arm+'/'+phase+'/'
        assert note==get(base+'result.json') and note['units']==total
        assert bool(note['stage']=='reverse')==(phase in ('edit','edit-repeat'))
        data=[json.loads(s) for s in members[base+'stdout'].splitlines()]
        assert data[-1]=={'reason':'build-finished','success':True}
        rows=[r for r in data if r['reason']=='compiler-artifact']
        assert len(rows)==total and sum(r['fresh'] for r in rows)==note['fresh']
        sig=sorted(json.dumps({k:r[k] for k in ('manifest_path','package_id','target','profile','features','filenames','executable')},sort_keys=True) for r in rows)
        if roster is None:roster=sig
        assert roster==sig
        tracked=get(base+'products.json');nat=get(base+'native.json')
        assert len(tracked)==note['workspace_files'] and note['product_sha']==idx['members'][base+'products.json'][0] and note['native_sha']==idx['members'][base+'native.json'][0]
        source_files={f for r in rows if r['package_id'].startswith('path+file:') for f in r['filenames']+([r['executable']] if r['executable'] else [])}
        assert set(tracked)==source_files
        touched=set() if products is None else {name for name in tracked if tracked[name]['sha']!=products[name]['sha']}
        assert touched==set(note['changed_files']);products=tracked
        assert sha(members[base+'reader.stdout'])==note['reader'] and sha(members[base+'behavior.stdout'])==note['behavior'] and not members[base+'reader.compile.stderr']
        message=members[base+'reader.stdout']; brand=b'Rome' if note['stage']=='reverse' else b'Ruff'
        assert message.startswith(b'Poor layout: ') and b'Invalid document: End tag of kind Group' in message and message.count(b'internal '+brand+b' error')==2
        if behavior is None:behavior=members[base+'behavior.stdout']
        assert behavior==members[base+'behavior.stdout'] and ((behavior==b'x = 1\n') if arm=='build' else b': test\n' in behavior)
        observed_public=get(base+'public.json')
        if public is None:public=observed_public
        assert public==observed_public
        jobs=nat['jobs']; links=nat['links']; configure=nat.get('configure',[]); failed=nat.get('failed_compilers',[])
        for job in jobs+links+configure+failed:
            trace=members[base+'trace/exec.'+str(job['pid'])].splitlines()
            assert trace[-1]==('+++ exited with '+str(job.get('exit',0))+' +++').encode()
            hits=[line for line in trace if (m:=calls.match(line)) and ast.literal_eval(m[1].decode())==job['exe'] and ast.literal_eval(m[2].decode())==job['argv']]
            assert len(hits)==1 and idx['exec_lines'][sha(hits[0])]==job['raw']
        assert collections.Counter(j['kind'] for j in jobs)==note['physical'] and all(j['wild'] for j in links) and len(links)==note['wild']==note['all_links']
        assert len(configure)==note['configure_probes'] and all(p['output']=='conftest' for p in configure)
        assert len(failed)==note.get('failed_compilers',0)
        if phase=='cold':
            assert note['fresh']==0 and len(jobs)==primary and all(j['kind']=='full' for j in jobs)
            assert len(links)==(67 if arm=='build' else 41)
            if arm=='test':
                assert len(failed)==1 and failed[0]['name']=='fixtures' and failed[0]['exit']==1 and sum((j['exe'],j['argv'])==(failed[0]['exe'],failed[0]['argv']) for j in jobs)==1
            else:
                assert len(configure)==61 and sum(bool(p['exit']) for p in configure)==8
        elif phase in ('edit','restore'):
            assert note['fresh']==dirty and note['physical']=={'full':1,'link-only':edited_links} and len(links)==edited_links and len(touched)==(3 if arm=='build' else 5)
            assert [j['name'] for j in jobs if j['kind']=='full']==['ruff_formatter']
            assert len(configure)==len(failed)==0
            if arm=='test':
                null,=[r for r in rows if r['target']['kind']==['bin'] and r['target']['name']=='ruff_python_formatter' and r['profile']['test']]
                null_name=Path(null['executable']).name;assert null_name=='ruff_python_formatter-81814697f8234e3f' and null['executable'] not in touched
                selected,=[j for j in links if Path(j['output']).name==null_name]
                archives=[Path(a).name for a in selected['argv'] if a.endswith('.rlib')]
                assert len(archives)==135 and any(n.startswith('libruff_formatter-') for n in archives) and any(n.startswith('libruff_python_formatter-') for n in archives)
                assert len({Path(n).name for n in touched}&{Path(j['output']).name for j in links})==3
                seen[phase]=tracked[null['executable']]['sha']
        else:
            assert note['fresh']==total and not (jobs or links or touched or failed or configure)
    if arm=='test':assert len(seen)==2 and len(set(seen.values()))==1
    summary[arm]={'units':total,'edit_full':1,'edit_links':edited_links,'empty_harness_sha256':seen.get('edit')}
for stop in ('v1-build','v2-test','v3-test'):
    assert members[f'stops/{stop}/exit']==b'1' and b'AssertionError' in members[f'stops/{stop}/failure.txt']
print(json.dumps(summary,sort_keys=True))
