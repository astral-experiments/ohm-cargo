"""Independently replay the clone inventories, Cargo freshness decisions and native results."""
from pathlib import Path
import hashlib
import json
import re
import tarfile

here = Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()
with tarfile.open(here/'native.tar.gz', 'r:gz') as tar:
    names = tar.getmembers()
    assert len(names) == len({m.name for m in names}) == 384
    assert all(m.isfile() and m.size < 4*1024**2 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in names)
    raw = {m.name:tar.extractfile(m).read() for m in names}
index = json.loads(raw.pop('index.json'))
assert index == {n:[len(b),sha(b)] for n,b in raw.items()}
J = lambda name: json.loads(raw[name])
bind = J('bindings.json')
old = J('official-17.identity.json')
assert (old['cargo'],old['driver'],old['frontend']) == (bind['official'],bind['driver'],bind['rustc'])
assert bind['official']=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
assert bind['driver']=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
prod = bind['product']
assert prod['base']=='a0c7d08c898d3fdff992f2f431dec57d2486add2' and prod['patch']=='f0d968799ed2c095111dced3a688b025527deb7ac5a0f17ab04bdc6223faf800'
assert prod['matched_baseline']=='50ca47744e09d3ab9cfa320794c1a656935137abc3aaf22b7f74841f7c1be466'
assert prod['cargo']=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
assert sha(raw['host.py'])=='23ede634196c4a01b69cd71a7d443415bb4b8d8fb68da41d06e2f9278c847025' and sha(raw['measure.py'])=='1730dad54a16ed734a552678dda861ac89a785aadaf95cf470513b6ed9eeec4f'
table = J('complete.json')
assert table == json.loads((here/'outcomes.json').read_bytes()) and len(table)==18
first = {}
count = physical = 0
for history, phases in table.items():
    arm, case = history.split('/')
    root = history+'/'
    before,orig = J(root+'before.json'),J(root+'original.json')
    fp = raw[root+'before.fingerprint']
    assert fp[-41:-37]==b'OBS1' and fp[-33]==1 and sha(fp)==before['fingerprint']==orig['old']['fingerprint']
    assert before['elf']==orig['executable'] and before['exe']==orig['old']['exe']
    assert before['input']==orig['input'] and before['source']==orig['source'] and orig['old']['value']==17 and orig['old']['fresh']
    assert 'sample=17' in before['stdout'].splitlines() and first.setdefault(case,before)==before
    assert J(root+'done.json')==phases
    for phase in ('repeat','again'):
        p=root+phase+'/'; row=J(p+'row.json'); assert row==phases[phase]
        events=[json.loads(l) for l in raw[p+'cargo.jsonl'].splitlines()]
        assert events[-1]=={'reason':'build-finished','success':True}
        arts=[v for v in events if v['reason']=='compiler-artifact']
        caller,=[v for v in arts if v['target']['name']=='hold_direct']
        assert len(arts)==row['all_units']==4 and caller['executable']==before['elf']
        assert caller['fresh']==row['fresh']==(arm!='fixed')
        assert [v['target']['name'] for v in arts if not v['fresh']]==row['rebuilt_units']==(['hold_direct'] if arm=='fixed' else [])
        for k,n in [('program','program'),('fingerprint','fingerprint'),('dep','rustc.d'),('trace','exec')]: assert row[k]==sha(raw[p+n])
        fp=raw[p+'fingerprint'];assert fp[-41:-37]==b'OBS1' and bool(fp[-33])==row['complete']==(arm!='fixed')
        lines=raw[p+'exec'].splitlines(); jobs=0
        for l in lines:
            if not (b'execve(' in l and b'/toolchains/ohm/bin/rustc", [' in l and b'"--crate-name", "hold_direct"' in l):continue
            if l.endswith(b'<unfinished ...>'):
                pid=l.split(maxsplit=1)[0]
                resumed,=[v for v in lines if v.startswith(pid+b' <... execve resumed>')]
                assert resumed.endswith(b'= 0')
            else: assert l.endswith(b'= 0')
            assert b'"link-only"' not in l and b'"-Zbinary-dep-depinfo"' not in l
            jobs+=1
        assert jobs==int(arm=='fixed'); physical+=jobs;count+=1
        stdout=raw[p+'program']; observed,=re.findall(rb'^sample=(\d+)$',stdout,re.M)
        assert int(observed)==row['value']==(29 if arm=='fixed' else 17) and b'revision=2' in stdout.splitlines()
        assert row['source']==before['source'] and row['input']==before['input']
    replay=J(root+'external-replay.json')
    assert replay['cloned']['sha256']==phases['again']['elf'] and replay['cloned']['native'].encode()==raw[root+'again/program']
    assert replay['preserved_original']['sha256']==before['exe'] and replay['preserved_original']['native']==before['stdout']
assert (len(first),count,physical)==(6,36,12)
print('36 Cargo runs, 12 full corrected callers, 24 truly fresh baselines and 36 independent final/original executable replays verified.')
