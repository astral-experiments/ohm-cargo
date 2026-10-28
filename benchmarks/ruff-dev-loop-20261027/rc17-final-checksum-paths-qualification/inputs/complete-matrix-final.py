from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time
a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('--cargo',choices=['old','fixed','upgrade','downgrade'],required=True);a.add_argument('--rust',choices=['old','fixed'],required=True);o=a.parse_args()
D=Path(__file__).resolve().parent.parent;root=o.root.resolve();root.mkdir();tmpl=D/'input/heldout-fixture';shipped=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027/assets/stock16-sdk').resolve();native=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027/assets/stage2-sdk');old_c=Path(os.environ.get('QUALIFIED_OLD_CARGO',str(shipped/'bin/cargo')));new_c=Path(os.environ['QUALIFIED_CARGO']);release=Path(os.environ.get('QUALIFIED_RELEASE',str(D/'no-release')));logical=root/'active-sdk';logical.mkdir();rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(logical)
old_release=os.environ.get('QUALIFIED_OLD_RELEASE')
if o.rust=='old' and old_release: release=Path(old_release)
physical=shipped if o.rust=='old' and not old_release else native
shutil.copytree(physical/'bin',logical/'bin',symlinks=False);(logical/'lib').mkdir()
for af in (physical/'lib').iterdir():
 (logical/'lib'/af.name).symlink_to(af)
if o.rust=='fixed' or old_release:
 receipt=json.loads((release/'receipt.json').read_text());so=release/'candidate-driver.so';front=release/'candidate-frontend'
 for file,digest in [(so,receipt['candidate_postbolt']),(front,receipt['frontend'])]:
  with file.open('rb') as stream: assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
 dst=logical/'lib'/receipt['driver_name']
 if dst.is_symlink():dst.unlink()
 subprocess.run(['cp','--reflink=auto',so,dst],check=True);(logical/'bin/rustc').unlink();shutil.copy2(front,logical/'bin/rustc')
 assert subprocess.check_output([logical/'bin/rustc','--print=sysroot'],text=True).strip()==str(logical)
 assert receipt['driver_name'].encode() in subprocess.check_output(['readelf','-d',logical/'bin/rustc'])
installed='initial'

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,case,e,ck,trace=None):
 global installed
 if installed!=ck:
  src=old_c if ck=='old' else new_c
  dst=logical/'bin/cargo'
  shutil.copy2(src,dst.with_name('cargo.replacement')); dst.with_name('cargo.replacement').replace(dst);installed=ck
 argv=list(map(str,args))
 if trace is not None:
  argv=['strace','-f','-qq','-s','16000','-e','trace=execve','-o',str(trace),*argv]
 s=subprocess.run(argv,cwd=case,env=e,capture_output=True,timeout=100)
 return s
def compiler(case,e,value,output,ck):
 src=case/'external.rs';src.write_text(f'pub fn value()->u32 {{{value}}}\n')
 v=run(['rustc','+ohm','--crate-name','escape_fixture','--crate-type=rlib','-Copt-level=1','-Cmetadata=keep-identical-tag','-Cdebuginfo=0',src,'-o',output],case,e,ck)
 assert v.returncode==0,v.stderr.decode()[-3000:]
def cargo(case,e,label,ck,real,shadow):
 rec=case/'records'/label;rec.mkdir(parents=True);cmd=['cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json'];r=run(cmd,case/'code',e,ck,rec/'exec')
 (rec/'stdout.jsonl').write_bytes(r.stdout);(rec/'stderr').write_bytes(r.stderr)
 assert r.returncode==0,(cmd,r.stderr.decode()[-3000:]);arts=[a for x in r.stdout.splitlines() if (a:=json.loads(x)).get('reason')=='compiler-artifact'];unit,=[a for a in arts if a['target']['name']=='hold_direct'];pr=subprocess.run([unit['executable']],cwd=case,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);(rec/'native').write_bytes(pr.stdout)
 dirs=[Path(e['CARGO_TARGET_DIR']),Path(e['CARGO_BUILD_BUILD_DIR'])]
 active=[x for base in dirs for x in base.rglob('dep-bin-hold_direct') if b'OBS' in x.read_bytes()]
 assert len(active)==1,[str(x) for x in active];fp,=active; dep,=[x for base in dirs for x in base.rglob('hold_direct*.d') if x.parent.name=='out' and b'ohm-foreign-span-bytes' in x.read_bytes()]
 b=fp.read_bytes();assert b[-41:-37] in (b'OBS1',b'OBS2')
 (rec/'fingerprint').write_bytes(b);(rec/'rustc.d').write_bytes(dep.read_bytes());argvrows=[s for s in (rec/'exec').read_text().splitlines() if 'execve(' in s and ' = 0' in s];physical=[s for s in argvrows if '\"--crate-name\", \"hold_direct\"' in s and '/bin/rustc\"' in s]
 # rustup may exec two processes. Record each line and classify only the actual toolchain path.
 compiler_rows=[s for s in physical if str(logical/'bin/rustc') in s or str((rustup/'toolchains/ohm')/'bin/rustc') in s]
 row={'mode':label,'cargo':ck,'rust':o.rust,'units':len(arts),'all_fresh':all(a['fresh'] for a in arts),'fresh':unit['fresh'],'native':pr.stdout.decode(),'value':int(pr.stdout.decode().split('escape-value=')[-1].strip()),'elf':sha(unit['executable']),'fp':str(fp),'fp_sha':sha(fp),'depfile':str(dep),'dep_sha':sha(dep),'version':b[5],'wire':b[-41:-37].decode(),'complete':b[-33],'header':dep.read_bytes().startswith(b'# ohm-raw-checksum-paths-v2\n'),'stamps':[real.stat().st_ino,real.stat().st_mtime_ns,real.stat().st_size],'real':sha(real),'shadow':sha(shadow) if shadow.exists() else None,'compiler_exec':compiler_rows,'all_rustc_launches':physical}
 (rec/'row.json').write_text(json.dumps(row,indent=2)+'\n');print(case.name,label,ck,o.rust,row['value'],row['fresh'],row['wire'],row['complete'],len(compiler_rows),flush=True);return row
