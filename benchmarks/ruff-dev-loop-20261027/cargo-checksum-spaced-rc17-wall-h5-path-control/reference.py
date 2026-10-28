"""Test typed comparison on two independently published external-machine workspace rosters."""
import json,tarfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from namespace import anchor,canonical,digest,encode
b,c=map(Path,sys.argv[1:]);report={}
for a,p in [('B',b),('C',c)]:
 with tarfile.open(p)as t:
  stdout=t.extractfile('workspace/call-3/stdout').read();raw=[json.loads(v) for v in stdout.splitlines()]
 units=[v for v in raw if v['reason']=='compiler-artifact'];assert len(units)==619
 keys=('package_id','manifest_path','target','profile','features','filenames','executable')
 rows=sorted(encode({k:u[k]for k in keys})for u in units)
 root='/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027/logical/ruff-target'
 ns,anc=anchor(root,rows);out,num=canonical(root,rows,ns)
 diag=sorted(encode(r)for r in raw if r['reason']=='compiler-message')
 report[a]={'namespace':ns,'anchors':anc,'exact_raw':digest(rows),'after_substitution':digest(out),'changed_path_fields':num,'diagnostics':digest(diag),'units':len(rows)}
 i=next(i for i,v in enumerate(rows)if 'libunicode_ident-' in v)
 item=json.loads(rows[i]);j=next(j for j,f in enumerate(item['filenames'])if 'libunicode_ident-'in f)
 original=item['filenames'][j];item['filenames'][j]=original+'.changed'
 others=list(rows);others[i]=encode(item);assert digest(canonical(root,others,ns)[0])!=digest(out)
 item=json.loads(rows[i]);item['manifest_path']=original;others[i]=encode(item);assert digest(canonical(root,others,ns)[0])!=digest(out)
 item=json.loads(rows[i]);item['filenames'][j]=original.replace(ns[1],'v2-0011223344556677');others[i]=encode(item)
 try:canonical(root,others,ns)
 except AssertionError:pass
 else:raise AssertionError('a second namespace was accepted')
assert report['B']['after_substitution']==report['C']['after_substitution'] and report['B']['exact_raw']!=report['C']['exact_raw'] and report['B']['diagnostics']==report['C']['diagnostics']
assert report['B']['namespace'][0]==report['C']['namespace'][0]
print(json.dumps(report,sort_keys=True,indent=2))
