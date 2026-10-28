from pathlib import Path
from statistics import median
import json,sys
p=Path(sys.argv[1])
for rd,l,r in [('ir-children-v2','B','C'),('history-v1','normal','forced')]:
 x={}
 for f in (p/rd).glob('rows/*/edit/counts.json'):
    idx,arm=f.parent.parent.name.split('-')
    x.setdefault(idx,{})[arm]=json.loads(f.read_bytes())
 if not x:continue
 for name in ['build_script_build','rustc:ty_vendored','rustc:ty_wasm']:
    vals=[(rr[l][name]['total'],rr[r][name]['total']) for rr in x.values() if l in rr and r in rr]
    if not vals:continue
    ratio=[100*(b/a-1) for a,b in vals];delta=[(b-a)/1e6 for a,b in vals]
    print(rd,name,len(vals),round(median(a for a,b in vals)/1e6,3),round(median(b for a,b in vals)/1e6,3),'delta',round(min(delta),3),round(median(delta),3),round(max(delta),3),'range%',round(min(ratio),3),round(max(ratio),3))
