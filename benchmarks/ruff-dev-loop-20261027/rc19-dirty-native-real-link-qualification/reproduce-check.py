from pathlib import Path
import ast,hashlib,json,re,shutil,subprocess,sys
q=Path(__file__).resolve().parent
c=Path(sys.argv[1]);sdk=Path(sys.argv[2])
c.mkdir();src=c/'source'
for path in [src/'src',src/'tests',c/'rustup/toolchains',c/'home',c/'cargo-home']: path.mkdir(parents=True,exist_ok=True)
(c/'rustup/toolchains/ohm').symlink_to(sdk, target_is_directory=True)
(src/'Cargo.toml').write_text('[package]\nname="current_api"\nversion="0.1.0"\nedition="2024"\n')
(src/'Cargo.lock').write_text('version=4\n\n[[package]]\nname="current_api"\nversion="0.1.0"\n')
(src/'tests/reader.rs').write_text('#[test] fn ordinary_call(){ assert_eq!(current_api::value(), 29); }\n')
a=b'pub fn value() -> u8 { 17 }\n';b=b'pub fn value() -> u8 { 29 }\n';broken=b'pub fn value(x: u8) -> u8 { x }\n'
env={'HOME':str(c/'home'),'PATH':str(Path(shutil.which('rustup')).parent)+':/usr/bin:/bin','LANG':'C','RUSTUP_HOME':str(c/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(c/'cargo-home')}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
rows={}
for label,body,empty,expected in [('initial',a,False,0),('initial-unchanged',a,False,0),('private-body',b,False,0),('private-body-unchanged',b,False,0),('public-api',broken,False,101),('empty-public-api',broken,True,101),('restore',b,False,0)]:
 lib=src/'src/lib.rs'
 if not lib.is_file() or lib.read_bytes()!=body: lib.write_bytes(body)
 lane=c/('empty' if empty else 'normal');d=c/label; d.mkdir()
 cmd=['cargo','+ohm','check','--test','reader','--locked','--offline','-j2','--message-format=json']
 runenv=env|{'CARGO_TARGET_DIR':str(lane/'target'),'CARGO_BUILD_BUILD_DIR':str(lane/'shared')}
 tr=['strace','-ff','-q','-s','262144','-e','trace=execve','-o',str(d/'exec')]+cmd
 with (d/'stdout').open('wb') as out,(d/'stderr').open('wb') as err:
  p=subprocess.run(tr,cwd=src,env=runenv,stdout=out,stderr=err)
 native=[];mods=[]
 for t in sorted(d.glob('exec.*')):
  for line in t.read_text(errors='replace').splitlines():
   m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',line)
   if not m:continue
   f=Path(ast.literal_eval(m[1])); args=ast.literal_eval(m[2])
   if f.name=='rustc' and '--crate-name' in args and args[args.index('--crate-name')+1]!='___':
    mods.append([args[args.index('--crate-name')+1],next((x for x in args if x.startswith('--emit=')),None)])
   if f.name in ('ld','ld.bfd','ld.lld','rust-lld') and '-o' in args:native.append(f.name)
 typed=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()]
 codes=[x['message']['code']['code'] for x in typed if x.get('reason')=='compiler-message' and (x['message'].get('code') or {}).get('code')]
 assert p.returncode==expected and not native,(label,p.returncode,expected,native)
 if expected: assert 'E0061' in codes,(label,codes)
 if label.endswith('unchanged'):assert not mods,mods
 rows[label]={'status':p.returncode,'compiler_units':mods,'linkers':native,'diagnostics':codes,'source':digest(lib),'artifact_fresh':[[v['target']['name'],v['fresh']] for v in typed if v.get('reason')=='compiler-artifact'],'stdout':digest(d/'stdout'),'stderr':digest(d/'stderr')}
 print(label,rows[label]['compiler_units'],p.returncode,codes,flush=True)
(c/'terminal.json').write_text(json.dumps({'cargo':digest(sdk/'bin/cargo'),'cmd':cmd,'results':rows},sort_keys=True,indent=2)+'\n')
