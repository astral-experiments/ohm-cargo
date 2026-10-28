import json,sys
from pathlib import Path
d=Path(sys.argv[1])
for e in sorted(d.glob('rows/*/edit')):
    if not (e/'counts.json').exists():continue
    for f in e.glob('*-rustc.count'):
        args=f.with_suffix('.args').read_bytes().split(b'\0');c=args[args.index(b'--crate-name')+1]
        if c!=b'ty_wasm':continue
        data=[(int(t[1]),int(t[2]),int(t[3])/1e6) for row in f.read_text().splitlines() if (t:=row.split())[0]=='F']
        ts=list(sorted((r[2] for r in data),reverse=True))
        print(e.parent.name,len(ts),round(sum(ts),1),'main',round(sum(r[2] for r in data if r[0]==r[1]),1),'top8',list(map(lambda x:round(x,1),ts[:8])),'next',round(sum(ts[8:]),1))
