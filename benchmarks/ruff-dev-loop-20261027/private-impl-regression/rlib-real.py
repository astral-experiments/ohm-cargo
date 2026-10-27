"""Compile a real source edit, then edit an external caller and compare with an independent empty target."""
from pathlib import Path
import os,sys,json
studycase=sys.argv[1];N=int(sys.argv[2]);del sys.argv[1:3];mode='forwarding'
ordinary=Path(__file__).resolve().with_name('ordinary-rlib.py');s=ordinary.read_text()
sys.argv.insert(1,mode)
exec(compile(s.split('rec_list=[]')[0].replace('range(9)','range(N)').replace("if b and case!='exported_macro_ref'","if b and active_type"),str(ordinary),'exec'))
active_type='types' in studycase
orig_app=a.read_text()
def after_app(tag):
 return orig_app.replace('struct External;',f'struct External; #[derive(Debug)] struct {tag};').replace('bundle::nested(External','bundle::nested('+tag).replace('println!("{}",bundle::Public{x:7}.x);','println!("{}",bundle::Public{x:11}.x);')
def rosters(q):
 l=[]
 for f in q.glob('child.*.argv'):
  ar=[v.decode()for v in f.read_bytes().split(b'\0')if v];n=ar[ar.index('--crate-name')+1]
  if n!='___':l.append([n,any(x in ['link-only','-Zlink-only']for x in ar)])
 return sorted(l)
def emit(q):
 art=[]
 for line in (q/'stdout.jsonl').read_text().splitlines():
  msg=json.loads(line)
  if msg['reason']=='compiler-artifact':art.append(msg)
 return art
def operation(q,cold=False):
 original_target=env['CARGO_TARGET_DIR'];original_shared=env['CARGO_BUILD_BUILD_DIR']
 if cold:env.update(CARGO_TARGET_DIR=str(root/(q.name+'-target')),CARGO_BUILD_BUILD_DIR=str(root/(q.name+'-shared')))
 try:
  try:result,child=run(q,'app')
  except RuntimeError:
   st=(q/'stderr').read_text().splitlines()
   panic=next((st[i+1][:220] for i,l in enumerate(st) if 'panicked at' in l),None)
   info={'compiled':False,'panic':panic}
  else:
   exe=Path(result['app']['executable']);pr=sp.run([str(exe)],text=True,capture_output=True);info={'compiled':True,'output':pr.stdout.splitlines(),'exit':pr.returncode,'exe_sha256':sha(exe)}
  ar=emit(q)
  for unit in ('bundle','leaf'):
   matches=[f for u in ar if u['target']['name']==unit for f in u['filenames'] if f.endswith('.rmeta')]
   if matches:
    t=Path(matches[0]);shutil.copyfile(t,q/(unit+'.rmeta'));info[unit+'_rmeta']=sha(t)
  hs=list(Path(env['CARGO_TARGET_DIR']).rglob('lib-leaf.public-api-hash'));assert len(hs)==1
  info['public_hash']=json.loads(hs[0].read_bytes());info['actual_compilers']=rosters(q)
  return info
 finally:env.update(CARGO_TARGET_DIR=original_target,CARGO_BUILD_BUILD_DIR=original_shared)
obs=[]
for name,b,app_changed in [('prime',False,False),('edit_leaf',True,False),('edit_caller',True,True),('restore_leaf',False,True),('restore_caller',False,False)]:
 data=src(b).replace('#[cfg(all())]', '#[cfg(any())]') if 'files' not in studycase else src(b)
 if not leaf.exists() or leaf.read_text()!=data:leaf.write_text(data)
 txt=after_app('Distinct') if app_changed else orig_app
 if a.read_text()!=txt:a.write_text(txt)
 q=root/name;q.mkdir();warm=operation(q/'warm');gold=operation(q/(name+'-clean'),True) if name in ['edit_caller','restore_caller'] else None
 if gold:assert gold['compiled'] and gold['exit']==0,(name,gold)
 obs.append({'phase':name,'leaf_sha':sha(leaf),'app_sha':sha(a),'driver':sha(driver),'warm':warm,'clean':gold});(root/'natural.json').write_text(json.dumps(obs,indent=2)+'\n')
 print(name,warm['public_hash']['value'][:8],warm['actual_compilers'],warm['compiled'],str(warm.get('panic',''))[:60],flush=True)
