from pathlib import Path
import hashlib,json,sys,os,shutil,time
I=Path(__file__).resolve().parent;X=I.parent;Q=X/'cfg-library-first-v1-campaign';T=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target');SH=T.parent/'shared';O=Q/'mixed-current-snapshots';O.mkdir(exist_ok=True);cache=O/'content';cache.mkdir(exist_ok=True);done=set();md5s={k:hashlib.md5((Q/'fixture'/k/'docstring.rs').read_bytes()).digest() for k in ('original','edited')}
sys.path.insert(0,str(I));from artifacts import archive,metadata
J=lambda p:json.loads(p.read_bytes())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def physical(p,m):
 p=Path(p);base=(Q if m!='test' else Path('/dev/shm/ohm-cfg-library-first-v1'))/'state'/m;root=T if p.is_relative_to(T) else SH;assert p.is_relative_to(root);return base/('target' if root==T else 'shared')/p.relative_to(root)
def capture():
 for stub in (Q/'receipts').glob('*/*/receipt.json'):
  if stub in done or stub.parent.name not in ('cold','edit','restore'):continue
  d=stub.parent;m=d.parent.name;src=J(stub)['view'];a=[json.loads(b) for b in (d/'stdout').read_bytes().splitlines()];known=J(d/'artifact-state.json');inv=J(d/'processes.json')['typed'];rows=[]
  for j in a:
   if j.get('reason')!='compiler-artifact' or j['target']['name']!='ty_wasm' or j['target']['kind'] not in (['rlib','cdylib'],['cdylib','rlib'],['lib']):continue
   r={'target':j['target'],'is_test':j['profile']['test'],'features':j['features'],'cargo_fresh':j['fresh'],'paths':{}}
   for raw in j['filenames']:
    p=physical(raw,m);rec=known[raw];h=rec.get('sha256');facts={'phase_sha256':h,'phase_bytes':rec.get('facts',[None]*3)[2],'retained':False};r['paths'][raw]=facts
    if not h:continue
    dest=cache/(h+p.suffix)
    if not dest.exists() and p.is_file() and sha(p)==h:
     t=cache/(h+'.tmp');shutil.copyfile(p,t)
     if sha(t)==h:t.rename(dest)
     else:t.unlink()
    if dest.is_file() and sha(dest)==h:facts['retained']=True
    facts['saved_path']=dest.name if facts['retained'] else None
   rows.append(r)
  rustc=[{k:r.get(k) for k in ('kind','pid','argv','test','exec_sha256','image_sha256')} for r in inv if r['crate']=='ty_wasm'];wild=[{k:r.get(k) for k in ('kind','pid','link_output','argv','exec_sha256','image_sha256')} for r in inv if r['kind']=='wild' and r['link_output'] and 'ty_wasm' in r['link_output']];(O/(m+'-'+d.name+'.json')).write_text(json.dumps({'rows':rows,'ty_wasm_actual_rustc':rustc,'matched_name_wild':wild,'record_sha256':sha(stub),'source_state':src},sort_keys=True,indent=1)+'\n');done.add(stub)
while not (Q/'complete.json').is_file() and not any(Q.glob('failure-*.txt')):
 capture();time.sleep(.35)
capture();print('completed',len(done),flush=True);(O/'complete.json').write_text(json.dumps({'parsed':len(done),'retained_bytes':sum(p.stat().st_size for p in cache.glob('*'))}))
