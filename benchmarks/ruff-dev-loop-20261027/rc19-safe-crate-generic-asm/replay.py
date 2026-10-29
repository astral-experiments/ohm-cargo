"""Cross-crate monomorphization of assembler file access in an untouched safe binary."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
d=Path(sys.argv[1]).absolute(); sdk=Path(sys.argv[2]).resolve()
if d.exists():raise SystemExit('use a new directory')
d.mkdir(mode=0o700)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def put(f,s):f.parent.mkdir(exist_ok=True,parents=True);f.write_text(s)
def report(f,x):put(f,json.dumps(x,indent=2,sort_keys=True)+'\n')
proxy=Path(shutil.which('cargo')).absolute();assert proxy.name=='cargo'
rustup=d/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk,target_is_directory=True)
env=dict(HOME=str(d/'home'),CARGO_HOME=str(d/'cargo-home'),RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',PATH=str(proxy.parent)+':/usr/bin:/bin',LANG='C.UTF-8',TERM='dumb',CARGO_INCREMENTAL='0')
for s in ('home','cargo-home'):(d/s).mkdir()
gen='''pub fn payload<T>() -> u32 {
    let byte: u32;
    unsafe { core::arch::asm!(
        "jmp 3f", "2:", ".incbin \\"untracked.bin\\"", "3:", "movzx {byte:e}, byte ptr [rip + 2b]",
        byte = out(reg) byte, options(nostack, preserves_flags),
    ); }
    byte
}
'''
app='''#![forbid(unsafe_code)]
fn main() { println!("{}:{}", revision::value(), engine::payload::<u32>()); }
'''
def revision(x):return '#[inline(never)]\npub fn value() -> u32 { '+str(x)+' }\n'
def project(root):
 put(root/'Cargo.toml','[workspace]\nmembers=["engine","revision","app"]\nresolver="2"\n')
 for name in ['engine','revision','app']:
  txt='[package]\nname="'+name+'"\nversion="0.1.0"\nedition="2021"\n'
  if name=='app': txt+='[dependencies]\nengine={path="../engine"}\nrevision={path="../revision"}\n'
  put(root/name/'Cargo.toml',txt)
 put(root/'engine/src/lib.rs',gen);put(root/'app/src/main.rs',app);put(root/'revision/src/lib.rs',revision(5))
def sub(c,root,e):return subprocess.run(c,cwd=root,env=e,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
def action(name,root,state,flags):
 out=d/'commands'/name;out.mkdir(parents=True)
 e=env|{'CARGO_TARGET_DIR':str(state/'target'),'CARGO_BUILD_BUILD_DIR':str(state/'shared')}
 cmd=['cargo','+ohm',*flags,'build','-p','app','--offline','-j2','-vv','--message-format=json']
 p=sub(cmd,root,e);(out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 js=[json.loads(x) for x in p.stdout.splitlines() if x.startswith(b'{')];assert js[-1]['reason']=='build-finished' and js[-1]['success']==(p.returncode==0)
 inv=[x for x in p.stderr.decode().splitlines() if 'Running ' in x and '--crate-name ' in x]; comp=[{'name':x.split('--crate-name ',1)[1].split(' ',1)[0],'link_only':'-Z link-only' in x or '-Zlink-only' in x} for x in inv]
 a={'status':p.returncode,'compiler':comp,'sources':{str(f.relative_to(root)):sha(f) for f in sorted(root.rglob('*.rs'))},'depfiles':[],'successful':js[-1]['success']}
 for f in sorted(state.rglob('app-*.d')):
  if f.is_file():
   contents=f.read_bytes();(out/(str(len(a['depfiles']))+'.d')).write_bytes(contents);a['depfiles'].append({'sha':sha(f),'payload_named':b'untracked.bin' in contents,'local_main':b'app/src/main.rs' in contents})
 if p.returncode==0:
  exe,=[x['executable'] for x in js if x.get('executable') and x['target']['name']=='app']
  r=sub([exe],root,e); assert r.returncode==0;a.update(value=r.stdout.decode().strip(),elf=sha(Path(exe)),target_fresh=[x['fresh'] for x in js if x['reason']=='compiler-artifact' and x['target']['name']=='app'][0])
 else:a['missing']=b'untracked.bin' in p.stdout+p.stderr
 report(out/'result.json',a);print(name,a['status'],a.get('value'),comp,flush=True);return a
rows={}
for arm,flags in [('default',[]),('full',['-Zrelink-only=no'])]:
 root=d/arm/'project';project(root);state=d/arm/'live-state';payload=root/'untracked.bin';payload.write_bytes(bytes([17]))
 rows[arm+'.initial']=action(arm+'.initial',root,state,flags)
 put(root/'revision/src/lib.rs',revision(9));payload.write_bytes(bytes([29]))
 rows[arm+'.edited']=action(arm+'.edited',root,state,flags)
 rows[arm+'.repeat']=action(arm+'.repeat',root,state,flags)
 rows[arm+'.empty-edited']=action(arm+'.empty-edited',root,d/arm/'empty-edited',flags)
 put(root/'revision/src/lib.rs',revision(7));payload.unlink()
 rows[arm+'.missing']=action(arm+'.missing',root,state,flags)
 rows[arm+'.empty-missing']=action(arm+'.empty-missing',root,d/arm/'empty-missing',flags)
 put(root/'revision/src/lib.rs',revision(5));payload.write_bytes(bytes([17]));rows[arm+'.restore']=action(arm+'.restore',root,state,flags)
report(d/'results.json',{'cargo':sha(sdk/'bin/cargo'),'rustc':sha(sdk/'bin/rustc'),'rows':rows})
