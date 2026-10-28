"""Analytic nulls, effect, adverse floor, and refusal of misordered native samples."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from design import schedule
from analyze import evaluate,read
root=Path(__file__).resolve().parent;plan=json.loads((root/'plan.json').read_bytes())

def synthetic(mode):
    cold=[];warm=[]
    for h in schedule():
        for position,arm in enumerate(h['cold_order'],1):
            factor=(.43+position/4) if mode=='slot_only' else 1
            first=0.82 if arm=='C' and mode in ('true','adverse_settled') else 5.7
            cold.append(dict(history=h['history'],position=position,arm=arm,cold_ns=round(factor*270e9),first_ns=round(factor*first*1e9),immediate_settled_ns=round(factor*.83e9)))
        for k,order in enumerate(h['settled_orders'],1):
            for position,arm in enumerate(order,1):
                factor=(.43+position/4) if mode=='slot_only' else 1
                slowdown=1.06 if mode=='adverse_settled' and arm=='C' else 1
                warm.append(dict(history=h['history'],wave=k,position=position,arm=arm,elapsed_ns=round(.83e9*factor*slowdown)))
    return cold,warm

out={}
for mode in ('null','slot_only','true','adverse_settled'):
    cold,warm=synthetic(mode);z=evaluate(plan,cold,warm);rows=z['comparisons'];m=[r for r in rows if 'p_exact'in r];settled=[r for r in rows if r['endpoint']=='settled'];assert all(r['paired_rows']==288 for r in settled)
    if mode in ('null','slot_only'):
        assert not z['primary_pass'] and all(r['p_exact']==1 and abs(r['paired_reduction_pct'])<1e-6 for r in m)
        assert all(abs(r['paired_reduction_pct'])<1e-6 and r['safety_pass'] for r in settled)
    else:
        assert z['primary_pass'] and all(r['at_least_extreme']==2 and r['assignments']==4096 and r['p_holm']==12/4096 for r in m)
        assert z['safety_pass']==(mode=='true') and all(r['safety_pass']==(mode=='true') for r in settled)
    out[mode]={'primary':z['primary_pass'],'safety':z['safety_pass'],'min_exact':min(r['p_exact'] for r in m),'settled_pass':all(r['safety_pass'] for r in settled)}
cold,warm=synthetic('null');warm[0],warm[1]=warm[1],warm[0]
try:read(plan,cold,warm)
except AssertionError:out['swapped_warm_rows_rejected']=True
else:raise AssertionError('corrupt warm ordering accepted')
print(json.dumps(out,sort_keys=True,indent=2))
