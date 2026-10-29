import hashlib
import json
import random
from pathlib import Path

p=Path(__file__).resolve().parent
rng=random.Random(0x202610292581)
labels=['formatter','linter','parser']
orders={name:[] for name in labels}
for label in labels:
    for _ in range(3):
        part=[0,0,1,1]
        rng.shuffle(part)
        orders[label].extend(part)
rows=[]
for idx in range(12):
    seq=labels.copy();rng.shuffle(seq)
    for label in seq:
        seq2=['normal','cow'] if not orders[label][idx] else ['cow','normal']
        rows.append(dict(pair=idx,library=label,order=seq2))
plan={'purpose':'standalone real GNU rlib writer feasibility on private Btrfs','labels':labels,'rows':rows,
      'scoring':'per-library median of paired (normal-cow)/normal; raw medians; sign and block bootstrap by three blocks of four equal-order pairs; never a Cargo end-to-end performance claim',
      'admission':'all ext4 and Btrfs native oracles and hostile controls; actual shared extents; prior artifact supplied before invocation',
      'decision':'extend only with a real reachable earlier archive and a materially favorable whole-writer effect. A candidate PR additionally requires replicated statistically significant ordinary Cargo build measurements.'}
with (p/'order.json').open('x') as f:
    json.dump(plan,f,sort_keys=True,indent=2);f.write('\n')
print(hashlib.sha256((p/'order.json').read_bytes()).hexdigest())

