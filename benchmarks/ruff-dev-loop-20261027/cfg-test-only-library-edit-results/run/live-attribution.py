from pathlib import Path
import hashlib,json,sys
I=Path(__file__).resolve().parent;X=I.parent;Q=X/'cfg-library-first-v1-campaign';sys.path.insert(0,str(I));from wire import read
from compare import archive_diff
J=lambda p:json.loads(p.read_bytes());selector=J(I/'plan.json')['source_selection'];out={}
for mode in ('build','check','test'):
 vals={}
 for label in ('cold','edit','restore'):
  d=Q/'receipts'/mode/label;v='edited' if label=='edit' else 'original';src=Q/'fixture'/v/'docstring.rs'
  if not (d/'producer.json').is_file():continue
  a=J(d/'producer.json');native=next(x for x in a if not x['profile']['test']);fit=next((s for s in native['component_hashes'].values() if 'members' in s),None);q=d/'producer.rmeta';r={'source':v,'wire':read(q,src,'docstring.rs') if q.is_file() else None,'raw_changed_outputs':[p for p in J(d/'artifact-changes.json') if label!='cold'],'observed':J(d/'receipt.json')};lm=Q/'mixed-current-snapshots'/(mode+'-'+label+'.json');mix=J(lm) if lm.is_file() else None
  if mix:r['mixed']=[{'test':z['is_test'],'current':{Path(p).name:[f['phase_sha256'],f['retained']] for p,f in z['paths'].items()}} for z in mix['rows']]
  r['roles']=[(b['kind'],b['crate'],b['test']) for b in J(d/'processes.json')['typed'] if b['kind'].startswith('rustc') and label!='cold'];r['archive']=fit;vals[label]=r
 for a,b in [('cold','edit'),('edit','restore')]:
  if a not in vals or b not in vals:continue
  x,y=vals[a],vals[b];print(mode,a,b, 'source geometry',[(z['wire']['normalized_bytes'],z['wire']['lines']) if z['wire'] else None for z in (x,y)],'changed raw published',[(Path(p).name) for p in y['raw_changed_outputs']]);print('mixed',[q.get('mixed') for q in (x,y)])
  if x['archive'] and y['archive']:y['comparison_'+a]=archive_diff(x['archive'],y['archive'])
 out[mode]={n:{k:v for k,v in rec.items() if k!='archive'} for n,rec in vals.items()}
(Q/'live-pair-attribution.json').write_text(json.dumps(out,indent=1,sort_keys=True)+'\n')
