"""Check balanced randomization against flat, position-only and known component effects."""
import csv
import json
from pathlib import Path
import sys
import tempfile

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from analyze import evaluate, holm, load_blocks

plan=json.loads((here/'plan.json').read_bytes())
out={}
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)/'input.csv'
    for name,effects,position in [('flat',dict(A=2,B=2,C=2),False),
                                  ('position-only',dict(A=2,B=2,C=2),True),
                                  ('both',dict(A=2,B=2,C=1),False),
                                  ('compiler-only',dict(A=2,B=1,C=1),False)]:
        rows=[]
        for mode,spec in plan['endpoints'].items():
            orders=spec['orders']
            with p.open('w',newline='') as f:
                writer=csv.writer(f);writer.writerow(['block','slot','arm','elapsed_ns'])
                for i,order in enumerate(orders,1):
                    for pos,arm in enumerate(order,1):
                        noise=i*(pos if position else 1)*10**7
                        writer.writerow([i,pos,arm,effects[arm]*noise])
            blocks=load_blocks(p,orders)
            for base in 'AB':
                rows.append(evaluate(orders,blocks,base,spec['bootstrap_seeds'][base]))
        holm(rows)
        for r in rows:
            expected=name=='both' or name=='compiler-only' and r['control_arm']=='A'
            assert r['qualified_wall_reduction']==expected
            assert r['as_or_more_extreme']==(2 if expected else 8000)
            assert abs(r['geometric_elapsed_reduction_pct']-(50 if expected else 0))<1e-12
            assert r['balanced_assignments']==8000
        out[name]=[{'control':r['control_arm'],'extreme':r['as_or_more_extreme'],'holm':r['holm_p']} for r in rows]
print(json.dumps(out,indent=2))
