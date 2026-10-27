from pathlib import Path
import ast,hashlib,json,os,re,shutil,signal,subprocess as sp,sys,time
d=Path('/mnt/devbox-scratch/dev-user/ohm-mixed-interface-20261027');home=Path('/home/dev-user/.cache/ohm-mixed-release-pilot-20261027')
src=Path('/home/dev-user/code/oss/ruff-ohm-mixed-interface-20261027');tool=d/'sysroot';son='librustc_driver-774a793a844d5500.so'
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def space():assert min(shutil.disk_usage(x).free for x in [d,home])>20*2**30
def git(*args):return sp.check_output(['git','--no-optional-locks','-C',src,*args])
pin='93526150df078af7dd8fc4226cdcc469539d2001';commit='3ea20f6161cbf59cb56595dfb634ec24bfa82f0b';assert git('rev-parse','HEAD').decode().strip()==pin and not git('status','--porcelain','--untracked-files=no')
patch=json.loads((d/'parser-patch.json').read_bytes());assert patch['commit']==commit and sha(d/'parser.patch')==patch['sha256']=='08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff'
home.mkdir(exist_ok=True);space()
release=d/'subjects-stock/stage2-sysroot'
cargo_image=home/'bounded-cargo'
driver=Path('/home/dev-user/.cache/ohm-guarded-mixed-release-20261027/driver-7c31057e86f800e313b7d32080c7a5abaa7b92fef92254ac21b2e43febf16384')
assert sha(cargo_image)=='7d8a2d6715e0275308194508c70a4d49cb4c281d462c6d14b222ff4f5ecc1572'
assert sha(driver)=='7c31057e86f800e313b7d32080c7a5abaa7b92fef92254ac21b2e43febf16384'
assert sha(release/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
assert sha(release/'lib/libLLVM.so.23.1-rust-1.99.0-beta')=='43bac9749e539cd5988a4d5452b64582cf07ac9e7c059fde29c7bee76e106c51'
lib=release/'lib/rustlib/x86_64-unknown-linux-gnu'
assert sha(lib/'bin/wild-ld/ld.bfd')=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert sha(lib/'lib/libstd-150b24506f9fb8c9.rlib')=='bb1da52e02b3bf34996fb9bc50c6d80b9244a23b8fe6d3b47f7eabd5953d4191'
def init():
 arm=home/'pair'
 arm.mkdir();(arm/'target').mkdir();(arm/'shared').mkdir()
 sp.run(['cp','-a','--reflink=auto',d/'registry-home',arm/'registry-home'],check=True)
 assert not any((arm/'target').iterdir()) and not any((arm/'shared').iterdir())
 write(home/'empty-prime.json',{'target_empty':True,'shared_empty': True,'cargo':sha(cargo_image),'compiler':sha(driver),'frontend':sha(release/'bin/rustc'),'wild':sha(lib/'bin/wild-ld/ld.bfd'),'git':pin,'patch':patch['sha256']})
def recipes(arm):
 out={}
 for f in (arm/'target').rglob('*.rlink'):
  if f.stem in ['ruff_wasm','ty_wasm']:
   out[str(d/'target'/f.relative_to(arm/'target'))]=(sha(f),f.stat().st_mtime_ns)
 return out
def one(name,mode,label):
 arm=home/name;out=home/'evidence'/name/label
 recover=(name,label)==('pair','prime') and (out/'stdout').is_file() and not (out/'result.json').is_file()
 if (out/'result.json').is_file():return json.loads((out/'result.json').read_bytes())
 out.mkdir(parents=True,exist_ok=recover);space()
 so=driver;car=cargo_image;assert name in ['pair','forced']
 args=['taskset','-c','0-15','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(out),str(out),'--ro-bind',str(release),str(tool),'--ro-bind',str(so),str(tool/'lib'/son),'--ro-bind',str(car),str(tool/'bin/cargo')]
 for n in ['target','shared','registry-home']:args+=['--bind',str(arm/n),str(d/n)]
 state=arm/'source';tag=arm/'source-state'
 if not tag.exists() or tag.read_text()!=mode:
  for rel in patch['paths']:
   dest=state/rel
   if (d/mode/rel).is_file():
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(d/mode/rel,dest)
    if rel.endswith('.rs'):os.utime(dest,None)
   else:
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():dest.unlink()
  tag.write_text(mode)
 for rel in patch['paths']:
  f=state/rel
  if f.is_file():args+=['--ro-bind',str(f),str(src/rel)]
  else:
   par=Path(rel).parent; new=out/'overlay'/par
   if not new.exists():shutil.copytree(src/par,new)
   if (new/Path(rel).name).exists():(new/Path(rel).name).unlink()
   args+=['--ro-bind',str(new),str(src/par)]
 env=dict(os.environ,RUSTUP_HOME=str(d/'rustup'),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(d/'registry-home'),CARGO_TARGET_DIR=str(d/'target'),CARGO_BUILD_BUILD_DIR=str(d/'shared'),CARGO_BUILD_JOBS='8',RUSTC=str(tool/'bin/rustc'),LD_LIBRARY_PATH=str(tool/'lib'),GIT_OPTIONAL_LOCKS='0',CARGO_TERM_COLOR='never',CARGO_NET_OFFLINE='true')
 for k in ['CARGO_ENCODED_RUSTFLAGS','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER']:env.pop(k,None)
 args+=['--chdir',str(src),'--','/usr/bin/strace','-qq','-ff','-e','trace=execve','-s','65536','-o',str(out/'exec'),'/home/dev-user/.cargo/bin/cargo','+ohm','build','--locked','--offline','-p','ruff_wasm','-p','ty_wasm','--message-format=json']
 if recover:
  assert 'Finished `dev`' in (out/'stderr').read_text()
  before=json.loads((out/'inputs.json').read_bytes())['before']
 else:
  before=recipes(arm);write(out/'inputs.json',{'rustc':sha(so),'cargo':sha(car),'source':mode,'before':before,'args':args})
  with (out/'stdout').open('wb') as o,(out/'stderr').open('wb') as e:
   po=sp.Popen(args,env=env,stdout=o,stderr=e,start_new_session=True)
   while po.poll() is None:
    try:space()
    except:os.killpg(po.pid,signal.SIGTERM);raise
    time.sleep(.4)
   assert po.returncode==0,(name,label,(out/'stderr').read_text()[-2000:])
 after=recipes(arm);procs=[];native={k:[] for k in ['cc','collect2','ld.bfd']};probes=[];arts={}
 for f in sorted(out.glob('exec.*')):
  pid=int(f.name.split('.')[-1])
  for line in f.read_text(errors='replace').splitlines():
   m=re.match(r'execve\("(.*?)", (\[.*?\]), .*\) += 0$',line)
   if not m:continue
   path,raw=m.groups();a=ast.literal_eval(raw)
   if Path(path).name in native:native[Path(path).name].append(pid)
   if Path(path).name!='rustc':continue
   if '--crate-name' not in a or '--print=file-names' in a:probes.append(pid);continue
   crate=a[a.index('--crate-name')+1];assert crate!='___'
   recipe=next((x.split('=',1)[1] for x in a if x.startswith('ohm-checked-mixed-rlink=')),None);checked=recipe is not None
   phase='HIR-and-native-link' if checked and recipe in before and before[recipe]==after[recipe] else 'checked-full-fallback' if checked else 'plain-link-only' if any(x in ('-Zlink-only','link-only') for x in a) else 'full'
   procs.append([pid,crate,phase]);write(out/('rustc-'+str(pid)+'.json'),a)
 for line in (out/'stdout').read_bytes().splitlines():
  v=json.loads(line)
  if v.get('reason')!='compiler-artifact':continue
  k=v['target']['name']
  outputs={}
  if k in ['ruff_python_parser','ruff_wasm','ty_wasm']:
   for p in map(Path,v['filenames']):
    f=arm/'target'/p.relative_to(d/'target');outputs[f.suffix]=sha(f)
    if f.suffix=='.rlib':outputs['embedded']=hashlib.sha256(sp.check_output(['ar','p',f,'lib.rmeta'])).hexdigest()
    if f.suffix=='.so':outputs['symbols']=sp.check_output(['nm','-D','--defined-only',f],text=True).splitlines()
  arts.setdefault(k,[]).append([v['fresh'],outputs])
 res={'source':mode,'cargo':sha(car),'driver':sha(so),'before':before,'after':after,'procs':procs,'discovery':probes,'native':native,'units':sum(map(len,arts.values())),'dirty':[k for k,vs in arts.items() for fresh,_ in vs if not fresh],'artifacts':{k:v for k,v in arts.items() if any(out for _,out in v)}}
 write(out/'result.json',res);print(name,label,res['units'],(procs if len(procs)<15 else len(procs)),{k:len(v) for k,v in native.items()},flush=True)
 if label.endswith('-fresh'):assert not procs and not res['dirty']
 return res
if sys.argv[1]=='init':init()
elif sys.argv[1]=='run':
 for name in ['pair']:
  for mode,label in [('original','prime'),('original','prime-fresh'),('edited','edit1'),('edited','edit1-fresh'),('original','restore'),('original','restore-fresh'),('edited','edit2'),('edited','edit2-fresh')]:one(name,mode,label)
else:one(*sys.argv[1:])
