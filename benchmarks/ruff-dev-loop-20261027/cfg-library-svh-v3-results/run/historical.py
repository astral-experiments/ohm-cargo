"""Prospective same-source normal Rust producer and ordinary private-binding readers. No Cargo runs or timings."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,traceback
H=Path(__file__).resolve().parent;X=H.parent;B=X/'cfg-library-first-v1-campaign';A=X/'cfg-library-first-v1-impl';V=X/'cfg-library-svh-v3-replay-v1';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');F=P/'frozen-toolchain';T=P/'native-target';SH=P/'shared';CH=P/'registry-home';ST=B/'state/build';W=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027');sys.path.insert(0,str(A));from artifacts import archive
from wire import read as source_entry
from compare import archive_diff
J=lambda p:json.loads(p.read_bytes());H0=lambda b:hashlib.sha256(b).hexdigest()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,r):p.write_text(json.dumps(r,sort_keys=True,indent=1)+'\n')
plan=J(H/'plan.json');inv=J(H/'prior-normal-compiler.json');bindings=J(H/'resolved-input-bindings.json');args=inv['argv'];assert H0(json.dumps(args,sort_keys=True,separators=(',',':')).encode())==plan['fixed_args_sha256'];source=plan['complete_history']['file'];srcs={k:B/'fixture'/k/'docstring.rs' for k in ('original','edited')};md5s={k:hashlib.md5(v.read_bytes()).digest() for k,v in srcs.items()};osel=Path(inv['absolute_output']);isel=Path(inv['absolute_incremental']);soname='librustc_driver-774a793a844d5500.so';treat=J(H/'release-binding.json')['sha256'];assert treat=='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05';img={'parent':X/'drivers'/('driver-'+plan['stock_rustc_driver']),'candidate':X/'cfg-library-svh-v3-release/candidate-driver.so'};vh=V/'common';selected=vh/'selected';outpoint=vh/'output';env_allow=inv['selected_package_env']['env'];env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(CH),CARGO_TARGET_DIR=str(T),CARGO_BUILD_BUILD_DIR=str(SH),CARGO_BUILD_JOBS='8',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',GIT_OPTIONAL_LOCKS='0',LC_ALL='C.UTF-8',CARGO_TERM_COLOR='never',SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs');env.update(env_allow);env.pop('RUSTC_LOG',None)
def protection():
 h=shutil.disk_usage(X).free;assert h>25*2**30;used=int(subprocess.check_output(['du','-sb',str(V)]).split()[0]);assert used<6*2**30,(used,h);return [used,h]
def physical(x):
 x=Path(x)
 for root,name in ((T,'target'),(SH,'shared'),(CH,'registry-home')):
  if x.is_relative_to(root):return ST/name/x.relative_to(root)
 return x
def verify_inputs(source_state):
 rs={}
 for f,h in bindings['all_sources_from_authentic_dep_info'][source_state].items():
  p=srcs[source_state] if f==source else physical(f) if Path(f).is_absolute() else W/f;rh=sha(p);assert h==rh,('source',f,h,rh);rs[f]=rh
 ed={}
 for z in bindings['direct_externs']:
  assert z['explicit_file'];p=physical(z['argv_file']);h=sha(p);assert h==z['current_real_sha256'],('extern',p,h,z['current_real_sha256']);ed[z['name']]=h
 assert len(rs)==44 and len(ed)==29 and sha(F/'bin/rustc')==plan['common_rustc_frontend'];return {'source_roster_sha256':H0(json.dumps(rs,sort_keys=True).encode()),'direct_extern_roster_sha256':H0(json.dumps(ed,sort_keys=True).encode()),'sources':len(rs),'externs':len(ed),'edited_file_sha256':rs[source]}
def ns(arm,src,binds):
 n=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp','--bind',str(V),str(V),'--ro-bind',str(ST/'rustup'),str(P/'rustup')]
 for a,b in ((ST/'target',T),(ST/'shared',SH),(ST/'registry-home',CH),(X/'cargo-observer-fifo-qualification/guardv3',F/'bin/cargo'),(img[arm],F/'lib'/soname),(srcs[src],W/source)):n+=['--ro-bind',str(a),str(b)]
 for a,b,writable in binds:n+=['--bind' if writable else '--ro-bind',str(a),str(b)]
 return n+['--']
def go(arm,src,cmd,binds=(),trace=None):
 if trace is not None:cmd=['strace','-qq','-f','-s','131072','-e','trace=execve,execveat','-o',str(trace),*cmd]
 return subprocess.run([*ns(arm,src,binds),*cmd],env=env,cwd=W,capture_output=True,timeout=400)
def head(arm,src,md):
 q=go(arm,src,['rustc','+ohm','--sysroot',str(F),'-Zls=root',str(md)]);s=q.stdout.decode(errors='replace');v=re.search(r'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',s,re.M);assert q.returncode==0 and v,(q.returncode,q.stderr[:800]);return {'private':v[1],'stable_crate_id':v[2],'public':v[3],'listing_sha256':H0(q.stdout)}
def producer(dst,arm,source_state,chain,name):
 d=dst/name;d.mkdir();store=dst/'chains'/chain;existed=store.exists()
 if not existed:store.mkdir(parents=True);(store/'out').mkdir();(store/'incremental').mkdir()
 prior=sorted(q.name for q in (store/'incremental').iterdir());expected_initial=name.startswith('empty') or name=='chain-original';assert (not prior)==expected_initial,(name,prior)
 inputs=verify_inputs(source_state);trace=d/'compiler.exec';q=go(arm,source_state,args,[(store/'out',osel,True),(store/'incremental',isel,True)],trace);(d/'stdout').write_bytes(q.stdout);(d/'stderr').write_bytes(q.stderr);actuals=[s for s in trace.read_text(errors='replace').splitlines() if 'execve("'+args[0]+'"' in s and re.search(r'= 0$',s)];assert len(actuals)==1
 r={'label':name,'source_state':source_state,'returncode':q.returncode,'actual_compiler_argv':args,'actual_exec_line_sha256':H0(actuals[0].encode()),'driver_sha256':sha(img[arm]),'input_bindings':inputs,'originally_empty_incremental':expected_initial,'reused_initial_contents':prior,'stdout_sha256':H0(q.stdout),'stderr_sha256':H0(q.stderr),'space':protection()}
 if q.returncode!=0:dump(d/'result.json',r);raise RuntimeError(('incompatible reference deps or failed producer',arm,name,q.returncode,q.stderr[-2600:]))
 oo=d/'artifacts';oo.mkdir();md,=sorted((store/'out').glob('libty_ide-*.rmeta'));rl,=sorted((store/'out').glob('libty_ide-*.rlib'));sample=oo/md.name;shutil.copyfile(md,sample);srl=oo/rl.name;shutil.copyfile(rl,srl);entry=source_entry(sample,srcs[source_state],'docstring.rs');assert entry['normalized_bytes']==srcs[source_state].stat().st_size and entry['carries_filename_near_entry'];r.update(metadata=sample.name,rlib=srl.name,metadata_sha256=sha(sample),rlib_sha256=sha(srl),header=head(arm,source_state,sample),physical_source=entry);r['equals_predeclared_public_api']=r['header']['public']=='f321b448bc54bd2819e1fe053541ce11';dump(d/'result.json',r);print(arm,name,r['header']['private'],r['header']['public'],flush=True)
 return [r,sample,srl]
def ordinary_search():
 result=['-Ldependency='+str(selected)];log=[];root=vh/'filtered';root.mkdir()
 for i,ls in enumerate(bindings['ordered_library_search_dirs']):
  kind,raw=ls.split('=',1);p=physical(raw)
  if kind!='dependency':continue
  if not p.is_dir():log.append({'ordered_index':i,'original':raw,'missing_search_dir':True});continue
  choices=[x.name for x in p.iterdir() if x.name.startswith(('libty_ide-','libty_ide.','libordinary_scope_bridge')) and x.suffix in ('.rmeta','.rlib','.so','.a')]
  if not choices:result+=['-Ldependency='+raw];continue
  # Keep the selected search order and every unrelated file. The private directory contains no other provider of either relevant metadata identity.
  dest=root/str(i);dest.mkdir()
  for member in p.iterdir():
   if member.name not in choices:(dest/member.name).symlink_to(Path(raw)/member.name,target_is_directory=member.is_dir())
  result+=['-Ldependency='+str(dest)];log.append({'ordered_index':i,'original':raw,'excluded':sorted(choices)})
 for dir in result[1:]:
  a=Path(dir.split('=',1)[1]);aa=physical(a);assert not [x for x in aa.iterdir() if x.name.startswith(('libty_ide-','libty_ide.','libordinary_scope_bridge')) and x.suffix in ('.rmeta','.rlib','.so','.a')],str(aa)
 dump(vh/'ordinary-search.json',{'actual_args':result,'masked_choices':log,'num_candidate_directories':len(result),'selected_empty_before_binding':True});return result
def bridge(dst,arm,prod,dirs):
 bridgefile=vh/'ordinary_bridge.rs';caller=vh/'ordinary_caller.rs';pe=selected/'libty_ide.rmeta';be=selected/'libordinary_scope_bridge.rmeta';out={}
 for name,(ro,md,library) in prod.items():
  d=dst/('ordinary-bridge-'+name);d.mkdir();cmd=['rustc','+ohm','--sysroot',str(F),'--edition=2024','--crate-name','ordinary_scope_bridge','--crate-type=lib','--emit=metadata','--error-format=json','--extern','ty_ide='+str(pe),*dirs,str(bridgefile),'-o',str(outpoint/'libordinary_scope_bridge.rmeta')];q=go(arm,'edited',cmd,[(md,pe,False),(d,outpoint,True)]);(d/'stderr').write_bytes(q.stderr);rec={'producer':ro['header'],'status':q.returncode,'args_sha256':H0(json.dumps(cmd).encode()),'producer_raw_sha':sha(md),'stderr_sha256':H0(q.stderr),'ordinary_no_public_hash_option':not any('public-api-hash' in x for x in cmd)};dump(d/'result.json',rec);assert rec['ordinary_no_public_hash_option'] and q.returncode==0,(arm,'ordinary bridge',name,q.stderr[-2000:]);out[name]=d/'libordinary_scope_bridge.rmeta'
 rows=[]
 for bs,bmd in out.items():
  for ps,(ro,md,library) in prod.items():
   d=dst/('ordinary-caller-'+bs+'-vs-'+ps);d.mkdir();cmd=['rustc','+ohm','--sysroot',str(F),'--edition=2024','--crate-name','genuine_ide_input','--crate-type=lib','--emit=metadata','--error-format=json','--extern','ordinary_scope_bridge='+str(be),'--extern','ty_ide='+str(pe),*dirs,str(caller),'-o',str(outpoint/'caller.rmeta')];q=go(arm,'edited',cmd,[(md,pe,False),(bmd,be,False),(d,outpoint,True)]);msgs=[json.loads(b) for b in q.stderr.splitlines() if b.startswith(b'{')];(d/'stderr').write_bytes(q.stderr);codes=[m['code']['code'] for m in msgs if m.get('code')];rr={'bridge_producer':bs,'caller_producer':ps,'same_source_state':'edited','bridge_metadata':sha(bmd),'selected_caller_producer':ro['header'],'status':q.returncode,'diagnostics':msgs,'codes':codes,'selector_dir':str(selected),'args_sha256':H0(json.dumps(cmd).encode()),'stderr_sha256':H0(q.stderr),'out_rmeta_sha256':sha(d/'caller.rmeta') if (d/'caller.rmeta').is_file() else None};dump(d/'result.json',rr);rows.append(rr);assert bs!=ps or q.returncode==0,(arm,bs,ps,codes,q.stderr[-1600:]);print('ordinary',arm,bs,ps,q.returncode,codes,flush=True)
 return rows
def main():
 assert not V.exists() and sha(H/'plan.json')=='b626b6198da7c6513b1b8a3917431b90e9dbfe7bcb4e8c801f2296f19c457cd2' and sha(H/'resolved-input-bindings.json')==plan['all_source_and_extern_bindings_sha256']
 assert sha(img['parent'])==plan['stock_rustc_driver'] and sha(img['candidate'])==treat and sha(F/'bin/rustc')==plan['common_rustc_frontend'];assert (ST/'rustup/toolchains/ohm').resolve()==F and not subprocess.check_output(['git','-C',str(W),'status','--porcelain']);assert subprocess.check_output(['git','-C',str(W),'rev-parse','HEAD']).decode().strip()==plan['real_source_ruff']
 V.mkdir(mode=0o700);vh.mkdir();selected.mkdir();outpoint.mkdir();(selected/'libty_ide.rmeta').touch();(selected/'libordinary_scope_bridge.rmeta').touch();assert not any(outpoint.iterdir());(vh/'ordinary_bridge.rs').write_text("pub use ty_ide::Completion; pub fn has_docs(c: &Completion<'_>) -> bool { c.documentation.is_some() }\n");(vh/'ordinary_caller.rs').write_text("pub fn read(c: &ty_ide::Completion<'_>) -> bool { ordinary_scope_bridge::has_docs(c) }\n");dirs=ordinary_search();rows=[]
 for block,ordering in enumerate(plan['arm_orders'],1):
  for arm in ordering:
   dst=V/('block-'+str(block))/arm;dst.mkdir(parents=True);values={}
   for src,chain,n in [('original','warm','chain-original'),('edited','warm','chain-edited'),('original','warm','chain-restored'),('edited','clean-edit','empty-edited'),('original','clean-original','empty-original')]:values[n]=producer(dst,arm,src,chain,n)
   pairs={'warm-edited':values['chain-edited'],'cold-edited':values['empty-edited']};br=bridge(dst,arm,pairs,dirs);summ={'block':block,'arm':arm,'driver_sha256':sha(img[arm]),'private':{n:v[0]['header']['private'] for n,v in values.items()},'public':{n:v[0]['header']['public'] for n,v in values.items()},'metadata':{n:v[0]['metadata_sha256'] for n,v in values.items()},'same_edited_private':values['chain-edited'][0]['header']['private']==values['empty-edited'][0]['header']['private'],'same_restored_private':values['chain-restored'][0]['header']['private']==values['empty-original'][0]['header']['private'],'ordinary_cross':[{'bridge':s['bridge_producer'],'caller':s['caller_producer'],'status':s['status'],'codes':s['codes']} for s in br],'edited_native_comparison':archive_diff(archive(pairs['warm-edited'][2],'docstring.rs',md5s),archive(pairs['cold-edited'][2],'docstring.rs',md5s))};rows.append(summ);dump(dst/'summary.json',summ);dump(V/'progress.json',rows)
 dump(V/'complete.json',{'result':rows,'space_check':protection(),'plan_sha256':sha(H/'plan.json'),'all_calls_reported':True})
if __name__=='__main__':
 try:main()
 except BaseException:
  if V.is_dir():(V/'failure.txt').write_text(traceback.format_exc())
  raise
