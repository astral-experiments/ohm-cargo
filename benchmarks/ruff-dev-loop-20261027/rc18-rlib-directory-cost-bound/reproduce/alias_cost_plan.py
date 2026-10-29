"""Run the registered in-process operations on one pinned CPU, outside any normal-build clocks."""
import collections,hashlib,json,os,random,statistics,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent/'alias-cost-v1'
plan=json.loads((d.parent/'alias-cost-registration.json').read_bytes())
assert len(plan['orders'])==12 and collections.Counter(plan['orders'])=={'AB':6,'BA':6}
fingerprint=json.loads((d/'qualification.json').read_bytes())['binary_sha256'];assert hashlib.sha256((d/'run').read_bytes()).hexdigest()==fingerprint
os.sched_setaffinity(0,{0});assert os.sched_getaffinity(0)=={0}
def op(a):
    out=subprocess.check_output([d/'run',a,d/'physical-inputs.tsv']).decode().strip().split()
    assert out[0]==a and int(out[1])==4212
    return {'arm':a,'members':int(out[1]),'observed_sum':int(out[2]),'elapsed_ns':int(out[3])}
training=[op(a)for a in 'ABBA']
raw=[]
for order in plan['orders']:
    raw.append([op(a)for a in order])
    (d/'progress-count').write_text(str(len(raw)))
sums={x['observed_sum'] for a in raw for x in a}
assert len(sums)==1
saved=[]
for p in raw:
    arms={x['arm']:x['elapsed_ns']for x in p};saved.append(arms['A']-arms['B'])
result={'case':'serial isolated same-device mechanism only','affinity':list(os.sched_getaffinity(0)),'training':training,'rows':raw,'median_ns':{a:statistics.median(x['elapsed_ns']for r in raw for x in r if x['arm']==a)for a in 'AB'},'median_saved_ns':statistics.median(saved),'favorable':sum(v>0 for v in saved),'registration_sha256':hashlib.sha256((d.parent/'alias-cost-registration.json').read_bytes()).hexdigest()}
(d/'terminal.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
