"""Exercise a null, a planted effect, reversed direction penalty and first-slot nuisance."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import analyze
plan=json.loads(Path(__file__).with_name('plan.json').read_bytes())
def evidence(scenario):
    out={}
    for mode,rows in plan['orders'].items():
        series=[]
        for i,r in enumerate(rows):
            base=1_000_000+i*8_000
            times={arm:base for arm in 'BC'}
            if scenario=='gain':times['C']=base//2
            if scenario=='direction':times['C']=base//2 if r['direction']=='edit' else 2*base
            if scenario=='slot':times[r['order'][0]]=base//2
            series.append({**r,'ns':times})
        out[mode]=series
    return out
for label in ('null','gain','direction','slot'):
    report=analyze(evidence(label),plan)
    for endpoint in report.values():
        assert endpoint['exact_assignments']==63_504
        assert endpoint['passes']==(label=='gain'),(label,endpoint)
        if label=='gain':assert abs(endpoint['paired_reduction_pct']-50)<1e-7 and endpoint['holm']<.001
        if label in ('null','slot','direction'):assert abs(endpoint['paired_reduction_pct'])<1e-7
print('Four simulations passed for each endpoint.')
