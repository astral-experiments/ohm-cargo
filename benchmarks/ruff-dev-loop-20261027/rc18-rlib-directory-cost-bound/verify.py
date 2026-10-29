"""Verify full schedule, exact inputs, native program checksum and every engineering clock."""
import collections
import hashlib
import json
import random
import statistics
from pathlib import Path
root=Path(__file__).resolve().parent
def read(n):
    return json.loads((root/n).read_bytes())
def sha(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()
plan=read('registration.json');qual=read('qualification.json');result=read('terminal.json')
p=sha(root/'registration.json')
assert p==result['registration_sha256']=='04fe8ee8eb206d6d4a14975c056fe7b7555f13fe0beb0fd479a5cc83755647c9'
assert all(sha(root/'reproduce'/name)==expected for name,expected in plan['source'].items())
orders=['AB']*6+['BA']*6
random.Random(202610282355).shuffle(orders)
assert orders==plan['orders']==[''.join(v['arm']for v in r) for r in result['rows']]
assert ''.join(z['arm']for z in result['training'])=='ABBA'
assert len(qual['groups'])==len({v['crate']for v in qual['groups']})==30
assert sum(v['members']for v in qual['groups'])==4212
for v in qual['groups']:
    assert v['members']>0 and v['bytes']>0 and len(v['archive_sha256'])==len(v['member_sha256'])==64
assert result['affinity']==[0] and len(qual['binary_sha256'])==64
records=[v for r in result['rows']for v in r]+result['training']
assert len(records)==28 and all(v['members']==4212 and v['elapsed_ns']>0 for v in records)
assert len({v['observed_sum']for v in records})==1
pairs=[{v['arm']:v['elapsed_ns']for v in row}for row in result['rows']]
saved=[r['A']-r['B']for r in pairs]
assert result['median_ns']=={a:statistics.median(r[a]for r in pairs)for a in 'AB'}
assert result['median_saved_ns']==statistics.median(saved)
assert result['favorable']==sum(v>0 for v in saved)
sibling=root.parent/'rc18-parser-cgu-alias-operations'
if sibling.exists():
    assert sha(sibling/'SHA256SUMS')=='6d3ef263d86741c5670bac21662aa6558cea4569f981db260ba984f545595e9e'
    jobs=json.loads((sibling/'all-jobs.json').read_bytes())['all_rustc_jobs']
    assert {j['name']:j['counts']['hardlinked']for j in jobs if j['pure']}=={v['crate']:v['members']for v in qual['groups']}
print(json.dumps({'pairs':len(pairs),'A_ms':result['median_ns']['A']/1e6,'B_ms':result['median_ns']['B']/1e6,'paired_saved_ms':result['median_saved_ns']/1e6,'favorable':result['favorable']},sort_keys=True))
