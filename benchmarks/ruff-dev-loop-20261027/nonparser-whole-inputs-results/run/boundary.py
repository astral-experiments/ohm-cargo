from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,os,re
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';S=Path('/dev/shm/ohm-nonparser-whole-inputs-20261027/state/test');P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');T=P/'native-target';J=lambda p:json.loads(p.read_bytes());save=lambda p,x:p.write_text(json.dumps(x,sort_keys=True,indent=1)+'\n');h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();W=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027');dpath=lambda p:S/'target'/Path(p).relative_to(T);D=Q/'input-attribution';new=D/'residual-boundaries';new.mkdir(exist_ok=True);categories={};
for case in ('formatter','ty-diagnostic'):
 rows=J(D/'test'/(case+'-joined')/'all-jobs.json');native=J(D/'test'/(case+'-joined')/'wild.json');state=[Q/'receipts/test'/(case+'-'+i) for i in ('edit','restore')];pc=[J(v/'processes.json') for v in state];srcs=[J(v/'setup.json')['source_set'] for v in state];art=[J(v/'artifact-state.json') for v in state];allj=defaultdict(dict)
 for side,data in enumerate(pc):
  for ast in [json.loads(v) for v in (state[side]/'stdout').read_bytes().splitlines()]:
   if ast.get('reason')!='compiler-artifact':continue
   for f in ast['filenames']:allj[side][f]={'fresh':ast['fresh'],'aliases':ast['filenames'],'name':ast['target']['name'],'kind':ast['target']['kind'],'pkg':ast['package_id'],'test':ast['profile']['test']}
  for job in data['typed']:
   if job['kind'] not in ('wild','rustc-full','rustc-link-only'):continue
   job['_side']=side
 run=[]
 for b in native:
  if b['outcome'].startswith(('actual changed','changed actual')):continue
  fs=[]
  for side,pid in enumerate(b['wild_pids']):
   if pid is None:fs.append(None);continue
   ww={r['pid']:r for r in pc[side]['typed']};w=ww[pid];base=Path(w['link_output']);g=next((v for v in rows if v['side']==('edit','restore')[side] and v['pid']!=pid and pid in v['native_children']),None);assert g is not None;ru=ww[g['pid']];args=ru['argv'];out=dpath(base);nm=base.name
   # Cargo sometimes publishes the executable in native-target/debug/deps, independent from the real Wild path.
   known=[k for k,v in allj[side].items() if Path(k).name==nm];fin=next((dpath(k) for k in known if dpath(k).with_suffix('.rlink-cache.json').is_file()),out);f=fin.with_suffix('.rlink-cache.json');man=J(f) if f.exists() else None;unused=man.get('unused_extern_names') if man else None;actual=[]
   for i,a in enumerate(args):
    if a=='--extern' and i+1<len(args):
     eq=args[i+1].split('=',1);name=eq[0];p=eq[1] if len(eq)==2 else None;hit=allj[side].get(p or '');equal=(p and art[0].get(p,{}).get('sha256')==art[1].get(p,{}).get('sha256')) if p in art[0] and p in art[1] else None;actual.append({'name':name,'path':p,'cargo_declared_fresh':hit.get('fresh') if hit else None,'raw_identical_between_states':equal,'recorded_unused':name in set(unused) if isinstance(unused,list) else None,'successful_rustc_own_or_thread_open':p in ru['opens'] if p else None});
   ds=[p for p in out.parent.glob('*.d') if nm.split('-')[-1] in p.name];deps={};
   for dd in ds:
    txt=dd.read_text(errors='replace');line=txt.splitlines()[0] if txt else '';deps[dd.name]={'sha256':h(dd),'prerequisites':line.split(': ',1)[-1].split(),'observed_markers':[l for l in txt.splitlines() if 'ohm-foreign' in l or 'ohm-untrackable' in l],'bin_envs':[l for l in txt.splitlines() if l.startswith('# env-dep:CARGO_BIN_EXE')],'tracked_binary_paths':[q for q in line.split(': ',1)[-1].split() if Path(q).name in ('ruff','ty')]}
   files=[a for a in args if a.endswith('.rs') and not a.startswith('-')];cpp=[m for m in ru['missing'] if 'CARGO_BIN_EXE' in m];reg={o for o in ru['opens'] if o.endswith(('.rlib','.rmeta','.so')) and not o.startswith(str(P/'frozen-toolchain'))};lower={o for o in w['opens'] if o.endswith(('.so','.a','.rlib','.lds','.ld')) or '.so.' in o};ws=[k for k in (unused or []) if k.startswith(('ty','ruff'))];change_used=[x['name'] for x in actual if (x['cargo_declared_fresh'] is False or x['raw_identical_between_states'] is False) and x['recorded_unused'] is not True];fs.append({'wild_pid':pid,'rustc_pid':ru['pid'],'rustc_kind':ru['kind'],'crate':ru['crate'],'rustc_source_argv':files,'first_source_line':(W/files[0]).read_text().splitlines()[0] if len(files)==1 and (W/files[0]).is_file() else None,'rustc_reported_argv_sha256':ru['exec_sha256'],'manifest_exists':f.is_file(),'final_saved_manifest_sha256':h(f) if man else None,'manifest_format_keys':list(man) if man else None,'unused_extern_names':unused,'direct_externs':actual,'dirty_externs_without_unused_proof':change_used,'non_sdk_registered_opened_rmeta':[q for q in sorted(reg) if not '/registry/' in q],'depinfo':deps,'native_opened_files_outside_exact_argv':sorted(lower-set(w['argv'])),'negative_open_lookups':w['missing'],'first_order_native_library_choices':[a for a in w['argv'] if a.startswith('-l')],'ordered_search_paths':[a[2:] for a in w['argv'] if a.startswith('-L')],'wild_argv':w['argv'],'kernel_open_process':bool(w['opens']),'eligible':False})
  if all(fs):delta=[{'index':i,'edited':a,'restored':b} for i,(a,b) in enumerate(zip(fs[0]['wild_argv'],fs[1]['wild_argv'])) if a!=b];
  else:delta=None
  if all(fs):
   for x in fs:x.pop('wild_argv')
  run.append({'output':str(Path(b['output']).name),'phases':fs,'wild_argv_change':delta,'physical_summary':{k:v for k,v in b.items() if k not in ['output','full_resolved_file_opens','actual_cargo_aliases','other_unknowns','changed_common_path_opened_inputs','changed_ordered_opened_inputs']}})
 save(new/(case+'.json'),run)
 for q in run:
  f=q['phases'][0];print(case,q['output'],f['rustc_kind'],'man',f['manifest_exists'],'dirty without proof',f['dirty_externs_without_unused_proof'],'non_sdk_inputs',len(f['non_sdk_registered_opened_rmeta']),'argc changes',len(q['wild_argv_change'] or []));
