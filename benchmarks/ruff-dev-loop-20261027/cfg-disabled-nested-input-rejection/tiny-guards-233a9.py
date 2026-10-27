"""Behavior of selected and rejected real Cargo/rustc/Wild integration test jobs."""
from pathlib import Path
import ast, hashlib, json, os, re, shutil, subprocess as sp, sys

q=Path('/dev/shm/ohm-stdlib-native-scout-20261027')
d=Path('/mnt/devbox-scratch/dev-user/ohm-mixed-interface-20261027')
v=d/'sysroot'; release=d/'subjects-stock/stage2-sysroot'; son='librustc_driver-774a793a844d5500.so'
driver=d/'subjects-stock/stage2-233'/son
arm=sys.argv[1];work=q/('tiny-'+arm); work.mkdir(); src=work/'src';src.mkdir()
car=q/('cargo-'+arm.split('-')[0]) if not arm.startswith('baseline') else d/'product-tools/fifo-cargo'
sha=lambda f:hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
def put(rel,data): p=src/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
put('Cargo.toml','''[workspace]
members = ["kit", "mark"]
resolver = "2"
''')
put('kit/Cargo.toml','''[package]
name="kit"
version="0.1.0"
edition="2024"
[lib]
crate-type=["cdylib","rlib"]
[dev-dependencies]
mark={path="../mark"}
[lints.rust]
explicit_builtin_cfgs_in_flags="allow"
''')
put('mark/Cargo.toml','[package]\nname="mark"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n')
put('mark/src/lib.rs','''extern crate proc_macro;
#[proc_macro_attribute] pub fn expose(_:proc_macro::TokenStream,x:proc_macro::TokenStream)->proc_macro::TokenStream{
    let mut result:proc_macro::TokenStream = "#[test]".parse().unwrap(); result.extend(x); result
}
''')
put('kit/build.rs','''fn main(){
 println!("cargo:rerun-if-changed=mode");
 let m=std::fs::read_to_string("mode").unwrap();
 if m.contains("cfg"){println!("cargo:rustc-cfg=target_arch=\\"wasm32\\"");}
 if let Some(n)=m.strip_prefix("native"){println!("cargo:rustc-link-arg-tests=-Wl,--defsym,ohm_guard_marker={n}");}
}
''')
def val(n):put('kit/src/lib.rs',f'pub fn n()->usize {{ {n} }}\n')
def mode(m):put('kit/mode',m)
def basic(cfg='target_arch = "wasm32"'):
 put('kit/tests/api.rs',f'#![cfg({cfg})]\n#[test] fn active(){{assert_eq!(kit::n(),7);}}\n')
