from pathlib import Path
import ast, hashlib, json, os, shutil, subprocess, sys
B=Path(__file__).resolve().parent;OPS=B/'ops';binroot=B/'bin';binroot.mkdir();out=B/'setup';out.mkdir()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):
 with p.open('x') as f:json.dump(x,f,sort_keys=True,indent=2);f.write('\n')
def command(argv,**kw):return subprocess.run(argv,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw).stdout.decode().strip()
def guard(initial=False):
 def free(p):return shutil.disk_usage(p).free
 avail=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
 assert avail>(72 if initial else 52)*2**30 and free(B)>52*2**30 and free(os.environ['QA_HOME_VOLUME'])>140*2**30
 return [avail,free(B),free(os.environ['QA_HOME_VOLUME'])]
assert set(os.sched_getaffinity(0))==set(range(4))
start=guard(True)
proxy=Path(os.environ['QA_RUSTUP_PROXY'])
for name in ('rustc','cargo','rustup'):(binroot/name).symlink_to(proxy)
base=Path(os.environ['QA_PARENT_SDK'])
fix=Path(os.environ['QA_GUARDED_SDK'])
build=Path(os.environ['QA_GUARDED_PRODUCT_DIR'])
assert sha(build/'product.json')=='8d2f4d444d55bcdd5910886f51859b18fceb019e82631fb7629dcff0232a2f6f'
cases={'P':(base,'66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e','7e71d3150938ff8ed82aca03416439d7e5b87ef3'),'G':(fix,'b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c','6b7f424ece4bc978ead5546b73e1b31d5ccb1e70')}
inputs=B/'checkouts';inputs.mkdir();seed=inputs/'origin';seed.mkdir()
def git(*args,cwd=seed):return command(['git','-c','user.name=Ohm native QA','-c','user.email=fixture@example.invalid',*args],cwd=cwd,env={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'})
git('init','-q','-b','qa_A')
for branch,value in [('A',17),('B',29),('C',41)]:
 if branch!='A':git('checkout','-q','-b','qa_'+branch)
 (seed/'main.rs').write_text((OPS/'main.rs.in').read_text().replace('VALUE',str(value)));git('add','main.rs');git('commit','-qm','fixture '+branch)
for name in 'ABC':
 dst=inputs/name;git('clone','--quiet','--no-hardlinks','--branch','qa_'+name,str(seed),str(dst),cwd=inputs)
 assert git('symbolic-ref','HEAD',cwd=dst)=='refs/heads/qa_'+name and git('status','--porcelain',cwd=dst)==''
roots={n:{'head':git('rev-parse','HEAD',cwd=inputs/n),'symbolic':git('symbolic-ref','HEAD',cwd=inputs/n),'source':sha(inputs/n/'main.rs')} for n in 'ABC'}
assert len({x['head'] for x in roots.values()})==3 and len({x['source'] for x in roots.values()})==3
source=out/'cargo-probe';(source/'src').mkdir(parents=True)
(source/'Cargo.toml').write_text('[package]\nname="visit_guard_mode"\nversion="0.1.0"\nedition="2021"\n[profile.dev]\ndebug=0\nincremental=true\n')
(source/'Cargo.lock').write_text('version = 4\n[[package]]\nname = "visit_guard_mode"\nversion = "0.1.0"\n');(source/'src/main.rs').write_text('fn main() { println!("enrolled"); }\n')
analyzer=OPS/'trace_exec.py';sys.path.insert(0,str(analyzer.parent));from trace_exec import collect_execs
kits={}
for key,(sdk,driver_sha,commit) in cases.items():
 guard();r=out/key;r.mkdir();(r/'rustup/toolchains').mkdir(parents=True);(r/'rustup/toolchains/ohm').symlink_to(sdk); (r/'home').mkdir()
 driver,=list((sdk/'lib').glob('librustc_driver-*.so'));assert sha(driver)==driver_sha
 assert sha(sdk/'bin/cargo')=='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add'
 env={'PATH':str(binroot)+':/usr/bin:/bin','HOME':str(r/'home'),'CARGO_HOME':str(r/'cargo-home'),'RUSTUP_HOME':str(r/'rustup'),'CARGO_TARGET_DIR':str(r/'target'),'CARGO_BUILD_BUILD_DIR':str(r/'shared'),'CARGO_NET_OFFLINE':'true','CARGO_CACHE_AUTO_CLEAN_FREQUENCY':'never','CARGO_TERM_COLOR':'never','LANG':'C','LC_ALL':'C','CARGO_INCREMENTAL':'1'}
 vv=command([str(binroot/'rustc'),'+ohm','-vV'],env=env);vvc=command([str(binroot/'cargo'),'+ohm','-Vv'],env=env)
 tr=r/'trace';tr.mkdir();argv=['/usr/bin/strace','-ff','-qq','-s','131072','-e','trace=execve,execveat,exit_group','-o',str(tr/'exec'),str(binroot/'cargo'),'+ohm','build','--locked','--offline','--message-format=json','-j1']
 with (r/'cargo.stdout').open('xb') as u,(r/'cargo.stderr').open('xb') as e:c=subprocess.run(argv,cwd=source,env=env,stdout=u,stderr=e,timeout=85)
 assert c.returncode==0,(r,c.returncode,(r/'cargo.stderr').read_text()[-650:])
 ex,raw,ct,_=collect_execs(tr);arr=[a for (exe,a),count in ex.items() if exe.endswith('/bin/rustc') and '--crate-name' in a and 'visit_guard_mode' in a];assert len(arr)==1
 a=arr[0];g=[word for word in a if word.split('=')[0]=='-Zohm-check-relink-inputs'];assert len(g)==1 and g[0] in ('-Zohm-check-relink-inputs','-Zohm-check-relink-inputs=yes'),g
 nativeflags=[]
 for i,arg in enumerate(a):
  if arg=='-C' and (a[i+1].startswith(('linker=','link-arg='))):nativeflags.extend([arg,a[i+1]])
  elif arg.startswith(('-Clinker=','-Clink-arg=')):nativeflags.append(arg)
 stock=[(exe,cmd) for (exe,cmd),cnt in ex.items() if exe.endswith('/wild-ld/ld.bfd') and '-o' in cmd and '--gc-sections' in cmd]
 assert len(stock)==1,(nativeflags,[(exe,len(cmd)) for (exe,cmd),_ in ex.items() if '-o' in cmd])
 assert command([str(r/'target/debug/visit_guard_mode')],env=env)=='enrolled'
 wild=Path(stock[0][0]);assert sha(wild)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
 proc=r/'liblock_qa_gate.so';macro=[str(binroot/'rustc'),'+ohm','--edition=2021','--crate-name','lock_qa_gate','--crate-type','proc-macro',str(OPS/'gate.rs'),'-Cdebuginfo=0',*nativeflags,'-o',str(proc)]
 with (r/'macro.stdout').open('xb') as u,(r/'macro.stderr').open('xb') as e:c=subprocess.run(macro,env=env,stdout=u,stderr=e,timeout=40)
 assert c.returncode==0,(r,(r/'macro.stderr').read_text()[-800:])
 save(r/'cargo-job.json',{'argv':a,'cargo_command':argv,'kernel':raw,'files':ct,'wild_argv':stock[0][1]})
 kits[key]={'sdk':str(sdk),'driver':driver_sha,'source':commit,'rustc':sha(sdk/'bin/rustc'),'cargo':sha(sdk/'bin/cargo'),'stock_wild':sha(wild),'env':env,'rustc_vv':vv,'cargo_vv':vvc,'guard':g,'link_flags':nativeflags,'proc_macro':str(proc),'proc_macro_sha':sha(proc),'cargo_job_sha':sha(r/'cargo-job.json')}
assert kits['P']['rustc']==kits['G']['rustc'] and kits['P']['rustc_vv']==kits['G']['rustc_vv']
save(out/'qualified.json',{'kits':kits,'checkouts':roots,'start':start,'end':guard(),'build_product_sha':sha(build/'product.json'),'build_complete_sha':sha(build/'completion.json'),'trace_parser_sha':sha(analyzer)})
print('setup green',sha(out/'qualified.json'),flush=True)
