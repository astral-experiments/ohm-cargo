from pathlib import Path
from collections import Counter
import hashlib,json,shutil,os,re
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';R=Q/'input-attribution';O=Q/'selected-evidence';O.mkdir(exist_ok=True);H=X/'nonparser-whole-inputs-impl-v1';T=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target');W='/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/';J=lambda p:json.loads(p.read_bytes());save=lambda p,v:p.write_text(json.dumps(v,sort_keys=True,indent=1)+'\n');h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();sel=[];stages=[];cmdsup=[];
for mode in ('build','test'):
 receipt=Q/'receipts'/mode;allr=sorted(receipt.glob('*/receipt.json'),key=lambda p:p.stat().st_mtime_ns);maps={};elfsets={};procs={};last=None
 for f in allr:
  d=f.parent;j=J(f);s=J(d/'artifact-state.json');c=J(d/'cli.json');a=[json.loads(b) for b in (d/'stdout').read_bytes().splitlines()];rows=[v for v in a if v.get('reason')=='compiler-artifact'];pkgrows=[v for v in rows if v.get('package_id','').startswith('path+')]; rawpaths={p for r in pkgrows for p in r['filenames'] if Path(p).suffix in ('','.so')}; state=(Q if mode=='build' else Path('/dev/shm/ohm-nonparser-whole-inputs-20261027'))/'state'/mode; outputs=[]
  for name in sorted(rawpaths):
   p=Path(name); base=T if p.is_relative_to(T) else T.parent/'shared';mapped=state/('target' if base==T else 'shared')/p.relative_to(base)
   with mapped.open('rb') as handle:magic=handle.read(4)
   if magic==bytes.fromhex('7f454c46'):outputs.append(name)
  expect=15 if mode=='build' else 110;assert len(outputs)==expect,(mode,len(outputs),outputs[:5]);e={p:s[p]['sha256'] for p in outputs};seenexec={r['executable'] for r in rows if r.get('executable') and r['profile']['test']};pc=J(d/'processes.json');testexec=[v for _,v in pc['exec-images'] if v in seenexec];assert not testexec;native=pc['typed'];old=elfsets.get(last,{});changes=[{'output':p,'before':old.get(p),'after':e[p]} for p in outputs if old.get(p)!=e[p]] if old else []
  show={'mode':mode,'label':d.name,'phase':j['phase'],'source':j['source'],'cargo_artifact_units':j['artifacts'],'fresh_units':j['fresh'],'published_files':j['physical_products'],'missing_published_files':j['missing_products'],'different_published_files':j['different_raw_products'],'workspace_elf_count':len(e),'different_workspace_elfs':len(changes),'different_outputs':changes,'elf_map_sha256':hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'jobs':j['jobs'],'executed_test_programs':testexec,'setup':J(d/'setup.json'),'actual_exec_trace_archive_sha256':h(d/'exec-traces.tar.zst'),'complete_product_data_sha256':h(d/'artifact-state.json'),'cli':c,'rustc_diagnostic_messages':[{'target':v.get('target',{}).get('name'),'level':v.get('message',{}).get('level'),'code':(v.get('message',{}).get('code') or {}).get('code'),'message':v.get('message',{}).get('message')} for v in a if v.get('reason')=='compiler-message']};stages.append(show);maps[d.name]=s;elfsets[d.name]=e;procs[d.name]=native;last=d.name
 for case in ('formatter','ty-diagnostic'):
  joined=R/mode/(case+'-joined');val=J(joined/'all-jobs.json');ww=J(joined/'wild.json');summary=J(joined/'summary.json');save(O/(mode+'-'+case+'-summary.json'),summary);
  for r in val:
   side=r['side'];name=case+'-'+side;pid=r['pid'];ar=next(q for q in procs[name] if q['pid']==pid);r['source_exec_trace_sha256']=ar['exec_sha256'];r['executable_sha256']=ar['image_sha256'];r['trace_img_name']=Path(ar['img']).name;r['actual_full_or_link_only']=[v for i,v in enumerate(ar['argv']) if v.startswith('-Zlink-only') or (i>0 and ar['argv'][i-1]=='-Z' and v=='link-only')];r['mode']=mode;r['case']=case
  save(O/(mode+'-'+case+'-jobs.json'),val);compact=[]
  for w in ww:
   q={k:v for k,v in w.items() if k not in ('actual_cargo_aliases','changed_common_path_opened_inputs','changed_ordered_opened_inputs')};q['complete_changed_common_paths_count']=len(w.get('changed_common_path_opened_inputs',[]));q['complete_changed_ordered_paths_count']=len(w.get('changed_ordered_opened_inputs',[]));q['changed_common_input_examples']=w.get('changed_common_path_opened_inputs',[])[:4];q['changed_ordered_input_examples']=w.get('changed_ordered_opened_inputs',[])[:2];q['independently_hashed_alias_examples']=w.get('actual_cargo_aliases',[])[:4];q['actual_wild_exec_line_sha256']=[next(v['exec_sha256'] for v in procs[case+'-'+s] if v['pid']==p) if p else None for s,p in zip(('edit','restore'),w['wild_pids'])];compact.append(q)
  save(O/(mode+'-'+case+'-wild.json'),compact);sel.append(summary)
 for name in maps:
  if name in ('cold','warm-1'):continue
  if name.endswith('-fresh') or name.startswith('warm-'):continue
  u=next(i for i in allr if i.parent.name==name);old=allr[allr.index(u)-1].parent.name;changed={p:{'before':maps[old].get(p,{}).get('sha256'),'after':v.get('sha256')} for p,v in maps[name].items() if maps[old].get(p,{}).get('sha256')!=v.get('sha256')};save(O/(mode+'-'+name+'-all-changed-files.json'),changed)
