"""Apply the small prospective screen gate to terminal registered instruction rows."""
import itertools,json,math,statistics,sys
from pathlib import Path
p=Path(__file__).resolve().parent;plan=json.loads((p/'screen-plan.json').read_bytes());rows=json.loads(Path(sys.argv[1]).read_bytes())
assert len(rows)==24
matched=[];positions=[]
for i,order in enumerate(plan['orders']):
    pair=rows[2*i:2*i+2];assert [r['arm'] for r in pair]==order and all(r['pair']==i and r['ir']>0 for r in pair)
    a,b=[r['ir'] for r in pair];positions.append(math.log(a)-math.log(b))
    costs={r['arm']:r['ir'] for r in pair};matched.append((costs['before'],costs['after']))
spreads=[a-b for a,b in matched];rates=[100*(a-b)/a for a,b in matched]
observed=sum(math.log(a)-math.log(b) for a,b in matched)
assignments=list(itertools.combinations(range(12),6))
randomization=sum(sum(v if j in s else -v for j,v in enumerate(positions))>=observed-1e-12 for s in assignments)/len(assignments)
savings=statistics.median(spreads)/plan['corpus_sweeps_per_command'];paired=statistics.median(rates);favorable=sum(s>0 for s in spreads)
print(json.dumps(dict(pairs=len(matched),favorable=favorable,paired_percent=paired,median_96_14_percent_interval=[sorted(rates)[2],sorted(rates)[-3]],per_sweep_instructions_saved=savings,paired_randomization_one_sided=randomization,threshold_pass=paired>=3 and favorable>=10 and randomization<=.01 and savings>=4000000,individual_percent=rates),indent=2))
