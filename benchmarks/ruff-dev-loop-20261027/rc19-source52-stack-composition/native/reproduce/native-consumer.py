"""Check a real downstream executable after Rust and static-C implementation changes."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('sdk',type=Path);parser.add_argument('out',type=Path)
args=parser.parse_args();root=args.out.resolve();root.mkdir(mode=0o700);sdk=args.sdk.resolve(strict=True)
def sha(file):
 with Path(file).open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def store(f,data):f.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
w=root/'project';top=w/'app';mid=w/'middle';pr=w/'producer'
for path in (top,mid,pr):(path/'src').mkdir(parents=True)
(w/'Cargo.toml').write_text('[workspace]\nmembers=["app","middle","producer"]\nresolver="3"\n')
for path,dep in [(top,'middle'),(mid,'producer'),(pr,None)]:
 (path/'Cargo.toml').write_text(f'[package]\nname="{path.name}"\nversion="0.1.0"\nedition="2024"\n'+(f'[dependencies]\n{dep}={{path="../{dep}"}}\n' if dep else ''))
(top/'src/main.rs').write_text('fn main(){println!("{}",middle::value());}\n')
(mid/'src/lib.rs').write_text('pub fn value()->i32 { producer::value() }\n')
def rust(value):
 (pr/'src/lib.rs').write_text('unsafe extern "C" { fn native_value() -> i32; }\n#[inline(never)] fn delta() -> i32 { '+str(value)+' }\npub fn value() -> i32 { let value=unsafe {native_value()}; value+delta() }\n')
def c(value):(pr/'native.c').write_text(f'int native_value(void) {{ return {value}; }}\n')
rust(0);c(17)
(pr/'build.rs').write_text('''use std::{env, path::PathBuf, process::Command};
fn main(){
    let dir=PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let object=dir.join("native.o");
    assert!(Command::new("cc").args(["-fPIC","-c","native.c","-o"]).arg(&object).status().unwrap().success());
    assert!(Command::new("ar").arg("crs").arg(dir.join("liborigin52.a")).arg(&object).status().unwrap().success());
    println!("cargo::rerun-if-changed=native.c");
    println!("cargo::rustc-link-search=native={}",dir.display());
    println!("cargo::rustc-link-lib=static=origin52");
}
''')
alias=root/'rustup/toolchains';alias.mkdir(parents=True);(alias/'ohm').symlink_to(sdk,target_is_directory=True)
proxy=shutil.which('cargo');assert proxy
base={'PATH':os.environ['PATH'],'HOME':str(root),'CARGO_HOME':str(root/'home'),'RUSTUP_HOME':str(alias.parent),'RUSTUP_AUTO_INSTALL':'0','CARGO_NET_OFFLINE':'true','CARGO_INCREMENTAL':'0','LANG':'C','LC_ALL':'C'}
subprocess.run([proxy,'+ohm','generate-lockfile','--offline'],env=base,cwd=w,check=True)
raw_crates={};rows=[];source_fingerprint={}
def run(phase,pkg,verdict,history='warm',fresh=False):
 target=root/('target-'+history);shared=root/('build-'+history);env=base|{'CARGO_TARGET_DIR':str(target),'CARGO_BUILD_BUILD_DIR':str(shared)}
 cmd=[proxy,'+ohm','--config','build.rustflags=["-Zpublic-api-hash"]','build','--locked','--offline','-j2','--message-format=json','-p',pkg]
 log=root/(phase+'.exec');work=subprocess.run(['strace','-ff','-qq','-s','8192','-e','trace=execve,execveat','-o',str(log),*cmd],env=env,cwd=w,capture_output=True)
 for k,v in [('stdout',work.stdout),('stderr',work.stderr)]: (root/(phase+'.'+k)).write_bytes(v)
 jobs=[];native=[];tools=[];children=sorted(root.glob(phase+'.exec.*'));assert children
 traces={f.name.rsplit('.',1)[1]:sha(f) for f in children}
 log.write_bytes(b''.join(f.read_bytes() for f in children))
 for line in log.read_text().splitlines():
  if re.search(r' = 0$',line) is None:continue
  mm=re.search(r'execve\(("(?:[^"\\]|\\.)*"), \[(.*?)\],',line)
  if not mm:continue
  path=json.loads(mm[1]);argv=json.loads('['+mm[2]+']');name=Path(path).name
  if name=='rustc' and '--crate-name' in argv and any(a.startswith('--emit=') for a in argv) and argv[argv.index('--crate-name')+1]!='___':
   if Path(path).resolve()==Path(proxy).resolve():continue
   crate=argv[argv.index('--crate-name')+1];assert Path(path).resolve()==(sdk/'bin/rustc').resolve();jobs.append(crate)
  if name in ('cc','gcc','ar','rust-lld','ld','ld.bfd','ld.lld','wild','collect2') or name.endswith(('-ld','-gcc','-cc','-ar')):native.append(name)
  tools.append([name,hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()])
 parsed=list(map(json.loads,work.stdout.splitlines()));success=verdict!='invalid'
 assert work.returncode==(0 if success else 101) and parsed[-1]=={'reason':'build-finished','success':success},(phase,work.returncode,work.stderr[-2400:])
 arts=[x for x in parsed if x['reason']=='compiler-artifact']
 cache={}
 for container in (target,shared):
  for f in container.rglob('libmiddle-*.rmeta'):
   assert f.is_file();s=f.stat();cache[str(f.relative_to(container))]={'sha256':sha(f),'length':s.st_size,'mtime_ns':s.st_mtime_ns}
 fps=[]
 for container in (target,shared):
  for f in container.rglob('*.public-api-hash'):
   if f.is_file() and f.name.startswith('lib-'):fps.append([f.name,sha(f)])
 appinfo=None
 if isinstance(verdict,int):
  app,=[Path(x['executable']) for x in arts if x['target']['name']=='app' and x.get('executable')]
  actual=subprocess.run([app],capture_output=True,check=True);assert actual.stdout==f'{verdict}\n'.encode() and not actual.stderr
  appinfo={'value':verdict,'elf_sha256':sha(app),'bytes':app.stat().st_size}
 if not success:assert b'origin52_current_native_invalid_source' in work.stderr and any(x in ('cc','gcc') or x.endswith('-gcc') for x in native)
 if fresh:assert arts and all(x['fresh'] for x in arts) and not jobs and not native,(phase,jobs,native)
 if phase in ('original','private-rust-independent'):
  assert set(jobs)>={'app','producer','middle','build_script_build'} and any(x in ('cc','gcc') or x.endswith('-gcc') for x in native) and 'ar' in native and fps
 if phase=='native-relinked':assert jobs and appinfo and native
 rows.append({'phase':phase,'exit':work.returncode,'selected':pkg,'state':history,'program':appinfo,'middle_metadata':cache,'public_hashes':sorted(fps),'typed':[[a['target']['name'],a['fresh']] for a in arts],'real_compilers':jobs,'native_commands':native,'successful_execs':tools,'raw_exec':sha(log),'raw_children':traces,'stdout':sha(root/(phase+'.stdout')),'stderr':sha(root/(phase+'.stderr')),'source_rust':sha(pr/'src/lib.rs'),'source_c':sha(pr/'native.c')})
 store(root/'progress.json',rows)
run('original','app',17);run('original-repeat','app',17,fresh=True)
c(29);run('native-producer','producer',None);run('native-relinked','app',29);run('native-repeat','app',29,fresh=True)
rust(1);run('private-rust-edit','app',30);run('private-rust-repeat','app',30,fresh=True);run('private-rust-independent','app',30,'vacant-edited')
(pr/'native.c').write_text('#error origin52_current_native_invalid_source\n')
run('invalid-warm','app','invalid');run('invalid-vacant','app','invalid','vacant-invalid')
rust(0);c(17);run('restored','app',17);run('restored-repeat','app',17,fresh=True)
store(root/'result.json',{'cargo':sha(sdk/'bin/cargo'),'rustc':sha(sdk/'bin/rustc'),'sdk_rust':subprocess.check_output([sdk/'bin/rustc','-Vv']).decode(),'lock':sha(w/'Cargo.lock'),'cases':rows})
print('checked',len(rows),[x['program']['value'] for x in rows if x['program']])
