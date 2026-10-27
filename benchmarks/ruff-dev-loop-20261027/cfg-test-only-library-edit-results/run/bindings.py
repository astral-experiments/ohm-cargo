from pathlib import Path
import hashlib,json,os
I=Path(__file__).resolve().parent;X=I.parent;Q=X/'cfg-library-first-v1-campaign';state=Q/'state/build';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');T=P/'native-target';S=P/'shared';R=P/'registry-home';W=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027')
J=lambda p:json.loads(p.read_bytes())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def phys(p):
 p=Path(p)
 for src,root in [(T,'target'),(S,'shared'),(R,'registry-home')]:
  if p.is_relative_to(src):return state/root/p.relative_to(src)
 return p
ident=J(Q/'clean-and-ordinary/identity.json');args=ident['argv'];dirs=[];ex=[];sets={k:J(Q/'receipts/build'/k/'artifact-state.json') for k in ('cold','edit','restore')};all_known={k:{} for k in sets}
for label,files in sets.items():
 for name,rec in files.items():
  if rec.get('sha256'):all_known[label].setdefault(rec['sha256'],[]).append(name)
for i,tok in enumerate(args):
 if i==0:continue
 if args[i-1]=='--extern':
  if '=' not in tok:ex.append({'name':tok,'explicit_file':False});continue
  key,path=tok.split('=',1);p=phys(path);h=sha(p);x={'name':key,'explicit_file':True,'argv_file':path,'current_real_sha256':h,'bytes':p.stat().st_size,'phase_bindings':{}}
  for label,files in sets.items():
   pr=files.get(path,{});hit=pr.get('sha256');aliases=all_known[label].get(h,[]);x['phase_bindings'][label]={'exact_argv_path_sha256':hit,'same_content_other_cargo_published_aliases':aliases if hit is None else []}
  ex.append(x)
 if args[i-1]=='-L':dirs.append(tok)
 assert True
dep=next((Q/'receipts/build/cold').glob('ty_ide-*.d.original'));line=dep.read_text().splitlines()[0];pfx,body=line.split(': ',1)
assert '\\' not in body
observed=sorted(set(body.split()));file='crates/ty_ide/src/docstring.rs';sources={}
for tag in ('original','edited'):
 sources[tag]={}
 for full in observed:
  p=Path(full);p=phys(p) if p.is_absolute() else W/p
  if p==W/file:p=Q/'fixture'/tag/'docstring.rs'
  sources[tag][full]=sha(p)
assert [k for k in observed if sources['edited'][k]!=sources['original'][k]]==[file]
r={'stable_source_ruff_commit':J(I/'plan.json')['original_ruff'],'actual_prior_normal_rustc_exec_line_sha256':ident['actual_exec_line_sha256'],'actual_argv_sha256':hashlib.sha256(json.dumps(args,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'original_cargo_package_environment_pid':ident['selected_package_env']['pid'],'true_cold_rustc_pid':ident['rustc_cold_trace_pid'],'direct_externs':ex,'ordered_library_search_dirs':dirs,'all_sources_from_authentic_dep_info':sources,'dep_info_sha256':sha(dep),'exactly_one_source_contents_changes':file,'comparison_scope':'Hashes of actual direct extern argument files in the restored state reused for the independent producer replay; Cargo-published cold,edit,restore evidence is separately indicated per exact path or matching byte alias. No claim of a complete ambient path fingerprint.'};out=Q/'selected/independent/resolved-input-bindings.json';out.write_text(json.dumps(r,sort_keys=True,indent=1)+'\n');print('externs',len(ex),'sources',len(observed),'same-pid',r['true_cold_rustc_pid']==r['original_cargo_package_environment_pid'],'unmatched',[(v['name'],k) for v in ex if v['explicit_file'] for k,b in v['phase_bindings'].items() if b['exact_argv_path_sha256']!=v['current_real_sha256'] and not b['same_content_other_cargo_published_aliases']])
