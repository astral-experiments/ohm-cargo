"""Check complete per-thread counts and regenerate paired intrinsic overhead."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys

p=Path(sys.argv[1])
rows=json.loads((p/'observations.json').read_bytes())
assert len(rows)==16
for row in rows:
    d=p/('{mode}-{pair:02}-{arm}'.format(**row))
    assert json.loads((d/'receipt.json').read_bytes())==row
    lines=[s.split() for s in (d/'rustc.ir').read_text().splitlines()]
    pid=lines[0][1]
    assert lines[0]==['B',pid,'0','0'] and lines[-1]==['P',pid,'0','0'] and all(s[1]==pid for s in lines)
    assert Counter(s[2] for s in lines if s[0]=='T')==Counter(s[2] for s in lines if s[0]=='F')
    assert sum(int(s[3]) for s in lines if s[0]=='F')==row['instructions']
report={}
for mode in ('check','build'):
    pairs=[{r['arm']:r['instructions'] for r in rows if r['mode']==mode and r['pair']==i} for i in range(1,5)]
    report[mode]={'pairs':pairs,'paired_median_overhead_pct':statistics.median(100*(pair['candidate']/pair['parent']-1) for pair in pairs)}
assert report==json.loads((p/'summary.json').read_bytes())
print(json.dumps(report,indent=2,sort_keys=True))
