"""Capture immediate query readers and their own fingerprints at the same two H5 endpoints."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,subprocess,time,traceback,sys
root=Path(__file__).resolve().parent
out=root.parent.parent
q=Path.home()/'.cache/ohm-233-position-qualified-20261027/first-occurrence-classic-pr233-h5-v2'
def j(p):return json.loads(p.read_bytes())
def wait(path):
 while not path.exists():
  if (q/'failure.txt').exists():raise RuntimeError('native study interrupted')
  time.sleep(.33)
def examine(mode,arm,phase):
 try:
  rel=Path(mode)/arm
  dest=root/rel;dest.mkdir(parents=True,exist_ok=True)
  f=out/'typed-queries'/rel/(phase+'.json');wait(f);x=j(f)
  old_names=j(out/'typed-queries/kinds.json');names=j(root/('kinds-'+arm+'.json'))
  k=names.index('module_children');old=old_names[k];e=j(out/rel/'manifest.json');by={v['stable_crate_id']:v for v in e['jobs']}
  rows=[]
  for job in x['jobs']:
   if job['crate']=='ruff_python_parser' or old not in job.get('result',{}).get('named',{}).get('lexer',{}):continue
   b=by[job['stable_crate_id']];session=job['graph']['session']
   if phase=='edit':f=out/rel/job['trace']/'dep-graph.bin'
   else:
    paths=list((q/'state'/rel/'target/debug/incremental').glob('*/'+b['directory']+'/'+session+'/dep-graph.bin'))
    if len(paths)!=1:
     rows.append({'crate':b['crate'],'stable_crate_id':b['stable_crate_id'],'session':session,'miss':'exact restored session already replaced or absent'});continue
    f,=paths
   s=subprocess.check_output([str(root/'module-parents'),str(f),*job['graph']['keys'],str(k)],text=True,timeout=60)
   m=[]
   for l in s.splitlines():
    sp=l.split()
    if sp[0]=='input_to':m.append(dict(kind=names[int(sp[1])],key=sp[2:4],value=sp[4]))
   assert any(l.startswith('q 2 '+str(k)+' ')for l in s.splitlines())
   rows.append(dict(crate=b['crate'],test=b['test'],stable_crate_id=b['stable_crate_id'],session=session,trace=job['trace'],incoming=m))
  dest=dest/(phase+'.json');tmp=dest.with_suffix('.part');tmp.write_text(json.dumps(dict(mode=mode,arm=arm,phase=phase,command=x['command_receipt'],rows=rows),indent=2,sort_keys=True)+'\n');tmp.replace(dest)
  print(mode,arm,phase,[j.get('miss',[(r['kind'],r['value'][:8]) for r in j.get('incoming',[])])for j in rows],flush=True)
 except BaseException:print('error',mode,arm,phase,traceback.format_exc(),flush=True)
with concurrent.futures.ThreadPoolExecutor(8) as pool:
 list(pool.map(lambda z:examine(*z),[(m,a,f) for m in ('build','test')for a in 'BC'for f in ('edit','restore')]))
