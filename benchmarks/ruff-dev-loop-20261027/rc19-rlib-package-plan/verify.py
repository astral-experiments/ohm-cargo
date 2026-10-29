from pathlib import Path
import copy
import json
import runpy
d=Path(__file__).resolve().parent
score=runpy.run_path(str(d/'score.py'))['score']
orders=json.loads((d/'order.json').read_bytes())
assert len(orders)==2 and orders['one']!=orders['two']
for schedule in orders.values():
    rows=[dict(r,valid=True,arms={arm:{phase:{'exit':0,'ns':ns} for phase in ('edit','repeat')} for arm,ns in [('S',1000),('A',1000),('C',900)]}) for r in schedule]
    assert score(schedule,rows)['qualified_mechanism_on_host']
    slower=copy.deepcopy(rows)
    for row in slower:row['arms']['C']['edit']['ns']=1500
    assert not score(schedule,slower)['qualified_mechanism_on_host']
    broken=copy.deepcopy(rows);broken[-1]['valid']=False
    try:score(schedule,broken)
    except AssertionError:pass
    else:raise AssertionError('accepted an invalid triplet')
    try:score(schedule,rows[:-1])
    except AssertionError:pass
    else:raise AssertionError('accepted a partial cohort')
print('Both counterbalanced 24-triplet rosters and positive/negative scoring controls passed.')

