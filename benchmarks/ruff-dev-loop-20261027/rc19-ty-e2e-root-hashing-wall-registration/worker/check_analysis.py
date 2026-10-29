"""Check balance, the exact sign transformation, interval direction and null behavior on synthetic integers."""
from collections import Counter
from itertools import product,combinations
import json,math,random,statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import DESIGN,get
from analyze_wall import analyze

def run():
    order=get(DESIGN/'orders.json');seq=order['orders'];seed=order['bootstrap_seed']
    def trial(d):
        rows=[{'parent':10000000+73*i,'child':10000000+73*i+d*(100000+15367*i)}for i in range(32)]
        return analyze(rows,seq,seed)
    group=[]
    for d in (0,-1,1):
        r=trial(d);assert r['assignments']==1679616 and r['replicates']==30000;assert r['direction']=={0:'inconclusive',-1:'faster',1:'slower'}[d] and (r['two_sided_exact_p']==1 if d==0 else r['two_sided_exact_p']<.05)
        assert len(r['order_strata'])==2 and all(x['pairs']==16 for x in r['order_strata'].values())
        group.append({'case':d,'decision':r['direction'],'extreme':r['extreme'],'p':r['two_sided_exact_p'],'log_interval':r['interval_log']})
    print(json.dumps({'test':'only synthetic data','cases':group},sort_keys=True,indent=2))
if __name__=='__main__':run()
