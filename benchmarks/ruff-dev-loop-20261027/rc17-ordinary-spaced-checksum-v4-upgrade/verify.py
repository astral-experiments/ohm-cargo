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
assert digest((here/'replay.py').read_bytes())=='2f5cc1d6c25a04c779ab66a7af099c43fcc85315352cf5348ba467dae3b62e6d'
assert digest((here/'cargo.patch').read_bytes())=='26883ced2f75bf7099bea1d69f83cc64a7e76b63069700cad8426a981d1170d3'
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
        assert row['cargo']=='787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5'
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
            if row['phase']=='next' and c=='build-ordinary':assert row['fresh']==[True] and row['encoded']['version']==4
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
