"""Validate the complete assignment and calculate paired, order-conditioned confidence tests."""
import argparse, collections, csv, hashlib, itertools, json, math, statistics
from pathlib import Path

def sign(x):
    return (x>0)-(x<0)

def two_sided_sign(wins,losses):
    n=wins+losses
    return min(1,2*sum(math.comb(n,j) for j in range(min(wins,losses)+1))/2**n) if n else 1

def signed_histogram(values,base_first):
    plus=values.count(1); minus=values.count(-1); zero=values.count(0)
    out=collections.Counter()
    for p in range(plus+1):
        for m in range(minus+1):
            z=base_first-p-m
            if not 0<=z<=zero:continue
            out[2*(p+minus-m)-plus-minus]+=math.comb(plus,p)*math.comb(minus,m)*math.comb(zero,z)
    assert sum(out.values())==math.comb(len(values),base_first)
    return out

def median_interval(values):
    vals=sorted(values); n=len(vals)
    accepted=[(k,1-2*sum(math.comb(n,j) for j in range(k))/2**n) for k in range(1,(n+1)//2+1)]
    if not any(coverage>=.95 for k,coverage in accepted):
        return {'lower':None,'upper':None,'coverage':None}
    k,coverage=next((k,c) for k,c in reversed(accepted) if c>=.95)
    return dict(lower=vals[k-1],upper=vals[n-k],coverage=coverage,lower_rank=k)

def compare(blocks,base,treatment):
    strata=collections.defaultdict(list);base_times=[];treatment_times=[];improvements=[];savings=[];positions=collections.defaultdict(list)
    for rows in blocks:
        by_arm={r['arm']:r for r in rows}
        b=by_arm[base];v=by_arm[treatment]
        bt=int(b['elapsed_ns']);vt=int(v['elapsed_ns'])
        assert min(bt,vt)>0
        base_times.append(bt/1e9);treatment_times.append(vt/1e9)
        pct=100*(bt-vt)/bt
        improvements.append(pct);savings.append((bt-vt)/1e6)
        bfirst=int(b['rank'])<int(v['rank'])
        positions['base-first' if bfirst else 'treatment-first'].append(pct)
        others=tuple((i,r['arm']) for i,r in enumerate(rows) if r['arm'] not in {base,treatment})
        strata[others].append((sign(bt-vt) if bfirst else sign(vt-bt),bfirst))
    wins=sum(v>0 for v in savings);losses=sum(v<0 for v in savings)
    observed=wins-losses;full=collections.Counter({0:1})
    for trials in strata.values():
        first=sum(flag for _,flag in trials)
        assert first*2==len(trials),(len(trials),first)
        local=signed_histogram([s for s,_ in trials],first)
        new=collections.Counter()
        for a,m in full.items():
            for b,n in local.items():new[a+b]+=n*m
        full=new
    total=sum(full.values());extreme=sum(m for score,m in full.items() if abs(score)>=abs(observed))
    return dict(control=base,treatment=treatment,n=len(blocks),wins=wins,losses=losses,ties=len(blocks)-wins-losses,
                control_median_sec=statistics.median(base_times),treatment_median_sec=statistics.median(treatment_times),
                median_saved_ms=statistics.median(savings),median_saved_pct=statistics.median(improvements),
                median_saved_pct_interval=median_interval(improvements),median_saved_ms_interval=median_interval(savings),
                median_saved_pct_by_order={k:statistics.median(v) for k,v in positions.items()},
                exact_two_sided_sign_p=two_sided_sign(wins,losses),
                conditional_two_sided_p=extreme/total,conditional_extreme=extreme,possible_assignments=total,
                permutation_strata=len(strata))

def validate(folder,schedule):
    csvfile=folder/'timings.csv'
    done=json.loads((folder/'done.json').read_text())
    assert hashlib.sha256(csvfile.read_bytes()).hexdigest()==done['rows']
    with csvfile.open() as f:rows=list(csv.DictReader(f))
    blocks=[];index=0;sources=set()
    for number,item in enumerate(schedule):
        n=len(item['order']); block=rows[index:index+n];index+=n
        assert [r['arm'] for r in block]==item['order']
        assert [int(r['rank']) for r in block]==list(range(n))
        assert all(int(r['block'])==number and r['literal']==item['literal'] for r in block)
        hashes={r['source_sha256'] for r in block}
        assert len(hashes)==1 and not sources&hashes
        sources|=hashes
        blocks.append(block)
    assert index==len(rows)
    return blocks

def test():
    vals=[1,-1,0,1,-1,-1]
    for k in range(len(vals)+1):
        brute=collections.Counter(sum(v if i in subset else -v for i,v in enumerate(vals))
                                  for subset in itertools.combinations(range(len(vals)),k))
        assert brute==signed_histogram(vals,k)
    for w,l,p in [(0,0,1),(3,0,.25),(2,2,1),(8,0,2/256)]:assert two_sided_sign(w,l)==p
    assert median_interval(list(range(1,25)))['lower_rank']==7
    orders=list(itertools.permutations(['base','shipped','stack','refresh']))
    blocks=[[dict(arm=arm,rank=i,elapsed_ns=(100 if arm=='refresh' else 200)) for i,arm in enumerate(order)] for order in orders]
    strongest=compare(blocks,'stack','refresh')
    assert strongest['wins']==24 and strongest['conditional_two_sided_p']==2/4096
    assert compare(blocks,'shipped','base')['conditional_two_sided_p']==1

def main():
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path,nargs='?');p.add_argument('folder',type=Path,nargs='?');p.add_argument('--self-test',action='store_true');args=p.parse_args()
    test()
    if args.self_test:return
    plan=json.loads(args.plan.read_text())
    result={}
    adjacent={'stack-vs-shipped':('shipped','stack'),'stack-vs-base':('base','stack'),'refresh-vs-stack':('stack','refresh'),'refresh-vs-shipped':('shipped','refresh')}
    for cohort,cfg in plan['cohorts'].items():
        result[cohort]={}
        for ep,schedule in cfg['endpoints'].items():
            folder=args.folder/cohort/ep
            if not (folder/'done.json').exists():continue
            rows=validate(folder,schedule);avail={r['arm'] for r in rows[0]}
            comparisons={k:compare(rows,a,b) for k,(a,b) in adjacent.items() if {a,b}<=avail}
            if len(avail)==2 and not comparisons:
                a,b=plan['arms'];comparisons[b+'-vs-'+a]=compare(rows,a,b)
            result[cohort][ep]=comparisons
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