mode('');val(1);basic()
put('kit/tests/input.txt','apple')
wrap=work/'workspace-wrapper';wrap.write_text('''#!/usr/bin/env python3
import os,sys
a=sys.argv[1:]
if "--crate-name" in a and a[a.index("--crate-name")+1]=="api":
 for j,v in enumerate(a):
  if v.startswith("--emit="):a[j]=v+",mir="+os.environ["GUARD_MIR"]
os.execv(a[0],a)
''');wrap.chmod(0o755)
receipts={};out=work/'summaries';out.mkdir()
def run(label,*,api=None, names=None, execok=None, value='starter',wrapper=False, flags='', options=(),fail=False):
 p=work/label;p.mkdir()
 tgt=work/'target';shared=work/'shared';cargo_home=work/'cargo-home';[f.mkdir(exist_ok=True) for f in (tgt,shared,cargo_home)]
 env=dict(os.environ,RUSTUP_HOME=str(d/'rustup'),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_TARGET_DIR=str(tgt),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_HOME=str(cargo_home),CARGO_BUILD_JOBS='1',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',RUSTC=str(v/'bin/rustc'),LD_LIBRARY_PATH=str(v/'lib'),CARGO_LOG='cargo::compiler=info',QA_VALUE=value,GUARD_MIR=str(work/'api.mir'))
 for key in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','WILD_WRITE_LAYOUT']:env.pop(key,None)
 if wrapper:env['RUSTC_WORKSPACE_WRAPPER']=str(wrap)
 if flags:env['RUSTFLAGS']=flags
 cmd=['taskset','-c','4-7','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(work),str(work),'--ro-bind',str(release),str(v),'--ro-bind',str(driver),str(v/'lib'/son),'--ro-bind',str(car),str(v/'bin/cargo'),'--chdir',str(src),'--','strace','-qq','-ff','-s','65536','-e','trace=execve','-o',str(p/'exec'),'/home/dev-user/.cargo/bin/cargo','+ohm','test','--no-run','--offline','-p','kit','--test','api','--message-format=json',*options]
 with (p/'stdout').open('wb') as o,(p/'stderr').open('wb') as e:rc=sp.run(cmd,env=env,stdout=o,stderr=e).returncode
 artifacts=[];messages=[];rustcs=[];wild=[];link_probes=[];fixed_links=[];api_modes=[]
 for line in (p/'stdout').read_text().splitlines():
  j=json.loads(line)
  if j['reason']=='compiler-artifact' and j['target']['name']=='api':artifacts.append(Path(j['executable']))
  if j['reason']=='compiler-message':messages.append([j['target']['name'],j['message']['level'],j['message'].get('code'),j['message']['message']])
 for f in p.glob('exec.*'):
  for line in f.read_text(errors='replace').splitlines():
   m=re.match(r'execve\("([^"]*)", (\[.*\]), [^\n]*\) += 0$',line)
   if not m:continue
   exe,args=m[1],ast.literal_eval(m[2])
   if exe.endswith('/rustc') and '--crate-name' in args and args[args.index('--crate-name')+1]!='___':rustcs.append(args[args.index('--crate-name')+1])
   if exe.endswith('/rustc') and '--crate-name' in args and args[args.index('--crate-name')+1]=='api':api_modes.append('link-only' if '-Zlink-only' in args else 'full')
   if exe.endswith('/wild-ld/ld.bfd'):
    if '-o' in args:
     name=Path(args[args.index('-o')+1]).name;wild.append(name)
     if name.startswith('api-') and '--threads=1' in args:fixed_links.append(name)
    elif args[1:]==['--help']:link_probes.append('wild --help')
    else:raise ValueError(args)
   if Path(exe).name=='cc' and '-print-search-dirs' in args:link_probes.append('cc -print-search-dirs')
 res={'rc':rc,'rustcs':rustcs,'wild':wild,'native_probes':link_probes,'messages':messages,'fixed':fixed_links,'api_modes':api_modes}
 if not fail and rc==0:
  assert len(artifacts)==1;f=artifacts[0];manifest=f.with_suffix('.rlink-cache.json')
  res.update(elf=sha(f),tests=sp.check_output([f,'--list'],text=True),proof=(json.loads(manifest.read_bytes()).get('disabled_test') if manifest.is_file() else None),native=[l.split()[0] for l in sp.check_output(['nm','-a',f],text=True).splitlines() if l.endswith(' ohm_guard_marker')])
  if execok is not None:
   vrun=sp.run([f,'--quiet'],capture_output=True);res['execution_rc']=vrun.returncode;assert (vrun.returncode==0)==execok,(label,res)
 receipts[label]=res;(out/(label+'.json')).write_text(json.dumps(res,indent=2)+'\n');print(label,rc,res.get('tests','').strip(),rustcs,wild,bool(res.get('proof')),flush=True)
 assert (rc!=0)==fail,(label,rc,(p/'stderr').read_text()[-700:],messages)
 if api is not None:assert rustcs.count('api')==api,(label,res)
 if names is not None:assert names in res['tests'],(label,res)
 return res
base=arm.startswith('baseline');reuses=arm.startswith('a9c')
first=run('prime',api=1,names='0 tests');assert not first['fixed'] and first['api_modes']==['full'] and (base or first['proof']['fixed_worker']==False)
run('prime-fresh',api=0)
val(103);train=run('first-dirty-training',api=1,names='0 tests');assert bool(train['fixed'])==(not base) and train['api_modes']==['full'] and (base or train['proof']['fixed_worker'])
val(2);result=run('positive',api=int(not reuses),names='0 tests',execok=True);assert result['elf']==train['elf']
assert bool(result['fixed'])==(not base and not reuses)
val(1);rev=run('positive-return',api=int(not reuses),names='0 tests');assert rev['elf']==train['elf']
mode('cfg');run('cfg-active-fail',api=1,names='active: test',execok=False)
val(7);run('cfg-active-pass',api=1,names='active: test',execok=True)
mode('');run('cfg-removed',api=1,names='0 tests')
mode('native140');a=run('native-140',api=1,names='0 tests');assert a['native']==['000000000000008c']
mode('native141');a=run('native-141',api=1,names='0 tests');assert a['native']==['000000000000008d']
mode('');a=run('native-removed',api=1,names='0 tests');assert not a['native']
val(3);run('reset-proof',names='0 tests')
basic('target_arch="not_a_real_host_arch"');a=run('warning-prime',api=1);assert any('unexpected' in m[3] for m in a['messages'])
val(4);b=run('warning-dirty',api=1);assert a['messages']==b['messages']
basic();run('warn-removed',api=1)
val(5);run('wrapper-prime',wrapper=True,api=1);mir=work/'api.mir';assert mir.is_file();m=sha(mir);mir.unlink()
val(6);run('wrapper-dirty',wrapper=True,api=1);assert sha(mir)==m
run('user-rustflags',api=1,flags='--cfg user_opt');val(8);run('user-rustflags-dirty',api=1,flags='--cfg user_opt')
run('target-override-prime',api=1,options=['--target','x86_64-unknown-linux-gnu']);val(9);run('target-override-dirty',api=1,options=['--target','x86_64-unknown-linux-gnu'])
put('kit/tests/api.rs','''#![cfg(target_arch="x86_64")]
#[mark::expose] fn external_case() { assert_eq!(include_str!("input.txt"), env!("QA_VALUE")); }
''');run('active-attr-env-include',api=1,names='external_case: test',value='apple',execok=True)
put('kit/tests/input.txt','pear');run('active-include-changed',api=1,value='apple',execok=False)
run('active-env-changed',api=1,value='pear',execok=True)
put('kit/tests/api.rs','''#[link(name="ohm_missing_or_unsupported_native_input")] unsafe extern "C" { }
''');run('active-raw-native-missing',api=1,fail=True)
basic();run('normal-recovery',api=1,names='0 tests',execok=True);run('normal-fresh',api=0,names='0 tests')
for name in ['cfg-active-fail','cfg-active-pass','native-140','native-141','warning-prime','warning-dirty','wrapper-prime','wrapper-dirty','user-rustflags','target-override-prime','active-attr-env-include']:
 assert not receipts[name]['fixed'],(name,receipts[name]['fixed'])
(work/'complete.json').write_text(json.dumps({'cargo':sha(car),'rustc':sha(driver),'cases':receipts},indent=2)+'\n')
