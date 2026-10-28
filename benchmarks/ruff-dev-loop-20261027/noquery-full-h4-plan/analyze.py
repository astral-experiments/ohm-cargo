"""Conditional two-sided tests and per-history bootstrap estimates for prespecified Ruff commands."""
from collections import Counter,defaultdict
from itertools import product
from pathlib import Path
import csv,json,math,random,statistics,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from design import ARMS,HISTORIES,WAVES,schedule


def read(plan,cold,warm):
    assert plan['histories']==schedule() and len(cold)==HISTORIES*4 and len(warm)==HISTORIES*WAVES*4
    initial=iter(cold);later=iter(warm);states=[]
    for h in plan['histories']:
        idx=h['history'];obs={p:{} for p in ('cold','first','cycle','immediate_settled')}; waves=[]
        for pos,arm in enumerate(h['cold_order'],1):
            row=next(initial);assert (int(row['history']),int(row['position']),row['arm'])==(idx,pos,arm)
            for p in ('cold','first','immediate_settled'):
                ns=int(row[p+'_ns']);assert ns>0;obs[p][arm]=ns*1e-9
            obs['cycle'][arm]=(int(row['cold_ns'])+int(row['first_ns']))*1e-9
        for wave,order in enumerate(h['settled_orders'],1):
            times={}
            for pos,arm in enumerate(order,1):
                row=next(later);assert (int(row['history']),int(row['wave']),int(row['position']),row['arm'])==(idx,wave,pos,arm)
                ns=int(row['elapsed_ns']);assert ns>0;times[arm]=ns*1e-9
            waves.append(times)
        states.append((obs,waves))
    assert next(initial,None) is None and next(later,None) is None
    return states


def permutation(orders,control,observations):
    third,fourth=sorted(set(ARMS)-{'C',control});groups=defaultdict(list)
    for o,row in zip(orders,observations,strict=True):
        a,b=[n for n in o if n in ('C',control)];groups[o.index(third),o.index(fourth)].append((math.log(row[b]/row[a]),b=='C'))
    assert len(groups)==12 and all(len(vals)==2 and sum(l for _,l in vals)==1 for vals in groups.values())
    terms=[(x[0][0]-x[1][0],x[0][1]) for x in groups.values()]
    observed=abs(math.fsum(math.log(x['C']/x[control]) for x in observations));assert math.isclose(observed,abs(math.fsum(v if later else -v for v,later in terms)),abs_tol=1.e-11)
    limit=2**12;extreme=sum(abs(math.fsum(z))>=observed-1e-12 for z in product(*[(v,-v) for v,_ in terms]));assert extreme>=2
    return extreme,limit


def estimate(group,ctrl,phase,rngseed):
    allrows=[x for history in group for x in history]
    ratios=[statistics.fmean(math.log(x['C']/x[ctrl]) for x in history) for history in group]
    diff=[statistics.fmean(x['C']-x[ctrl] for x in history) for history in group]
    rng=random.Random(rngseed);logged=[];absolute=[]
    for _ in range(20000):
        sel=rng.choices(range(HISTORIES),k=HISTORIES)
        logged.append(100*math.expm1(statistics.fmean(ratios[i] for i in sel)))
        absolute.append(1000*statistics.fmean(diff[i] for i in sel))
    logged.sort();absolute.sort()
    return {'endpoint':phase,'control_arm':ctrl,'candidate_arm':'C','cold_histories':HISTORIES,'paired_rows':len(allrows),
      'per_arm_median_s':{a:statistics.median(x[a] for x in allrows) for a in (ctrl,'C')},
      'paired_reduction_pct':-100*math.expm1(statistics.fmean(ratios)),'paired_mean_overhead_ms':1000*statistics.fmean(diff),
      'ci95_reduction_pct':[-logged[19500],-logged[499]],'upper98_75_overhead_pct':logged[19750],
      'upper98_75_overhead_ms':absolute[19750],'histories_favoring_candidate':sum(v<0 for v in ratios)}


def evaluate(plan,cold,warm):
    states=read(plan,cold,warm);orders=[h['cold_order'] for h in plan['histories']];rows=[]
    for i,ph in enumerate(('cold','first','cycle','settled','immediate_settled')):
        for j,ctrl in enumerate('OAB'):
            groups=[s[1] if ph=='settled' else [s[0][ph]] for s in states]
            row=estimate(groups,ctrl,ph,202610280900+i*3+j)
            if ph in ('first','cycle'):
                count,n=permutation(orders,ctrl,[a[0] for a in groups]);row.update({'p_exact':count/n,'at_least_extreme':count,'assignments':n})
            elif ph=='cold':row['safety_pass']=row['upper98_75_overhead_pct']<3
            elif ph=='settled':row['safety_pass']=row['upper98_75_overhead_pct']<5 and row['upper98_75_overhead_ms']<100
            rows.append(row)
    effects=[r for r in rows if 'p_exact' in r];actionable=[r for r in rows if 'safety_pass' in r];assert len(effects)==len(actionable)==6
    adjusted=0
    for n,r in enumerate(sorted(effects,key=lambda d:d['p_exact'])):
        adjusted=max(adjusted,min(1,(6-n)*r['p_exact']));r['p_holm']=adjusted;r['effect_pass']=adjusted<.05 and r['ci95_reduction_pct'][0]>0
    return {'cold_histories':HISTORIES,'cold_states':HISTORIES*4,'ordinary_commands':HISTORIES*4*(3+WAVES),'comparisons':rows,
       'primary_pass':all(r['effect_pass'] for r in effects),'safety_pass':all(r['safety_pass'] for r in actionable)}

if __name__=='__main__':
    read_csv=lambda p:list(csv.DictReader(Path(p).read_text().splitlines()))
    print(json.dumps(evaluate(json.loads(Path(sys.argv[1]).read_bytes()),read_csv(sys.argv[2]),read_csv(sys.argv[3])),sort_keys=True,indent=2))
