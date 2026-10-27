from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,os,sys,re
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';analysis=Q/'input-attribution';live=Q/'native-live';J=lambda f:json.loads(f.read_bytes());save=lambda f,j:f.write_text(json.dumps(j,sort_keys=True,indent=1)+'\n');assert (live/'complete.json').is_file();hasher=lambda b:hashlib.sha256(b).hexdigest()
R={int(p.stem):J(p) for p in live.glob('*.json') if p.stem.isdecimal()};summ=[]
for mode in ('build','test'):
 for edit in ('ty-diagnostic','formatter'):
  folders=[Q/'receipts'/mode/(edit+'-'+s) for s in ('edit','restore')];jobs=[J(analysis/mode/d.name/'jobs.json') for d in folders];st=[J(d/'artifact-state.json') for d in folders];pc=[J(d/'processes.json') for d in folders];
  byout=[{r['link_output']:r for r in v if r['kind']=='wild'} for v in jobs]; assert all(len(b)==sum(r['kind']=='wild' for r in v) for b,v in zip(byout,jobs));whole=[]
  for k in sorted(set(byout[0])|set(byout[1])):
   jj=[w.get(k) for w in byout];types=['wild-edit','wild-restore'];pids=[x['pid'] if x else None for x in jj];ll=[R.get(p) for p in pids];actual=[{x['pid']:x for x in f['typed']} for f in pc];basis={'output':k,'wild_pids':pids,'present':[bool(x) for x in ll]};
   if not all(ll):basis['outcome']='wild observer missed at least one real invocation';whole.append(basis);continue
   assert all(l['argv']==actual[side][p]['argv'] and l['output']==k and l['label']==folders[side].name for side,(p,l) in enumerate(zip(pids,ll))),('argv mismatch',k,pids)
   opens=[set(j['link_object_or_archive_reads'])|set(j['temporary_reads']) for j in jj];caps=[v['captures'] for v in ll];known=[{p:v['sha256'] for p,v in c.items() if 'sha256'in v} for c in caps];reread=set(known[0])&set(known[1])&opens[0]&opens[1];differ=[{'path':p,'edit':known[0][p],'restored':known[1][p],'bytes':[caps[0][p]['facts'][2],caps[1][p]['facts'][2]]} for p in sorted(reread) if known[0][p]!=known[1][p]]
   # Rustc can choose final local .rcgu filenames which differ. Compare same ordered GCC-expanded input role separately; preserve both raw names/hashes.
   ordered=[];equal_inputs=0;different_tokens=0;la=[x['argv'] for x in ll];
   for i,(left,right) in enumerate(zip(*la)):
    if left!=right:different_tokens+=1
    if left in opens[0] and right in opens[1] and left in known[0] and right in known[1]:
     if known[0][left]!=known[1][right]:ordered.append({'argv_index':i,'left':left,'right':right,'edit':known[0][left],'restored':known[1][right]})
     else:equal_inputs+=1
   # Corroborate any Cargo alias with both original and reversion bytes, without using names or inode assumptions.
   aliases=[]
   for row in differ:
    if row['path'].endswith('.rlib'):
     a={p for p,i in st[0].items() if i.get('sha256')==row['edit']};b={p for p,i in st[1].items() if i.get('sha256')==row['restored']};aliases.extend({'actual':row['path'],'cargo_alias':p} for p in sorted(a&b))
   basename=Path(k).name;alias_candidates=[k];alias_candidates+=[p for p in set(st[0])&set(st[1]) if Path(p).name==basename and p not in alias_candidates];oobs={p:[st[0][p]['sha256'],st[1][p]['sha256']] for p in alias_candidates if p in st[0] and p in st[1] and st[0][p].get('sha256') and st[1][p].get('sha256')};evidenceleft=set(ll[0]['captures'])-set(known[0]);evidenceright=set(ll[1]['captures'])-set(known[1]);
   pos=[{'path':p,'sha256':known[0][p]} for p in sorted(reread) if known[0][p]==known[1][p]]
   basis.update({'outcome':'actual changed whole file opened by Wild at both endpoints' if differ else 'changed actual ordered-input bytes' if ordered else 'no known changed real inputs in captured direct intersection','changed_common_path_opened_inputs':differ,'changed_ordered_opened_inputs':ordered,'matched_direct_read_files':len(reread),'matched_equal_direct_read_files':len(pos),'matched_ordered_equal_args':equal_inputs,'different_argv_tokens':different_tokens,'argc':[len(x) for x in la],'known_equal_digest_set_sha256':hasher(json.dumps(pos,sort_keys=True).encode()),'displayed_product_raw_sha':oobs,'snapshot_errors':[sorted(evidenceleft),sorted(evidenceright)],'other_unknowns':['Native linker script/response includes and negative search candidates are not authenticated by an argv-file digest alone.','A system-tool, an opened loader/script, an ephemeral argument, or output inode/mode may differ even with equal archives.'],'actual_cargo_aliases':aliases,'kernel_readonly_object_archive_or_tmp_files':[len(v) for v in opens]});whole.append(basis)
  native_proven={r['output'] for r in whole if r['outcome'] in ('actual changed whole file opened by Wild at both endpoints','changed actual ordered-input bytes')};
  asmt=[]
  for side,rows in enumerate(jobs):
   wild_by={r['pid']:r for r in rows if r['kind']=='wild'}
   for r in rows:
    actual_proc={v['pid']:v for v in pc[side]['typed']}[r['pid']];ar=actual_proc['argv'];outdir=Path(ar[ar.index('--out-dir')+1]) if '--out-dir' in ar else None;external={p:hs for p,hs in r['changed_actual_paths'].items() if outdir is None or Path(p).parent!=outdir};
    if r['kind']=='wild':x=r['link_output'] in native_proven
    else:x=bool(external) or any(wild_by[w]['link_output'] in native_proven for w in r['descendant_wilds']);
    asmt.append({'side':('edit','restore')[side],'kind':r['kind'],'crate':r['crate'],'pid':r['pid'],'changed_actual_open_or_child':x,'consumed_changed_inputs_excluding_own_out_dir':external,'read_own_outputs_excluded':sorted(set(r['changed_actual_paths'])-set(external)),'changed_source_or_direct_extern':[p for p in sorted(external) if p.startswith('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/') or p in set(actual_proc['externs'])],'native_children':r['descendant_wilds'],'output':r['link_output']})
  bucket=analysis/mode/(edit+'-joined');bucket.mkdir(exist_ok=True);save(bucket/'wild.json',whole);save(bucket/'all-jobs.json',asmt);compact={'mode':mode,'edit':edit,'native_job_pairs':len(whole),'native_observed_in_both':sum(all(r['present']) for r in whole),'actual_changed_input_link_pairs':len(native_proven),'remaining_native_outputs':[r['output'] for r in whole if r['output'] not in native_proven],'typed_incidence':dict(Counter(str(x['side'])+' '+x['kind']+' changed='+str(x['changed_actual_open_or_child']) for x in asmt)),'live_observer_failures':sum(len(x) for r in whole for x in r.get('snapshot_errors',[]))};save(bucket/'summary.json',compact);summ.append(compact);print(compact,flush=True)
save(analysis/'joined-summary.json',summ)
