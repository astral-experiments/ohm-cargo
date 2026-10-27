"""Direct empty-state production compiler replay and genuine new external readers, never modifying the Cargo state."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys
I=Path(__file__).resolve().parent;sys.path.insert(0,str(I));from runner import Q,RUFF,P,FROZEN,SONAME,cargo,driver,state,env,sha,disk,J,dump,sel,f,plan,TARGET,SHARED,CARGO_HOME
from artifacts import archive,metadata
O=Q/'clean-and-ordinary';O.mkdir(mode=0o700);st=state('build');remeta=Q/'receipts/build';rows=J(remeta/'cold/processes.json')['typed'];cand=[r for r in rows if r['kind']=='rustc-full' and r['crate']=='ty_ide' and not r['test']];assert len(cand)==1,(len(cand),[(v['test'],v['argv'][:3]) for v in cand]);rec=cand[0];args=rec['argv'];od=Path(args[args.index('--out-dir')+1]);inc=next(Path(v.split('=',1)[1]) for v in args if v.startswith('incremental='));assert od.is_relative_to(TARGET) and inc.is_relative_to(TARGET)
md5s={k:hashlib.md5((Q/'fixture'/k/Path(f).name).read_bytes()).digest() for k in ('original','edited')};need={'frontend':sha(FROZEN/'bin/rustc'),'cargo':sha(cargo),'driver':sha(driver)};allenv=list((Q/'compiler-env-roster').glob('*.json'));en=None
for p in allenv:
 e=J(p)
 if str(rec['pid'])==p.stem:en=e;break
 if not e['env'].get('CARGO_MANIFEST_DIR','').endswith('/crates/ty_ide'):continue
 if en is None:en=e
cfg=env();cfg.update(en['env'] if en else {});H0=lambda d:hashlib.sha256(d).hexdigest();dump(O/'identity.json',{'rustc_cold_trace_pid':rec['pid'],'actual_exec_line_sha256':rec['exec_sha256'],'physical_image_sha256':rec['image_sha256'],'argv':args,'selected_package_env':en,'tools':need,'explicit_replay_root':str(O),'absolute_output':str(od),'absolute_incremental':str(inc)})
def ns(view,over=()):
 n=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp','--bind',str(O),str(O),'--ro-bind',str(st/'rustup'),str(P/'rustup')]
 for src,dst in [(st/'target',TARGET),(st/'shared',SHARED),(st/'registry-home',CARGO_HOME),(cargo,FROZEN/'bin/cargo'),(driver,FROZEN/'lib'/SONAME),(Q/'fixture'/view/Path(f).name,RUFF/f)]:n+=['--ro-bind',str(src),str(dst)]
 for src,dst,allow in over:n+=['--bind' if allow else '--ro-bind',str(src),str(dst)]
 return n+['--']
def physical(p):return st/'target'/Path(p).relative_to(TARGET)
def call(argv,stdin=None,view='original',over=()):
 disk();p=subprocess.run(ns(view,over)+argv,cwd=RUFF,env=cfg,capture_output=True,input=stdin,timeout=600);disk();return p
prod={};headers={};reference=[]
for source in ('original','edited'):
 d=O/('compiler-'+source);d.mkdir();o=d/'out';ic=d/'inc';o.mkdir();ic.mkdir();p=call(args,view=source,over=[(o,od,True),(ic,inc,True)]);(d/'stdout').write_bytes(p.stdout);(d/'stderr').write_bytes(p.stderr);m={'source':source,'status':p.returncode,'compiler_argv':args,'stderr_sha256':H0(p.stderr),'stdout_sha256':H0(p.stdout),'target_sha256':sha(Q/'fixture'/source/Path(f).name),'artifacts':{},'output_info':{'out':str(od),'incr':str(inc),'empty_before':True}}
 for q in sorted(o.iterdir()) if p.returncode==0 else []:
  if q.suffix=='.rmeta':m['metadata']=metadata(q,md5s);prod[source]=q
  elif q.suffix=='.rlib':m['archive']=archive(q,'docstring.rs',md5s)
  if q.is_file():m['artifacts'][q.name]=sha(q)
 dump(d/'evidence.json',m);reference.append(m);print('clean',source,p.returncode,p.stderr[-250:],(m.get('metadata') or {}).get('source_md5'),flush=True)
# A diagnostic third direct run reuses only the original producer's private incremental state; INFO reveals a successful existing prefix fast path.
if 'original' in prod and 'edited' in prod:
 d=O/'warm-isolated-prefix';d.mkdir();o=d/'out';o.mkdir();ic=O/'compiler-original/inc';previous=cfg.get('RUSTC_LOG');cfg['RUSTC_LOG']='ohm_metadata_reuse=info';q=call(args,view='edited',over=[(o,od,True),(ic,inc,True)])
 if previous is None:cfg.pop('RUSTC_LOG')
 else:cfg['RUSTC_LOG']=previous
 (d/'stdout').write_bytes(q.stdout);(d/'stderr').write_bytes(q.stderr);dump(d/'evidence.json',{'status':q.returncode,'source':'edited','previous_incremental':'compiler-original/inc','separately_empty_output':True,'metadata_prefix_reuse_info_emitted':b'reused metadata item prefix with a freshly encoded source map' in q.stderr,'stderr_sha256':H0(q.stderr),'files':{p.name:sha(p) for p in o.iterdir() if p.is_file()}})
def doc(header,src):
 a=call(['rustc','+ohm','--sysroot',str(FROZEN),'-Zls=root',str(header)],view=src);rt=a.stdout.decode(errors='replace');return {'status':a.returncode,'record':rt.splitlines()[:14],'stdout_sha256':H0(a.stdout),'stderr_sha256':H0(a.stderr)}
for m in ('build','check','test'):
 for v,src in [('cold','original'),('edit','edited'),('restore','original')]:
  bucket=Q/'receipts'/m/v;md=bucket/'producer.rmeta'
  if md.is_file():headers[m+'-'+v]=doc(md,src)
for src,q in prod.items():headers['direct-clean-'+src]=doc(q,src)
dump(O/'current-root-listings.json',headers)
if len(prod)!=2:
 dump(O/'complete.json',{'clean_compiler_complete':False,'num_clean':len(prod),'physical_error':'see compiler-original/edited evidence; no parity inferred'});sys.exit()
final=[];rf=O/'reader_error.rs';rf.write_text('pub fn observe(c: &ty_ide::Completion<\'_>) { if let Some(d) = &c.documentation { let _ = d.render(); } }\n');ok=O/'reader_good.rs';ok.write_text(rf.read_text().replace('d.render()','d.render(ty_ide::MarkupKind::PlainText)'));base=O/'reader-output';base.mkdir();argindex=0;allsearch=[];seen=set()
for a in args:
 if a.startswith(('-Ldependency=','dependency=','-Lnative=','native=')):
  ac=a[2:] if a.startswith('-L') else a;ls=ac.split('=',1)[1]
  if (ac,ls) not in seen:seen.add((ac,ls));allsearch+=['-L',ac]
# Include the exact foreign --extern owners' directories as well as the linked lib search path.
for a in args:
 if '=' not in a or a.startswith('-'):continue
 raw=a.split('=',1)[1]
 if not raw.endswith(('.rmeta','.rlib','.so')) or not raw.startswith('/'):continue
 entry='dependency='+str(Path(raw).parent)
 if (entry,str(Path(raw).parent)) not in seen:seen.add((entry,str(Path(raw).parent)));allsearch+=['-L',entry]
for phys,diskview in (('original','original'),('edited','edited'),('original','edited'),('edited','original')):
 for rv in (rf,ok):
  cmd=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','--crate-name','external_scope_probe','--crate-type=lib','--emit=metadata','--error-format=json','--extern','ty_ide='+str(prod[phys]),*allsearch,str(rv),'-o',str(base/'probe.rmeta')];q=call(cmd,view=diskview);msgs=[json.loads(l) for l in q.stderr.splitlines() if l.startswith(b'{')];code=[v for v in msgs if (v.get('code') or {}).get('code')=='E0061'];roots=[sp for v in code for ch in [v,*v.get('children',[])] for sp in ch.get('spans',[]) if sp.get('file_name','').endswith('crates/ty_ide/src/docstring.rs')];row={'input_metadata_state':phys,'disk_source_state':diskview,'reader':rv.name,'source_sha256':sha(rv),'status':q.returncode,'metadata_sha256':sha(prod[phys]),'compiler_argv_sha256':H0(json.dumps(cmd).encode()),'stdout_sha256':H0(q.stdout),'foreign_definition_spans':roots,'all_diagnostics':msgs};final.append(row);print('ordinary',phys,diskview,rv.name,q.returncode,[(x['line_start'],x['column_start'],len(x['text'])) for x in roots],flush=True)
# This source-consuming proc macro records its external input path explicitly. It observes the real file even when its test module is logically inactive.
pm=O/'raw_observer.rs';pm.write_text('#![feature(proc_macro_tracked_path)]\nextern crate proc_macro; use proc_macro::TokenStream; #[proc_macro] pub fn measure_source(_:TokenStream)->TokenStream {let p="'+str(RUFF/f)+'"; proc_macro::tracked::path(p); std::fs::metadata(p).unwrap().len().to_string().parse().unwrap()}\n');mp=O/'libraw_observer.so';pc=['rustc','+ohm','--sysroot',str(FROZEN),'--crate-name','raw_observer','--edition=2024','--crate-type=proc-macro',str(pm),'-o',str(mp)];pq=call(pc);(O/'raw_observer-build.stderr').write_bytes(pq.stderr);macro=[]
if pq.returncode==0:
 cr=O/'raw_source_client.rs';cr.write_text('const SOURCE_LENGTH: usize = raw_observer::measure_source!(); fn main(){ println!("{SOURCE_LENGTH}"); }\n')
 for src in ('original','edited'):
  d=O/('raw-source-client-'+src);d.mkdir();cmd=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','--crate-name','raw_source_client','--crate-type=bin','--emit=dep-info,link','--extern','raw_observer='+str(mp),str(cr),'--out-dir',str(d)];q=call(cmd,view=src);(d/'stderr').write_bytes(q.stderr);dr=d/'raw_source_client.d';value=None;path_tracked=False
  if q.returncode==0:
   value=subprocess.check_output([str(d/'raw_source_client')],text=True).strip();path_tracked=str(RUFF/f).encode() in dr.read_bytes();assert int(value)==(Q/'fixture'/src/Path(f).name).stat().st_size and path_tracked
  macro.append({'source':src,'compiler_status':q.returncode,'runtime_stdout':value,'source_tracked_in_real_depinfo':path_tracked,'stderr_sha256':H0(q.stderr),'depinfo_sha256':sha(dr) if dr.is_file() else None})
dump(O/'macro-headers.json',{'macro_source_sha256':sha(pm),'macro_build_status':pq.returncode,'macro_build_stderr':pq.stderr.decode(errors='replace'),'rows':macro});dump(O/'external-readers.json',final);dump(O/'complete.json',{'clean_compiler_complete':True,'external_readers':len(final),'macro':macro})
