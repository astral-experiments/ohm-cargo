from pathlib import Path
import hashlib,importlib.util,json,statistics,sys
N=Path(__file__).resolve().parent
r=N/'ops/reference-analysis.py';sp=importlib.util.spec_from_file_location('reference',r);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def load(p):return json.loads(p.read_bytes())
def analyze(which):
    plan=load(N/'base-plan.json');orders=['FR' if x=='new-first' else 'RF' for x in plan[('primary' if which=='primary' else 'secondary')+'_orders']]
    raw=[]
    for i,o in enumerate(orders,1):
        pair={}
        for arm,tag in [('parent','R'),('child','F')]:
            d=N/'visits'/arm/(which+'-'+str(i).zfill(2)+'-dirty')
            assert load(d/'post.json')['typed_fresh']==285
            if which=='primary':pair[tag]=load(d/'instructions.json')['totals_ir']
            else:
                c=load(d/'clock.json');assert c['elapsed']==c['end']-c['start']>0 and c['status']==0;pair[tag]=c['elapsed']
        raw.append(pair)
    result=m.summarize(raw,orders,20261029,30000)
    n=len(orders);assert result['permutation_count']=={8:70,12:924}[n]
    clean={k:v for k,v in result.items() if k not in ('cached_median_seconds','full_median_seconds','paired_delta_seconds')}
    clean['metric']='parent-Cargo userspace Ir' if which=='primary' else 'whole command ns'
    clean.update(parent_median=statistics.median(x['R'] for x in raw),child_median=statistics.median(x['F'] for x in raw),median_raw_paired_difference=statistics.median(x['F']-x['R'] for x in raw),raw_pairs=raw,source_analysis_sha256=hashlib.sha256(r.read_bytes()).hexdigest(),orders=orders)
    clean['qualifying_reduction']=clean['upper95']<0 and clean['two_sided_balanced_p']<.05
    return clean
if __name__=='__main__':
    if sys.argv[1:] and sys.argv[1]=='--selftest':print(json.dumps(m.self_checks(),sort_keys=True))
    else:
        gate=load(N/'qualification/measurement-terminal.json');assert gate['primary_pairs']==8 and gate['wall_pairs']==12
        with (N/'results.json').open('x') as f:json.dump({k:analyze(k) for k in ('primary','wall')},f,sort_keys=True,indent=2);f.write('\n')
