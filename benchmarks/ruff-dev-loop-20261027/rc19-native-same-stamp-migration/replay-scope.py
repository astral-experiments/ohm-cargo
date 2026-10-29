from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys
d=Path(sys.argv[1]);old=Path(sys.argv[2]);new=Path(sys.argv[3])
def sha(f):
 with f.open('rb') as inpt:return hashlib.file_digest(inpt,'sha256').hexdigest()
def put(f,v):f.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
d.mkdir();src=d/'workspace';src.mkdir()
def file(p,s):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
file(src/'Cargo.toml','[workspace]\nmembers=["library","binary"]\nresolver="3"\n')
for pkg in ['library','binary']:
 base=src/pkg;file(base/'Cargo.toml',f'[package]\nname="{pkg}"\nversion="0.1.0"\nedition="2024"\n')
 file(base/'src/main.rs','fn main() { println!("hello"); }\n')
 if pkg=='library':file(base/'src/lib.rs','pub fn value() -> u8 { 17 }\n')
 file(base/f'tests/{pkg}_integration.rs','#[test] fn work() { assert_eq!(4, 2+2); }\n')
file(src/'Cargo.lock','version=4\n\n[[package]]\nname="binary"\nversion="0.1.0"\n\n[[package]]\nname="library"\nversion="0.1.0"\n')
sdk=d/'sdk'; donor=Path(sys.argv[4]);sdk.mkdir();(sdk/'bin').mkdir()
for p in donor.iterdir():
 if p.name!='bin':(sdk/p.name).symlink_to(p, target_is_directory=p.is_dir())
for p in (donor/'bin').iterdir():
 if p.name!='cargo':(sdk/'bin'/p.name).symlink_to(p)
rustup=d/'rustup/toolchains';rustup.mkdir(parents=True);(rustup/'ohm').symlink_to(sdk,target_is_directory=True)
(d/'home').mkdir();(d/'cargo-home').mkdir();live=sdk/'bin/cargo';tmp=live.with_name('next-cargo')
env={'HOME':str(d/'home'),'PATH':str(Path(shutil.which('rustup')).parent)+':/usr/bin:/bin','LANG':'C','RUSTUP_HOME':str(d/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(d/'cargo-home')}
reports=[]
for side,program in [('old',old),('new',new)]:
 shutil.copyfile(program,tmp);tmp.chmod(0o755);os.replace(tmp,live);assert sha(program)==sha(live)
 who=subprocess.check_output(['cargo','+ohm','-Vv'],env=env,cwd=src)
 (d/(side+'-version')).write_bytes(who)
 if side=='new':assert who==(d/'old-version').read_bytes(),who
 for mode,argv in [('defaults-off',['-Zohm-defaults=no','test','--no-run']),('check',['check','--all-targets']),('native',['test','--no-run'])]:
  state=d/('state-'+mode);resident=env|{'CARGO_TARGET_DIR':str(state/'target'),'CARGO_BUILD_BUILD_DIR':str(state/'shared')}
  for j in [1,2]:
   label=f'{side}-{mode}-{j}';o=d/label;o.mkdir();args=['cargo','+ohm',*argv,'--workspace','--locked','--offline','-j2','--message-format=json']
   with (o/'stdout').open('wb') as out,(o/'stderr').open('wb') as err:
    run=subprocess.run(['strace','-ff','-q','-s','262144','-e','trace=execve','-o',str(o/'exec'),*args],cwd=src,env=resident,stderr=err,stdout=out)
   assert run.returncode==0,(label,(o/'stderr').read_text())
   records=[json.loads(v) for v in (o/'stdout').read_bytes().splitlines()];comp=[];links=[]
   for f in sorted(o.glob('exec.*')):
    for l in f.read_text(errors='replace').splitlines():
     m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',l)
     if not m:continue
     exe=Path(ast.literal_eval(m[1]));a=ast.literal_eval(m[2])
     if exe.name=='rustc' and '--crate-name' in a:
      crate=a[a.index('--crate-name')+1]
      if crate!='___':comp.append({'crate':crate,'link_only':'link-only' in a or '-Zlink-only' in a,'sha':hashlib.sha256(l.encode()).hexdigest()})
     if exe.name in ['ld','ld.bfd','rust-lld','ld.lld'] and '-o' in a:links.append({'exe':sha(exe),'output':Path(a[a.index('-o')+1]).name})
   arts=[]
   for k in records:
    if k.get('reason')=='compiler-artifact':
     arts.append({'name':k['target']['name'],'kind':k['target']['kind'],'test':k['profile']['test'],'fresh':k['fresh'],'sha':sha(Path(k['executable'])) if k.get('executable') else None})
   assert not any(k.get('reason')=='build-script-executed' for k in records)
   report={'label':label,'cargo':sha(live),'rustc':sha(sdk/'bin/rustc'),'argv':args,'compiler':comp,'linker':links,'units':arts,'stdout_sha':sha(o/'stdout'),'stderr_sha':sha(o/'stderr')}
   put(o/'result.json',report);reports.append(report)
   print(label,[u['name'] for u in arts if not u['fresh']],[(x['crate'],x['link_only']) for x in comp],len(links),flush=True)
   if j==2 or side=='new' and mode!='native':assert all(u['fresh'] for u in arts) and not comp and not links,label
   if side=='new' and mode=='native' and j==1:
    assert [u['name'] for u in arts if not u['fresh']]==['library_integration'] and [x['crate'] for x in comp]==['library_integration'] and len(links)==1,(label,report)
put(d/'terminal.json',{'complete':True,'same_version':True,'version_sha':sha(d/'old-version'),'reports':reports})
