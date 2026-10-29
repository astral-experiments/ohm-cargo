"""Balance the three arm positions inside each edit direction without using observed effects."""
import itertools
import json
from pathlib import Path
import random

root=Path(__file__).resolve().parent
perms=[''.join(p) for p in itertools.permutations('SAC')]
cyclic=['SAC','ACS','CSA']
reverse=[p for p in perms if p not in cyclic]
assert len(reverse)==3
orders={}
for host,seed in [('one',0x1E928710),('two',0x1E928729)]:
    rng=random.Random(seed);rows=[]
    for block in range(4):
        p=cyclic[:] if block%2==0 else reverse[:]
        h=reverse[:] if block%2==0 else cyclic[:]
        rng.shuffle(p);rng.shuffle(h)
        for j in range(3):
            for revision,order in [('parent',p[j]),('historical',h[j])]:
                rows.append(dict(index=len(rows)+1,block=block+1,direction=revision,order=order))
    orders[host]=rows
with (root/'order.json').open('x') as f:json.dump(orders,f,sort_keys=True,indent=2);f.write('\n')

