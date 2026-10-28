"""Distinguish the new .025 significance rule with generated, balanced synthetic pairs."""
import collections
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from analysis import evaluate

def run():
    plan=json.loads((HERE/'plan.json').read_bytes());assert plan['alpha']==.025
    seen=collections.Counter();rows=[]
    for i,order in enumerate(plan['order'],1):
        seen[order]+=1
        ns={'B':100,'C':80} if seen[order]<=9 else {'B':80,'C':100}
        rows.append({'block':i,'order':order,'ns':ns})
    result=evaluate(plan,rows)
    assert result['favorable']==18 and result['ci95'][0]>1 and .025<result['p_two_sided']<.05 and not result['qualifies']
    return {'synthetic_only':True,'genuine_clocks':0,'favorable':result['favorable'],'ci95':result['ci95'],'p_two_sided':result['p_two_sided'],
            'required_p_below':.025,'nominal_interval_confidence':.95,'qualifies':result['qualifies']}
if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