save(O/'phases.json',stages);save(O/'joined-summary.json',sel);save(O/'live-observer-coverage.json',J(Q/'native-live/complete.json'));save(O/'disk-reserve.json',{'initial_available':J(Q/'baseline-disk.json'),'after_campaign_available_bytes':{'root':shutil.disk_usage(Q).free,'tmpfs':shutil.disk_usage('/dev/shm').free}})
for case in ('formatter','ty-diagnostic'):
 residual=J(R/'residual-boundaries'/(case+'.json'));save(O/(case+'-residuals.json'),residual)
source=Q/'ordinary-native-readers';dest=O/'ordinary-new-callers';dest.mkdir(exist_ok=True)
for p in sorted(source.glob('*.rs'))+sorted(source.glob('*/result.json'))+sorted(source.glob('*/rustc.stderr'))+sorted(source.glob('*/runtime.stdout'))+sorted(source.glob('*/runtime.stderr'))+[source/'complete.json']:
 t=dest/p.relative_to(source);t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,t)
for name in ('producer-snapshots','formatter-native-snapshots'):
 dest=O/name;dest.mkdir(exist_ok=True);shutil.copyfile(Q/name/'complete.json',dest/'complete.json')
for name in ('genuine-cgu-name-selector','genuine-cgu-name-selector-v2'):
 src=Q/name;dst=O/name;dst.mkdir(exist_ok=True);shutil.copyfile(src/'complete.json',dst/'complete.json');rows=J(src/'complete.json')
 for z in rows:
  raw=src/z['target'];saved=dst/z['target'];saved.mkdir(exist_ok=True);shutil.copyfile(raw/'start.s',saved/'start.s');shutil.copyfile(raw/'selector.ld',saved/'selector.ld');
  if name.endswith('v2'):
   obj=raw/Path(z['actual_source_argv_paths'][0]).name;assert h(obj)==z['source_object_sha'] and obj.stat().st_size<8*2**20;shutil.copyfile(obj,saved/'genuine-input.rcgu.o');
ford=Q/'receipts/test';last=next(v for v in stages if v['mode']=='test' and v['label']=='warm-2');assert last['fresh_units']==619 and last['different_published_files']==0
ids=J(X/'first-occurrence-worker-v2/binding.json')['host']['host_tools'];want={k:v for k,v in ids.items() if k in ('GCC_driver','collect2','Wild','rustc_frontend','rustup_cargo_proxy')};save(O/'subject.json',{'ruff':J(H/'plan.json')['base'],'cargo':stages[-1]['setup']['cargo'],'driver':stages[-1]['setup']['rustc_driver'],'frontend':stages[-1]['setup']['frontend'],'prior_fixed_host_manifest':want,'observed_tool_hashes':{role:sorted({w['executable_sha256'] for x in O.glob('*-jobs.json') for w in J(x) if w['kind']==role}) for role in ('rustc-full','wild')},'historical_path_sha256':{k:h(H/v) for k,v in [('ty','ty-diagnostic.patch'),('formatter','formatter.patch'),('before-plan','plan.json')]}});print([(s['mode'],s['label'],s['different_workspace_elfs']) for s in stages if s['phase'] in ('edit','restore')]); print('payload',sum(q.stat().st_size for q in O.rglob('*') if q.is_file()))
