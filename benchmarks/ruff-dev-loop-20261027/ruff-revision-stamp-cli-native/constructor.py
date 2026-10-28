"""Exercise arbitrary native initialization before a normal declarative macro loads its file."""
from pathlib import Path
import ast,collections,fcntl,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
src=ram/'native-constructor-fixture';out=q/'constructor';src.mkdir();out.mkdir()
inputs={'Cargo.toml':'[workspace]\nmembers=["activate","bridge","app"]\nresolver="3"\n',
'activate/Cargo.toml':'[package]\nname="activate"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n',
'activate/src/lib.rs':r'''extern crate proc_macro;
#[proc_macro]
pub fn never_expand(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    panic!("the test must never execute a procedural macro")
}
extern "C" fn init() {
    let (Some(file), Some(value)) = (std::env::var_os("OHM_CTOR_FILE"), std::env::var_os("OHM_CTOR_VALUE")) else { return };
    let value = value.to_str().unwrap();
    if value == "new" { eprintln!("constructor observed the new revision"); }
    if std::fs::read(&file).ok().as_deref() != Some(value.as_bytes()) {
        std::fs::write(file, value.as_bytes()).unwrap();
    }
}
#[used]
#[unsafe(link_section = ".init_array")]
static INIT: extern "C" fn() = init;
''','bridge/Cargo.toml':'[package]\nname="bridge"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nactivate={path="../activate"}\n',
'bridge/src/lib.rs':'''pub use activate::never_expand;
#[macro_export] macro_rules! read_payload { ($path:literal) => { include_str!($path) }; }
''','app/Cargo.toml':'[package]\nname="app"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nbridge={path="../bridge"}\n',
'app/build.rs':'''fn main() {
    println!("cargo::rerun-if-changed=revision");
    let mode = std::fs::read_to_string("revision").unwrap();
    let root = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    println!("cargo::rustc-env=OHM_CTOR_FILE={root}/src/payload");
    println!("cargo::rustc-env=OHM_CTOR_VALUE={mode}");
}
''','app/src/main.rs':'fn main() { println!("{}", bridge::read_payload!("payload")); }\n',
'app/src/payload':'old','app/revision':'old'}
for name,v in inputs.items():
 f=src/name;f.parent.mkdir(exist_ok=True,parents=True);f.write_text(v)
put(out/'source.json',inputs)
baseenv=dict(env);baseenv['CARGO_TARGET_DIR']=str(src/'target');baseenv['CARGO_BUILD_BUILD_DIR']=str(src/'build')
def run(cmd,en,where,stem):
 v=subprocess.run(list(map(str,cmd)),cwd=src,env=en,capture_output=True);(where/(stem+'.stdout')).write_bytes(v.stdout);(where/(stem+'.stderr')).write_bytes(v.stderr);assert v.returncode==0,(v.returncode,v.stderr[-950:]);return v
