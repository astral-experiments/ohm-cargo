"""Analyze complete ABBA/BAAB blocks at the unit of randomization."""
import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import statistics


def analyze(plan,rows):
    expected=[(b['case'],b['block'],b['order'],i,c) for b in plan['blocks'] for i,c in enumerate(b['order'])]
    assert [(r['case'],int(r['block']),r['order'],int(r['position']),r['arm']) for r in rows]==expected and len(rows)==96
    reports={};by_block=[]
    for case,n in [('private',8),('public',16)]:
        rows_c=[r for r in rows if r['case']==case];ds=[];parents=[];treatments=[]
        for b in range(1,n+1):
            group=[r for r in rows_c if int(r['block'])==b];assert len(group)==4 and ''.join(r['arm'] for r in group) in ('ABBA','BAAB');A=[int(r['elapsed_ns']) for r in group if r['arm']=='A'];B=[int(r['elapsed_ns']) for r in group if r['arm']=='B'];assert len(A)==len(B)==2;v=(sum(math.log(x) for x in A)-sum(math.log(y) for y in B))/2;ds.append(v);parents.extend(A);treatments.extend(B);by_block.append({'case':case,'block':b,'order':group[0]['order'],'mean_log_control_over_treatment':v,'elapsed_reduction_percent':100*(-math.expm1(-v))})
        obs=abs(sum(ds));extreme=sum(abs(sum(si*x for si,x in zip(sign,ds)))>=obs-1e-12 for sign in itertools.product((-1,1),repeat=n));reduce_sorted=sorted(100*(-math.expm1(-v)) for v in ds);rank=max(k for k in range(1,n//2+1) if 1-2*sum(math.comb(n,i) for i in range(k))/2**n>=.95);cover=1-2*sum(math.comb(n,i) for i in range(rank))/2**n
        reports[case]={'blocks':n,'scored_commands':4*n,'control_median_seconds':statistics.median(parents)/1e9,'treatment_median_seconds':statistics.median(treatments)/1e9,'median_block_reduction_percent':statistics.median(reduce_sorted),'distribution_free_median_interval_percent':[reduce_sorted[rank-1],reduce_sorted[-rank]],'interval_coverage':cover,'minmax_block_reduction_percent':[reduce_sorted[0],reduce_sorted[-1]],'favorable_blocks':sum(v>0 for v in ds),'extreme_orientations':extreme,'total_orientations':2**n,'exact_two_sided_p':extreme/2**n}
    maximum=0
    for i,k in enumerate(sorted(reports,key=lambda k:reports[k]['exact_two_sided_p'])):
        maximum=max(maximum,(2-i)*reports[k]['exact_two_sided_p']);reports[k]['two_endpoint_holm_p']=min(1,maximum)
    return reports,by_block


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',nargs='?',type=Path,default=Path(__file__).resolve().parent);a=p.parse_args();d=a.directory;plan=json.loads((d/'plan.json').read_text());rows=list(csv.DictReader((d/'observations.csv').open()));verify=list(csv.DictReader((d/'verification.csv').open()));assert len(verify)==len(rows)==96;check=json.loads((d/'completion.json').read_text());assert check['expected_scored_commands']==len(rows) and check['index']==plan['index']
    for r,v in zip(rows,verify):
        assert all(r[k]==v[k] for k in ('case','block','position','arm')) and v['graph']==plan['graph'] and v['before_fresh']==v['after_fresh']=='520';expected=(35 if r['case']=='public' or r['arm']=='A' else 1);assert int(r['rustcs'])==expected and int(r['one_thread'])+int(r['eight_threads'])==expected
    report,blocks=analyze(plan,rows);(d/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    with (d/'blocks.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=blocks[0]);w.writeheader();w.writerows(blocks)
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
