from pathlib import Path
import json,sys
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');sys.argv=['whole-paths.py','h8','qualify'];g={};source=(H/'whole-paths.py').read_text();exec(compile(source[:source.rindex('os.umask(0o077)')],str(H/'whole-paths.py'),'exec'),g)
A={}
actual_proofs=g['proofs']()
for mode in ('workspace','test'):
 root=H/'qualified-whole-v1'/mode;a=json.loads((root/'qual/anchor.json').read_text())
 blobs=g['contents']([Path(p) for p in a['dot_d']]);ps=g['stamps']([Path(p) for p in a['products']]);expected=set(a['dot_d']);found=set(map(str,g['depfiles'](mode)))
 A[mode]=dict(qualification_anchor=g['sha'](root/'qual/anchor.json'),changed_dot_d=[n for n,d in blobs.items() if a['dot_d'][n]!=d],missing=list(expected-found),added=list(found-expected),changed_product_stamps={p:{'expected':a['product_stamps'][p],'actual':v} for p,v in ps.items() if a['product_stamps'][p]!=v},proof_native=a['proofs'],proof_now=actual_proofs,scored_rows=len(list(root.glob('ir/*/record.json')))+len(list(root.glob('wall/*/record.json'))))
 for scope in ('workspace','test'):
  if scope==mode:continue
  other=json.loads((H/'qualified-whole-v1'/scope/'qual/anchor.json').read_text())['proofs']
  A[mode]['current_is_other_qualified_proof']=(other==actual_proofs)
out=H/'rejected-v1-diagnostic.json';out.write_text(json.dumps(A,indent=2,sort_keys=True)+'\n');print(json.dumps({k:{i:(len(x) if i in ['changed_product_stamps'] else x) for i,x in v.items()} for k,v in A.items()},indent=2))