def cargo(tag,value):
 d=out/tag;d.mkdir();(d/'trace').mkdir();pl=src/'app/src/payload';pre=pl.read_bytes();(src/'app/revision').write_text(value)if (src/'app/revision').read_text()!=value else None
 tr=['strace','-ff','-q','-e','trace=execve','-s','131072','-e','signal=none','-o',d/'trace/exec'];args=['cargo','+ohm','build','--offline','--locked','-p','app','--message-format=json'];run([*tr,*args],baseenv,d,'cargo');read=lambda f:f.read_bytes()
 rows=[json.loads(x)for x in read(d/'cargo.stdout').splitlines()];assert rows[-1]=={'reason':'build-finished','success':True};arts=[x for x in rows if x['reason']=='compiler-artifact'];app,=[x for x in arts if x['target']['kind']==['bin']and x['target']['name']=='app'];usage={}
 for f in(d/'trace').glob('exec.*'):
  for l in f.read_bytes().splitlines():
   if not l.startswith(b'execve(')or not re.search(rb'\)\s+= 0$',l):continue
   m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',l);assert m
   imag=ast.literal_eval(m[1].decode());a=ast.literal_eval(m[2].decode())
   if Path(imag).name=='rustc'and '--crate-name'in a and '--out-dir'in a and a[a.index('--crate-name')+1]=='app':
    assert 'app'not in usage;usage['app']={'argv':a,'image':imag,'trace_sha':sha(f),'full':not any(s in ('link-only','-Zlink-only')for s in a)}
 if usage:
  a=usage['app']['argv'];od=Path(a[a.index('--out-dir')+1]);dep,=list(od.glob('app*.d'));raw=dep.read_bytes();(d/'app.d').write_bytes(raw);usage['d_inputs']=[v.decode()for v in raw.splitlines()if v.startswith((b'# env-dep:',b'# checksum:'))]
 z=run([app['executable']],baseenv,d,'app');rows={'expected':value,'before':pre.decode(),'after':pl.read_text(),'runtime':z.stdout.decode().strip(),'exe':sha(app['executable']),'units':len(arts),'fresh':sum(y['fresh']for y in arts),'compiler':usage,'warned':b'constructor observed the new revision'in read(d/'cargo.stderr')};put(d/'result.json',rows);print(tag,value,rows['before'],rows['runtime'],rows['after'],rows['warned'],bool(usage),flush=True);return rows
def main():
 guard()
 with(p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run(['cargo','+ohm','generate-lockfile','--offline'],baseenv,out,'lock')
  rs={n:cargo(n,v)for n,v in [('initial','old'),('settled','old'),('changed','new'),('repeat','new'),('restore','old')]}
  assert rs['changed']['compiler']['app']['full'] and rs['restore']['compiler']['app']['full']and rs['changed']['before']=='old'and rs['restore']['before']=='new'
  assert all(v['runtime']==v['expected']==v['after']for v in rs.values()) and rs['changed']['warned'] and not rs['initial']['warned']
  assert not any(x.startswith('# env-dep:OHM_CTOR')for row in rs.values()for x in row['compiler'].get('d_inputs',[]))
  current=rs['restore']['compiler']['app']['argv'];patched=list(current[1:]);audit=ram/'constructor-profile';audit.mkdir();(audit/'out').mkdir();(audit/'objects').mkdir()
  for i,x in enumerate(patched):
   if x.startswith('incremental='):patched[i]='incremental='+str(audit/'incremental')
   elif x.startswith('temps-dir='):patched[i]='temps-dir='+str(audit/'objects')
  patched[patched.index('--out-dir')+1]=str(audit/'out')
  audit_env=dict(baseenv,OHM_CTOR_VALUE='new',OHM_CTOR_FILE=str(src/'app/src/payload'),LD_DEBUG='files',LD_DEBUG_OUTPUT=str(audit/'ld'))
  assert (src/'app/src/payload').read_text()=='old';z=run(['rustc','+ohm',*patched,'-Zself-profile='+str(audit/'profile'),'-Zself-profile-events=generic-activity','-Zbinary-dep-depinfo'],audit_env,out,'profile')
  profiles=list(audit.rglob('*.mm_profdata'));assert len(profiles)==1;v=profiles[0].read_bytes();names=('expand_proc_macro','expand_attr_proc_macro_outer','expand_derive_proc_macro_outer')
  ln=[x.strip() for f in audit.glob('ld.*')for x in f.read_text().splitlines()if 'calling init:'in x and 'libactivate-'in x];assert ln and all(x.encode()not in v for x in names)
  assert b'constructor observed the new revision'in z.stderr and (src/'app/src/payload').read_text()=='new'
  e=audit/'out/app';assert run([e],baseenv,out,'profile-run').stdout==b'new\n'
  put(out/'done.json',{'ordinary':{k:[v['before'],v['runtime'],v['warned'],bool(v['compiler'])]for k,v in rs.items()},'silent_first':not rs['initial']['warned'],'loader':ln,'no_custom_expansion_profile':[x for x in names if x.encode()in v],'profile_hash':H(v),'probe_dll_listed':'libactivate-'in(audit/'out/app.d').read_text(),'status':0})
if __name__=='__main__':main()
