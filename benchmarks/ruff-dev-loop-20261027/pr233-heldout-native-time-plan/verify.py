from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import analyze
p=Path(__file__).resolve().parent
plan=json.loads((p/'plan.json').read_bytes())
assert all(len(seq)==2 and set(seq)==set('BC') for seq in [s['arms'] for s in plan['sequence']])
for n, (a,b,sig) in enumerate([(100,100,False),(100,60,True),(60,100,False)]):
    rows=[dict(q,elapsed_ns={'B':a*1000000,'C':b*1000000}) for q in plan['sequence']]
    res=analyze(plan,rows);assert len(res)==6 and all(z['qualified_reduction']==sig for z in res)
    assert all(abs(z['reduction_percent']-100*(1-b/a))<1e-10 and z['assignments']==4900 for z in res)
    assert all(z['exact_p']==(1 if a==b else 2/4900) for z in res)
print('Three controlled six-endpoint families reproduce null, gain and regression; all 4,900 balanced assignments are included.')