base=dict(os.environ,RUSTUP_HOME=str(rustup),PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'])
for k in ('RUSTFLAGS','RUSTUP_TOOLCHAIN','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST'):base.pop(k,None)
for ck in (['old','fixed'] if o.cargo in ['upgrade','downgrade'] else [o.cargo]):
 for n in ('cargo','rustc'):
  r=run([n,'+ohm','-vV' if n=='rustc' else '-Vv'],root,base,ck);assert r.returncode==0,r.stderr;(root/(n+'-'+ck+'.version')).write_bytes(r.stdout)
cases={}
for mode in (['decoy-removed','decoy-kept','ordinary'] if o.cargo=='upgrade' else ['decoy','no-decoy','ordinary']):
 st=root/mode;st.mkdir();shutil.copytree(tmpl,st/'code');s=st/'code/hold_direct/src/main.rs';s.write_text(s.read_text().replace(');}',');println!("escape-value={}",escape_fixture::value());}'))
 folder='input space' if mode!='ordinary' else 'input';real=st/folder/'libescape_fixture.rlib';real.parent.mkdir();shadow=st/folder.replace(' ','\\ ')/real.name if mode!='ordinary' else st/'absent'
 start={'upgrade':'old','downgrade':'fixed'}.get(o.cargo,o.cargo);e=dict(base,CARGO_HOME=str(st/'cargo-home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_ENCODED_RUSTFLAGS='--extern\x1fescape_fixture='+str(real),CARGO_BUILD_JOBS='4')
 compiler(st,e,17,real,start);shutil.copy2(real,st/'original.rlib');compiler(st,e,29,st/'future.rlib',start)
 if mode.startswith('decoy'):shadow.parent.mkdir();shutil.copy2(st/'future.rlib',shadow)
 v={};v['first']=cargo(st,e,'first',start,real,shadow);v['train']=cargo(st,e,'train',start,real,shadow);v['unchanged']=cargo(st,e,'unchanged',start,real,shadow)
 m=real.stat();real.write_bytes((st/'future.rlib').read_bytes());os.utime(real,ns=(m.st_atime_ns,m.st_mtime_ns))
 v['changed']=cargo(st,e,'changed',start,real,shadow)
 if o.cargo=='upgrade':
  if mode=='decoy-removed':shadow.unlink()
  v['upgrade']=cargo(st,e,'upgrade','fixed',real,shadow);v['upgrade-noop']=cargo(st,e,'upgrade-noop','fixed',real,shadow)
 if o.cargo=='downgrade':
  for label,role in [('return-old','old'),('train-old','old'),('noop-old','old'),('return-new','fixed'),('train-new','fixed'),('noop-new','fixed')]:
   v[label]=cargo(st,e,label,role,real,shadow)
 end='fixed' if o.cargo in ('upgrade','downgrade') else start
 v['empty']=cargo(st,dict(e,CARGO_TARGET_DIR=str(st/'clean-target'),CARGO_BUILD_BUILD_DIR=str(st/'clean-shared')),'empty',end,real,shadow)
 cases[mode]=v
(root/'identity.json').write_text(json.dumps({'old_cargo':sha(old_c),'new_cargo':sha(new_c),'frontend':sha(logical/'bin/rustc'),'driver':sha(logical/'lib'/__import__('re').search(rb'Shared library: \[(librustc_driver[^\]]+)\]',subprocess.check_output(['readelf','-d',logical/'bin/rustc'])).group(1).decode()),'old_release':old_release,'new_release':str(release),'rust':o.rust},indent=2)+'\n')
(root/'result.json').write_text(json.dumps(cases,indent=2)+'\n')
