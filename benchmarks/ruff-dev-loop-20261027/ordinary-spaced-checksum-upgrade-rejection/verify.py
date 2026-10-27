"""Reconstruct the false-fresh results from raw Cargo JSON, depfiles, fingerprints and native outputs."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tarfile

here=Path(__file__).resolve().parent
if (here/'SHA256SUMS').is_file():
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
with tarfile.open(here/'observed.tgz') as t:
    files={m.name:t.extractfile(m).read() for m in t}
idx=json.loads(files.pop('inventory.json'))
assert idx=={n:[sha(b),len(b)] for n,b in files.items()}
get=lambda n:json.loads(files[n])
root={'plain':'bfd692d6e7e59cc68251d01451023bcd10311938b26b32b2f3f10849398578d9',
      'alias':'7136a554bdf41da39da9b245569333e7b0ee0e7199e9f764fb1ab6ea336997bc'}
old='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
first_fix='dc377742bbae74011f4dca99b7c5ea3002e5af5b979149a6a2f8c0ba7bc726c4'
before=sha(bytes([17,255,0,254]));after=sha(bytes([29,255,0,254]))
digest17=b'8c22c73f63db34c0d0f92b7601558b689981bd7d3107dd98fda4fdbd7e9145ea'
digest29=b'd71296e687d690af44fd4e117a86d351122a6213bb65071647921df79a5fbefa'
def paths(b):
    assert b[:6]==bytes([1,0,0,0,255,2])
    pos=6;items=[]
    def u32():
        nonlocal pos
        n=struct.unpack_from('<I',b,pos)[0];pos+=4
        return n
    for _ in range(u32()):
        k=b[pos];pos+=1;n=u32();name=b[pos:pos+n];pos+=n
        ck=b[pos];pos+=1;h=None
        if ck:
            assert ck==1
            length=struct.unpack_from('<Q',b,pos)[0];pos+=8;n=u32();h=b[pos:pos+n];pos+=n
            if name.endswith(b'value.bin'):assert length==4
        assert k in (0,1)
        items.append((name,h))
    for _ in range(u32()):
        n=u32();pos+=n;present=b[pos];pos+=1
        if present:n=u32();pos+=n
    assert pos==len(b)
    return items

totals=programs=stale=hidden=0
for group,source in [('plain','ordinary-include.py'),('alias','ordinary-alias-modes.py')]:
    assert sha((here/source).read_bytes())==root[group]
    subjects=get(group+'/complete.json')
    assert len(subjects)==(6 if group=='plain' else 8)
    for case in subjects:
        prefix=group+'/'+case+'/'
        is_build=case.startswith('build-')
        poisoned=group=='alias' or case.endswith('-decoy')
        records=get(prefix+'result.json')
        assert set(records)=={'baseline','unchanged','changed','cargo-upgrade','clean'}
        rust=files[prefix+'source/src/main.rs']
        assert b'include_bytes!' in rust and (b'const _: [();17]' in rust)==(not is_build)
        assert b'proc-macro' not in files[prefix+'source/Cargo.toml'] and files[prefix+'source/Cargo.lock'].count(b'[[package]]')==1
        for phase,rec in records.items():
            k=prefix+phase+'/'
            assert rec==get(k+'record.json') and rec['source']==sha(rust)
            assert rec['cargo']==(first_fix if phase in ('clean','cargo-upgrade') else old)
            assert rec['data']==(before if phase in ('baseline','unchanged') else after)
            assert rec['decoy']==(after if poisoned and phase in ('baseline','unchanged','changed') else None)
            assert all(sha(files[k+n])==rec[n] for n in ('stdout','stderr'))
            rows=[json.loads(b) for b in files[k+'stdout'].splitlines()]
            assert rows[-1]=={'reason':'build-finished','success':rec['rc']==0}
            art=[v for v in rows if v['reason']=='compiler-artifact']
            assert len(art)<=1 and all(v['target']['name']=='byte_reader' for v in art)
            assert rec['fresh']==[v['fresh'] for v in art]
            errors=[(v['message'].get('code') or {}).get('code') for v in rows if v['reason']=='compiler-message' and v['message']['level']=='error']
            assert errors==rec['errors']
            assert ('-Zohm-worktree-seeds=no' in rec['cmd'])==('-legacy-' in case)
            assert ('-Zchecksum-freshness' in rec['cmd'])==('-legacy-' in case)
            assert rec['cmd'][:2]==['cargo','+ohm'] and rec['cmd'].count('build' if is_build else 'check')==1
            if is_build:
                assert rec['rc']==0 and files[k+'program.stdout']==(str(rec['runtime'])+'\n').encode()
                actual=17 if phase in ('baseline','unchanged') or (poisoned and phase in ('changed','cargo-upgrade')) else 29
                assert rec['runtime']==actual;programs+=1
            else:
                bad=(phase=='clean' or phase in ('changed','cargo-upgrade') and not poisoned)
                assert (rec['rc'],errors)==((101,['E0308']) if bad else (0,[]))
            if poisoned and phase in ('changed','cargo-upgrade'):
                assert rec['fresh']==[True];stale+=1
            if case.endswith('-ordinary') and (phase=='unchanged' or is_build and phase=='cargo-upgrade'):
                assert rec['fresh']==[True]
            if case.endswith('-space') and phase=='unchanged':
                assert rec['fresh']==[False]
            raw=[]
            for f,meta in rec['physical_files'].items():
                b=files[k+f]
                assert sha(b)==meta['sha'] and not meta['observer'] and meta['trailer'] is None
                if Path(meta['path']).name=='dep-bin-byte_reader':
                    entries=paths(b)
                    if poisoned and phase in ('baseline','changed','cargo-upgrade'):
                        inc,=[h for path,h in entries if path.endswith(b'value.bin')]
                        assert inc==b'blake3='+digest29
                        if group=='alias' and phase=='changed':
                            physical=[path.decode() for path,_ in entries]
                            assert physical==get(prefix+'encoded-paths.json')
                            assert any(' ' in name for name in physical)==('-default-' in case)
                            if '-legacy-' in case:hidden+=1
                else:
                    raw += [line for line in b.splitlines() if line.startswith(b'# checksum:') and b'value.bin' in line]
            if phase=='baseline' and poisoned:
                assert raw and all(b'blake3='+digest29+b' file_len:4' in line for line in raw)
            if phase=='baseline' and case.endswith('-ordinary'):
                assert raw and all(b'blake3='+digest17+b' file_len:4' in line for line in raw)
            totals+=1
        if is_build:
            replay=get(prefix+'native-replay.json')
            assert all(v['runtime']==records[k]['runtime'] and len(v['elf'])==64 and v['bytes']>10000 for k,v in replay.items())
            if poisoned:
                assert replay['cargo-upgrade']['elf']!=replay['clean']['elf']
assert totals==70 and programs==35 and stale==20 and hidden==4
assert b'alias space/value.bin' in (here/'ordinary-alias.stderr').read_bytes()
print('Verified 70 Cargo commands, 35 recorded native outputs, 20 false-fresh outcomes and four ordinary records with no remaining space in their paths.')
