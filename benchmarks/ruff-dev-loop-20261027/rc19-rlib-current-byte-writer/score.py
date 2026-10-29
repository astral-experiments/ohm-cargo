"""Validate the order, raw output reports and fixture commitments, then summarize terminal pairs."""
from collections import Counter
from itertools import product
import hashlib
import json
from math import comb
from pathlib import Path
import statistics
import sys

def calculate(root):
    load=lambda p:json.loads((root/p).read_bytes())
    ready=load('order.json');rows=load('terminal/trial-btrfs-first/pairs.json')
    assert hashlib.sha256((root/'order.json').read_bytes()).hexdigest()=='cede7a4cb6a08977274c1ad97651eea6e54620a5ac16730c6690c659c6b3262c'
    assert len(rows)==len(ready['rows'])==36 and [{k:r[k] for k in ('pair','library','order')} for r in rows]==ready['rows']
    prior=load('terminal/members/provenance.json')
    checks={key:load(f'terminal/trial-{key}-first/controls.json') for key in ('ext4','btrfs')}
    for kind,c in checks.items():
        assert (root/f'terminal/trial-{kind}-first/exit').read_text()=='0\n'
        assert (root/f'terminal/trial-{kind}-first/stderr').stat().st_size==0
        assert len(c)==17 and all((v['exit']!=0)==(k in ('before-rename','limited-write')) for k,v in c.items())
        assert all(not c[k]['cloned'] for k in ('no-incumbent','fifo','symlink','socket'))
    results={}
    for label in ready['labels']:
        v=[r for r in rows if r['library']==label]
        assert [r['pair'] for r in v]==list(range(12))
        assert all(Counter(tuple(r['order']) for r in v[i:i+4])=={('normal','cow'):2,('cow','normal'):2} for i in range(0,12,4))
        size=prior[label]['size']
        b=[r['measurements']['normal'] for r in v];t=[r['measurements']['cow'] for r in v]
        assert all(r['exit']==0 and r['length']==size for r in b+t)
        assert all(not r['cloned'] and r['retained']==r['fallback']==0 for r in b)
        assert all(r['cloned'] and r['fallback']==0 for r in t) and len({r['retained'] for r in t})==1
        a,z=[r['ns'] for r in b],[r['ns'] for r in t]
        effects=[100*(x-y)/x for x,y in zip(a,z)]
        blocks=[effects[i:i+4] for i in range(0,12,4)]
        boot=sorted(statistics.median([x for group in sel for x in blocks[group]]) for sel in product(range(3),repeat=3))
        def pct(p):
            off=(len(boot)-1)*p;lo=int(off);return boot[lo]+(boot[min(lo+1,len(boot)-1)]-boot[lo])*(off-lo)
        wins=sum(x>0 for x in effects);loss=sum(x<0 for x in effects)
        p=min(1,2*sum(comb(wins+loss,k) for k in range(min(wins,loss)+1))/2**(wins+loss))
        ctrl=checks['btrfs'][label+'-cow'];assert ctrl['retained']==t[0]['retained'] and ctrl['shared_physical_bytes']>0
        results[label]=dict(normal_ms=statistics.median(a)/1e6,cow_ms=statistics.median(z)/1e6,paired_reduction_percent=statistics.median(effects),
                            bootstrap_interval=[pct(.025),pct(.975)],positive=wins,sign_two_sided=p,size=size,retained=ctrl['retained'],
                            shared_physical=ctrl['shared_physical_bytes'],objects=prior[label]['objects'],written_by_candidate=size-ctrl['retained'])
    return results

if __name__=='__main__':
    values=calculate(Path(__file__).resolve().parent)
    print(json.dumps(values,sort_keys=True,indent=2))

