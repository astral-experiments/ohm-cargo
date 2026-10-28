"""Rebuild one producer under the original full Cargo command, alternately preserving or emptying its own prior state."""
from pathlib import Path
import fcntl,json,os,shutil,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_data import call,external,go,git,H,sha,dig,guard,guard_source,read,put,p,q,w,s,t,seed,plan
assert (q/'complete.json').is_file()
job=next(j for j in read(q/'receipts/edited-ruff/jobs.json')if j['name']=='annotate_snippets')
argv=job['args'];out=Path(job['out_dir']);incroot=Path(next(v.removeprefix('incremental=')for v in argv if v.startswith('incremental=')))
inc,=incroot.glob('annotate_snippets-*');fprint=out.parent/'fingerprint';status=fprint/'lib-annotate_snippets'
assert out.parent.parent.name=='ruff_annotate_snippets'and incroot.is_relative_to(t)and status.is_file()
rlib,=out.glob('*.rlib');rmeta=rlib.with_suffix('.rmeta');dep,=out.glob('*.d')
assert all(z.is_relative_to(t)for z in (inc,out,status))
hold=t/'.isolated-annotate-svh-controls';hold.mkdir();audit=q/'producer-history';audit.mkdir();rows={}
schedule=[
 ('actual-original',False,'seed'),('actual-restored',False,'current'),
 ('warm-forced-restored',False,'warm-force'),('empty-original-1',False,'empty'),('empty-original-2',False,'empty'),
 ('original-to-edited',True,'natural'),('edited-to-original',False,'natural'),
 ('empty-edited-1',True,'empty'),('empty-edited-2',True,'empty'),('empty-original-3',False,'empty')]
put(audit/'design.json',{'plan':sha(q/'ops/plan.json'),'schedule':schedule,'argv':argv,'source_pin':plan['pin'],'initial_edit_and_restore_workspace_receipts':[sha(q/'receipts'/n/'result.json') for n in ('edited-ruff','restored-ruff')],'producer':[str(out),str(inc),str(fprint)],'conditioning':'Ordinary release -16 cargo build -p ruff --bin ruff for every active row with frozen full argv. Only the selected producer state is reserved/emptied. Registry and other Ruff dependency states persist. Warm forcing removes only successful Cargo fingerprint. No wall-time claim.'})
def record(tag,rev,md,lib,di,phasedir=None):
 dest=audit/tag;dest.mkdir();by={}
 for key,f in [('rmeta',md),('rlib',lib),('dep-info',di)]:
  cp=dest/('producer.'+key);shutil.copyfile(f,cp);by[key]={'logical':str(rmeta if key=='rmeta'else rlib if key=='rlib'else dep),'bytes':cp.stat().st_size,'sha':sha(cp)}
 hdr=go(['rustc','+ohm','-Zls=root',md]).stdout;(dest/'root.txt').write_bytes(hdr)
 import re
 ma=re.search(rb'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',hdr,re.M);assert ma
 current=plan['sha_edit'if rev else'sha_original'];assert all(sha(w/n)==v for n,v in current.items())
 source_manifest={str(f.relative_to(w)):sha(f) for f in sorted((w/'crates/ruff_annotate_snippets').rglob('*'))if f.is_file()}
 exs={k:sha(v['path'])for k,v in job['externs'].items()};assert exs=={k:v['after'][1]for k,v in job['externs'].items()}
 row={'tag':tag,'variant':'edited'if rev else'original','source_manifest_sha':H(json.dumps(source_manifest,sort_keys=True).encode()),'artifacts':by,'features':[v for i,v in enumerate(argv)if i and argv[i-1]=='--cfg'],'externs':exs,'private':ma[1].decode(),'stable_id':ma[2].decode(),'public':ma[3].decode(),'physical_origin':None if not phasedir else str(phasedir)}
 if phasedir:
  js=read(phasedir/'jobs.json');one,=[j for j in js if j['name']=='annotate_snippets'and j['kind']=='full'];assert one['args']==argv;row['native_counts']=read(phasedir/'result.json')['counts'];row['pid_trace']=one['raw_sha'];row['argv_sha']=one['argv_sha']
  arts=[v for l in(phasedir/'cargo.stdout').read_bytes().splitlines()if(v:=json.loads(l)).get('reason')=='compiler-artifact'];row['reader']=external(dest,lib,arts,rev)
 put(dest/'source-manifest.json',source_manifest);put(dest/'result.json',row);rows[tag]=row;print(tag,row['public'],row['private'],by['rmeta']['sha'][:12],row.get('native_counts'),flush=True)
with(p/'native-measure.lock').open('rb') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);guard_source(False);last=False
 for tag,rev,action in schedule:
  if rev!=last:go(['git','apply',*(['--reverse']if rev else[]),q/'ops/edit.patch']);last=rev
  guard_source(rev);guard()
  if action=='seed':
   a=seed/'target'/rmeta.relative_to(t);b=a.with_suffix('.rlib');d=a.parent/dep.name;oldrow=read(q/'receipts/original-ruff/result.json')['producer'];assert oldrow['rmeta'][1][1]==sha(a)and oldrow['rlib'][1][1]==sha(b);record(tag,rev,a,b,d);continue
  if action=='current':
   oldrow=read(q/'receipts/restored-ruff/result.json')['producer'];assert oldrow['rmeta'][1][1]==sha(rmeta)and oldrow['rlib'][1][1]==sha(rlib);record(tag,rev,rmeta,rlib,dep);continue
  prior=hold/tag;prior.mkdir()
  if action=='warm-force':status.rename(prior/status.name)
  elif action=='empty':
   assert inc.is_dir()and out.is_dir()and fprint.is_dir()
   for f in [inc,out,fprint]:f.rename(prior/f.name);assert not f.exists()
  row=call('history-'+tag,'ruff',rev);ph=q/'receipts'/('history-'+tag+'-ruff')
  record(tag,rev,rmeta,rlib,dep,ph)
 assert not last;guard_source(False);put(audit/'complete.json',{'rows':len(rows),'physical_compiler_rows':sum('argv_sha'in v for v in rows.values()),'rows_sha':{k:sha(audit/k/'result.json')for k in rows}});print('all natural controls complete',flush=True)
