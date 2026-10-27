from pathlib import Path
import hashlib,json,sys
r=Path(__file__).resolve().parent;sys.path.insert(0,str(r));from analyze import evaluate
p=json.loads((r/'plan.json').read_bytes());assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in p['scripts'].items())
val={}
for case in ('no-effect','slot-only','known-improvement','known-regression'):
    rows=[]
    for n,order in enumerate(p['orders'],1):
        if case=='no-effect':ns={'B':100,'C':100}
        elif case=='slot-only':ns={order[0]:100,order[1]:115}
        elif case=='known-improvement':ns={'B':100,'C':84}
        else:ns={'B':100,'C':118}
        rows.append(dict(order=order,ns=ns,block=n))
    out=evaluate(p,rows);assert out['qualifies']==(case=='known-improvement')
    expect=1 if case in ('no-effect','slot-only') else 2/924;assert out['p_exact_two_sided']==expect;val[case]=expect
print(json.dumps({'pairs':len(p['orders']),'controls':val,'bound_files':len(p['scripts'])},sort_keys=True))
