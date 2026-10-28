import collections,json,sys,statistics
from pathlib import Path
d=Path(sys.argv[1])
for root in [d/'ir-children-v2/rows',d/'history-v1/rows']:
    if not root.exists():continue
    print(root.parent.name)
    table={}
    for p in sorted(root.glob('*/edit/counts.json')):
        arg=p.parent.parent.name;raw=json.loads(p.read_bytes());table[arg]=raw
        print(arg,*(f'{k}={v["total"]/1e6:.2f}M' for k,v in sorted(raw.items())))
