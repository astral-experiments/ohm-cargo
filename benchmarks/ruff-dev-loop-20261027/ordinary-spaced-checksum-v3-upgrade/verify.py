"""Compare every first and second upgraded command directly with the earlier clean Cargo output."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile

here=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
def unpack(name):
    with tarfile.open(here/name) as tar:
        data={m.name:tar.extractfile(m).read() for m in tar}
    index=json.loads(data.pop('inventory.json'))
    assert {k:[digest(b),len(b)] for k,b in data.items()}==index
    return data
def read(mapping,key):return json.loads(mapping[key])
def messages(mapping,key):
    return [json.loads(b) for b in mapping[key].splitlines()]
def errors(rows):
    return [v['message'] for v in rows if v['reason']=='compiler-message' and v['message']['level']=='error']

if (here/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
assert digest((here/'before.tgz').read_bytes())=='438a4b4836c1605cf8f3783d78dc02ebf13f617b2e56aa59756568788c884232'
assert digest((here/'replay.py').read_bytes())=='5dc7c7e375cc5bb75852f9ba49627077a3bd8fc13b2f5b61bfb924e3b5922c73'
assert digest((here/'cargo.patch').read_bytes())=='cd34639683147ae6bf6dfed39153f1842cb57b5c504b6589dd473236234f9811'
before=unpack('before.tgz');fixed=unpack('upgraded.tgz')
allr=read(fixed,'complete.json');assert len(allr)==14
restored=rejects=commands=0
for label,short in sorted(allr.items()):
    g,c=label.split('/');prefix=label+'/'
    old=read(before,prefix+'result.json');prior=old['cargo-upgrade'];gold=old['clean']
    orig=errors(messages(before,prefix+'clean/stdout'))
    poisoned=(g=='alias' or c.endswith('-decoy'))
    if poisoned:
        assert prior['fresh']==[True] and prior['rc']==0
    paired=read(fixed,prefix+'result.json')
    assert [v['phase'] for v in paired]==['first','next']
    collected=[]
    for row in paired:
        k=prefix+row['phase']+'/'
        assert row['cargo']=='549d2ed1cb47a4810f334572fd3a56987a0695a24f7a7b79c1b6a3b11c357087'
        assert row==read(fixed,k+'record.json') and row['cmd']==prior['cmd'] and row['source']==prior['source']
        assert row['old_fresh']==prior['fresh'] and row['old_runtime']==prior['runtime'] and row['old_rc']==prior['rc']
        assert all(digest(fixed[k+f])==row[f] for f in ('stdout','stderr'))
        stream=messages(fixed,k+'stdout')
        assert stream[-1]=={'reason':'build-finished','success':gold['rc']==0}
        art=[v for v in stream if v['reason']=='compiler-artifact']
        assert row['fresh']==[v['fresh'] for v in art] and row['rc']==gold['rc']
        assert errors(stream)==orig
        assert row['clean_diag_sha']==digest(json.dumps(orig,sort_keys=True).encode())
        if c.startswith('build-'):
            assert gold['runtime']==row['runtime']==29 and fixed[k+'program.stdout']==b'29\n'
            assert len(row['elf'])==64
            if row['phase']=='first':assert row['fresh']==[False]
            if row['phase']=='next' and c=='build-ordinary':assert row['fresh']==[True]
            if poisoned:
                assert prior['runtime']==17
                if row['phase']=='first':restored+=1
        else:
            assert not art and orig and row['errors']==['E0308'] and row['rc']==101
            if poisoned and row['phase']=='first':rejects+=1
        enc=row['encoded']
        if enc:
            b=fixed[k+'encoded'];assert digest(b)==enc['new_sha'] and b[5]==enc['version'] and enc['old_version']==2
            old_file,=[(key,meta) for key,meta in prior['physical_files'].items() if Path(meta['path']).name=='dep-bin-byte_reader']
            assert old_file[1]['sha']==enc['old_sha'] and digest(before[prefix+'cargo-upgrade/'+old_file[0]])==enc['old_sha']
        collected.append([row['rc'],row['fresh'],row['runtime'],row['errors'],enc.get('version')])
        commands+=1
    assert collected==short
assert (restored,rejects,commands)==(5,5,28)
print('Verified 28 upgraded commands, every native output or full clean E0308, five stale binaries repaired, and five previously accepted invalid checks rejected.')
