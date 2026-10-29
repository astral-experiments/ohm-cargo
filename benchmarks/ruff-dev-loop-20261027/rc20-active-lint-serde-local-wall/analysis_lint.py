"""Recompute paired saving for each CLI, direction and arm order from elapsed nanoseconds."""
import itertools,random,statistics,math
def q(values,p):
    x=(len(values)-1)*p
    lo=math.floor(x)
    return values[lo]+(x-lo)*(values[math.ceil(x)]-values[lo])
def describe(rows):
    med=statistics.median
    ds=[(r['A']-r['B'])/1e6 for r in rows]
    pc=[100*(r['A']-r['B'])/r['A'] for r in rows]
    n=sum(d!=0 for d in ds);w=sum(d>0 for d in ds)
    sign=min(1.,2*sum(math.comb(n,i) for i in range(min(w,n-w)+1))/2**n)
    return dict(n=len(rows),A_ms=med([r['A'] for r in rows])/1e6,B_ms=med([r['B'] for r in rows])/1e6,ms=med(ds),pct=med(pc),wins=w,ties=len(ds)-n,p=sign)
def interval(rows,seed,plan):
    directions=sorted({r['direction'] for r in rows})
    groups=[[r for r in rows if (r['direction'],r['order'])==(d,o)] for d,o in itertools.product(directions,('AB','BA'))]
    assert all(len(g)==8 for g in groups)
    rng=random.Random(seed);pc=[];ms=[]
    groups=[[(100*(r['A']-r['B'])/r['A'],(r['A']-r['B'])/1e6)for r in g]for g in groups]
    for _ in range(plan['bootstrap']):
        draw=[x for g in groups for x in rng.choices(g,k=len(g))]
        v,m=zip(*draw);pc.append(statistics.median(v));ms.append(statistics.median(m))
    pc.sort();ms.sort()
    return dict(**describe(rows),ci_pct=[q(pc,p) for p in (.025,.975)],ci_ms=[q(ms,p) for p in (.025,.975)])
def all_results(measurements,plan):
    result={};p={}
    for ix,s in enumerate(('check','build','serde')):
        r=measurements.get(s)
        if r is None:
            p[s]=1;continue
        assert len(r)==32 and [v['pair'] for v in r]==list(range(1,33))
        for a,b in zip(r,plan['schedule'][s]):
            assert all(a[k]==b[k] for k in ('pair','direction','order'))
        result[s]={}
        for j,e in enumerate(('edit','repeat','combined')):
            rr=[]
            for a in r:
                row={k:a[k]for k in ('pair','order','direction')}
                for t in 'AB':
                    z=a['arms'][t];row[t]=z['edit']['ns']+z['repeat']['ns'] if e=='combined' else z[e]['ns']
                rr.append(row)
            seed=plan['interval_seed']+100*ix+j
            value=interval(rr,seed,plan)
            value['direction']={d:interval([a for a in rr if a['direction']==d],seed+10*(i+1),plan)for i,d in enumerate(('reverse','restore'))}
            value['order']={o:describe([a for a in rr if a['order']==o])for o in ('AB','BA')}
            value['four_way']={d+'-'+o:describe([a for a in rr if (a['direction'],a['order'])==(d,o)])for d,o in itertools.product(('reverse','restore'),('AB','BA'))}
            fn=lambda row:(row['A']-row['B'])/row['A']
            value['most_adverse_pct']=min(rr,key=fn);value['most_favorable_pct']=max(rr,key=fn)
            value['most_adverse_ms']=min(rr,key=lambda row:row['A']-row['B'])
            result[s][e]=value
        p[s]=result[s]['combined']['p']
    last=0
    for i,s in enumerate(sorted(p,key=p.get)):
        last=max(last,min(1,p[s]*(len(p)-i)))
        if s not in result:continue
        r=result[s];r['primary_holm']=last;r['primary_pass']=r['combined']['ci_pct'][0]>0 and last<.05
        rep=r['repeat'];r['repeat_guard']=rep['ci_pct'][0]>=-plan['guard']['max_pct_regression'] and rep['ci_ms'][0]>=-plan['guard']['max_ms_regression']
        r['wall_claim']=r['primary_pass'] and r['repeat_guard']
    return result
