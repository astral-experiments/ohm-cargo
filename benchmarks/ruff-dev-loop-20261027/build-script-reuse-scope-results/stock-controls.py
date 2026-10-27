"""Demonstrate which build-script effects are observable by a downstream compiler, native linker or proc macro."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');D=P/'build-script-producer-reuse16-v1';Q=D/'stock-controls-v1';Q.mkdir(exist_ok=False)
import fcntl
lock=(P/'native-measure.lock').open('rb');fcntl.flock(lock,fcntl.LOCK_EX)
rt=D/'rustup';sdk=D/'sdk';cargo=sdk/'bin/cargo';driver,=(sdk/'lib').glob('librustc_driver*.so');son=driver
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,d):p.write_text(json.dumps(d,sort_keys=True,indent=2)+'\n')
binding={'cargo':h(cargo),'frontend':h(sdk/'bin/rustc'),'driver':h(driver)};assert binding=={'cargo':'42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568','frontend':'b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5','driver':'c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4'}
put(Q/'toolchain.json',binding)
pm='''#![feature(proc_macro_tracked_path)]
extern crate proc_macro;
#[proc_macro]
pub fn outside_value(_:proc_macro::TokenStream)->proc_macro::TokenStream {
 let path=std::env::var("CARGO_MANIFEST_DIR").unwrap()+"/outside.txt";
 proc_macro::tracked::path(&path);
 std::fs::read_to_string(path).unwrap().trim().parse().unwrap()
}
'''
parts={
'watch-only':('println!("cargo::rerun-if-changed=watch-{}.txt",v);', 'fn main(){println!("41");}'),
'environment':('println!("cargo::rustc-env=SEEN={}",v);', 'fn main(){println!("{}",env!("SEEN"));}'),
'generator':('std::fs::write(std::path::Path::new(&std::env::var_os("OUT_DIR").unwrap()).join("number.txt"),v).unwrap();','fn main(){print!("{}",include_str!(concat!(env!("OUT_DIR"),"/number.txt")));}'),
'outside-include':('std::fs::write("outside.txt",v).unwrap();','fn main(){print!("{}",include_str!("../outside.txt"));}'),
'outside-proc':('std::fs::write("outside.txt",v).unwrap();','fn main(){print!("{}",observation_macro::outside_value!());}'),
'library-order':('''
 let path=std::env::current_dir().unwrap().join("native");
 println!("cargo::rustc-link-search=native={}",path.display());
 let names = if v=="41" { ["first","second"] } else { ["second","first"] };
 for n in names { println!("cargo::rustc-link-lib=static={n}"); }
''','unsafe extern "C"{fn observed_number()->i32;}fn main(){println!("{}",unsafe{observed_number()});}'),
'outside-archive':('''
 use std::process::Command;
 let path=std::env::current_dir().unwrap().join("native");
 let source=path.join("value.c");let object=path.join("value.o");let archive=path.join("libmutable.a");
 std::fs::write(&source,format!("int observed_number(void){{return {v};}}")).unwrap();
 assert!(Command::new("cc").arg("-c").arg(source).arg("-o").arg(&object).status().unwrap().success());
 assert!(Command::new("ar").arg("rcs").arg(archive).arg(object).status().unwrap().success());
 println!("cargo::rustc-link-search=native={}",path.display());println!("cargo::rustc-link-lib=static=mutable");
''','unsafe extern "C"{fn observed_number()->i32;}fn main(){println!("{}",unsafe{observed_number()});}')}
def command(z,cf,tag,target):
 ws=z/'ws';rec=z/tag;rec.mkdir();target=z/target;shared=target.with_name(target.name+'-shared');e=dict(os.environ,RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',RUSTUP_HOME=str(rt),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_HOME=str(z/'cargo-home'),CARGO_BUILD_JOBS='2',RUSTC=str(sdk/'bin/rustc'),GIT_OPTIONAL_LOCKS='0')
 for k in ('RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_ENCODED_RUSTFLAGS','RUSTFLAGS','RUSTC_LOG'):e.pop(k,None)
 cmd=['taskset','-c','0-3','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(z),str(z),'--ro-bind',str(cargo),str(sdk/'bin/cargo'),'--ro-bind',str(driver),str(son),'--chdir',str(ws),'--','strace','-f','-qq','-s','16384','-e','trace=execve','-o',str(rec/'physical.exec'),str(Path.home()/'.cargo/bin/cargo'),'+ohm','build','--offline','--message-format=json','-j2']
 r=subprocess.run(cmd,env=e,capture_output=True,timeout=120);(rec/'cargo.stderr').write_bytes(r.stderr);(rec/'cargo.stdout').write_bytes(r.stdout);assert r.returncode==0,(cf,tag,r.stderr.decode()[-1600:])
 items=[json.loads(l) for l in r.stdout.splitlines()];ar=[a for a in items if a.get('reason')=='compiler-artifact'];s,=[a for a in items if a['reason']=='build-script-executed' and a['package_id'].split('#',1)[0].endswith('/ws')];od=Path(s['out_dir']);logs=[p/n for p in (od.parent,od.parent/'run') for n in ('output','stdout')];opp=next(p for p in logs if p.is_file());pt=next(Path(a['executable']) for a in ar if a.get('executable'));executed=subprocess.run([str(pt)],capture_output=True,timeout=3);dp={str(p):p.read_text() for p in target.rglob('observation_probe-*.d') if p.is_file()};trace=(rec/'physical.exec').read_text();q={'argv':cmd,'build_returncode':r.returncode,'program_returncode':executed.returncode,'program_stdout':executed.stdout.decode().strip(),'program_stderr':executed.stderr.decode(),'executable_sha256':h(pt),'cargo_fresh':[[a['target']['name'],a['fresh']] for a in ar],'build_script_stdout':opp.read_text().splitlines(),'cargo_build_script':s,'out_contents':{str(p.relative_to(od)):h(p) for p in od.rglob('*') if p.is_file()},'outside_bytes':{str(p.relative_to(ws)):h(p) for p in [ws/'outside.txt',*list((ws/'native').glob('*.a'))] if p.is_file()},'dep_info':dp,'physical_rustc_builds':[l for l in trace.splitlines() if l.endswith('= 0') and 'execve("'+str(sdk/'bin/rustc')+'"' in l and '"--crate-name", "observation_probe"' in l],'linker':[l for l in trace.splitlines() if l.endswith('= 0') and 'wild-ld/ld.bfd"' in l and 'execve(' in l]};put(rec/'result.json',q);return q
summary={}
for case,(work,consumer) in parts.items():
 z=Q/case;ws=z/'ws';(ws/'src').mkdir(parents=True);(ws/'src/main.rs').write_text(consumer+'\n');(ws/'native').mkdir();(ws/'Cargo.toml').write_text('[package]\nname="observation_probe"\nversion="0.1.0"\nedition="2024"\n'+('[dependencies]\nobservation_macro={path="macro"}\n' if case=='outside-proc' else ''));(ws/'build.rs').write_text('fn main(){println!("cargo::rerun-if-changed=trigger.txt");let source=std::fs::read_to_string("trigger.txt").unwrap();let v=source.trim();\n'+work+'\n}\n');(ws/'outside.txt').write_text('41')
 for n in ('41','83'):(ws/('watch-'+n+'.txt')).write_text('unchanged\n')
 if case=='outside-proc':
  (ws/'macro/src').mkdir(parents=True);(ws/'macro/Cargo.toml').write_text('[package]\nname="observation_macro"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n');(ws/'macro/src/lib.rs').write_text(pm)
 if case=='library-order':
  for name,num in [('first',41),('second',83)]:
   src=ws/'native'/(name+'.c');src.write_text(f'int observed_number(void){{return {num};}}\n');o=src.with_suffix('.o');subprocess.run(['cc','-c',str(src),'-o',str(o)],check=True);subprocess.run(['ar','rcs',str(o.with_name('lib'+name+'.a')),str(o)],check=True)
 results={};trigger=ws/'trigger.txt'
 for tag,value,target in [('prime','41','active'),('warm-original','41','active'),('edit','83','active'),('warm-edited','83','active'),('empty-edited','83','independent'),('restore','41','active')]:
  if not trigger.is_file() or trigger.read_text()!=value:trigger.write_text(value)
  q=command(z,case,tag,target);expected='41' if case=='watch-only' else value
  assert q['program_returncode']==0,(case,tag,q['program_returncode']);results[tag]={'stdout':q['program_stdout'],'expected':expected,'correct':q['program_stdout']==expected,'consumer_compilers':len(q['physical_rustc_builds']),'native_linkers':len(q['linker']),'stdout_of_script':q['build_script_stdout'],'out_files':q['out_contents'],'outside_files':q['outside_bytes'],'ELF':q['executable_sha256']}
 summary[case]=results;put(Q/'result.json',summary)
print(json.dumps(summary))
