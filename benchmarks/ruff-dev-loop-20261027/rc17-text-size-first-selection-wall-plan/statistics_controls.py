"""Separate the exact-test, effect-size and favorable-pair gates on synthetic samples."""
from collections import Counter
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import checks as g
import analysis


def run():
    tests=analysis.selftests(g.P);special={}
    for kind in ('p_cut','size_cut','favorable_cut'):
        seen=Counter();rows=[]
        for i,order in enumerate(g.P['order'],1):
            seen[order]+=1
            if kind=='p_cut':ns={'B':100,'C':80} if seen[order]<=9 else {'B':80,'C':100}
            elif kind=='size_cut':ns={'B':10000,'C':9850}
            else:ns={'B':1000,'C':350 if seen[order]<=(8 if order=='BC' else 7) else 1001}
            rows.append(dict(block=i,order=order,ns=ns))
        special[kind]=analysis.evaluate(g.P,rows)
    assert all(not s['qualifies'] for s in special.values())
    p=special['p_cut'];assert .025<p['p_two_sided']<.05 and p['ci95'][0]>2 and p['favorable']>=16
    p=special['size_cut'];assert p['p_two_sided']<.025 and 1<p['ci95'][0]<2 and p['favorable']==24
    p=special['favorable_cut'];assert p['p_two_sided']<.025 and p['ci95'][0]>2 and p['favorable']==15
    return {k:{s:r[s] for s in ('favorable','ci95','p_two_sided','qualifies')} for k,r in (tests|special).items()}


if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True,indent=2))
