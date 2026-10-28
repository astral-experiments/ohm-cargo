"""Independent renderer-only matched compiler holdout for the existing incremental allocation fix."""
from pathlib import Path
import ast,fcntl,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *;from run_data import guard_source
x=h/'.cache/ohm-233-position-qualified-20261027';host=p/'frozen-toolchain';origdrv,=(host/'lib').glob('librustc_driver-*.so')
cfg={'release':'dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f','macro':'36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05','alloc':'4a993e1f78e3ec0122771380eadbf58ed5d467c058d314381e523f1bbe78d955'}
imgs={'release':x/'drivers'/('driver-'+cfg['release']),'macro':p/'parse-source-replay-v3/candidate-driver.so','alloc':q/'alloc4-driver.so'}
for a,v in imgs.items():assert sha(v)==cfg[a]
assert sha(host/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'and sha(sdk/'bin/cargo')==plan['release']['cargo']
root=q/'existing-alloc-replay-v2';root.mkdir();st=Path('/dev/shm/ohm-annotate-alloc-replay-h3-v2');st.mkdir()
(subsrc:=st/'edited-files').mkdir()
for n in plan['files']:
 d=subsrc/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(w/n,d)
patch=(q/'ops/edit.patch').read_bytes();z=subprocess.run(['git','apply','--unsafe-paths','--no-index','--reverse','-'],cwd=subsrc,input=patch,capture_output=True);assert z.returncode==0,z.stderr
assert all(sha(subsrc/n)==v for n,v in plan['sha_edit'].items())
assert all(sha(w/n)==v for n,v in plan['sha_original'].items())
assert shutil.disk_usage(st).free-(800<<20)>25*(1<<30)
registry=st/'registry-home';shutil.copytree(seed/'registry-home',registry,symlinks=True);cmd=['cargo','+ohm','build','--locked','--offline','--message-format=json','-p','ruff_annotate_snippets','--lib'];arts={}
spec=[('original','chain',False),('warm-edited','chain',True),('warm-restored','chain',False),('empty-edited','empty-edited',True),('empty-original','empty-original',False)]
put(root/'design.json',{'experiment':'Historical renderer source on independently trained released-compiler-equivalent stages, no wall-time comparison. New target and shared dir per arm/empty. Compare features, normal Cargo unit outputs, actual allocation vector and hash, private source, native behavior in each history.','arms':cfg,'frontend':sha(host/'bin/rustc'),'cargo':sha(sdk/'bin/cargo'),'spec':spec,'command':cmd,'toolchain_std':{str(z.name):sha(z)for z in (host/'lib/rustlib/x86_64-unknown-linux-gnu/lib').glob('libstd-*.rlib')},'sources':plan['sha_original'],'reversed':plan['sha_edit']})
def val(a,ns,env2,output):
 z=subprocess.run([*ns,*map(str,a)],env=env2,cwd=w,capture_output=True,timeout=150);(output.parent/(output.name+'.out')).write_bytes(z.stdout);(output.parent/(output.name+'.err')).write_bytes(z.stderr);return z
def read_root(hd):
 ma=re.search(rb'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',hd,re.M);assert ma;return [v.decode()for v in ma.groups()]
with(p/'native-measure.lock').open('rb')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);guard_source(False);prev=False;env2=dict(env,RUSTUP_HOME=str(p/'rustup'))
 for arm in ('release','macro','alloc'):
  ad=root/arm;ad.mkdir()
  for tag,ca,rv in spec:
   guard()
   assert all(sha((subsrc if rv else w)/n)==v for n,v in plan['sha_edit'if rv else'sha_original'].items());d=ad/tag;d.mkdir();sd=st/arm/ca
   for n in ('target','shared'):(sd/n).mkdir(parents=True,exist_ok=True)
   ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',str(q),str(q),'--bind',str(sd/'target'),str(t),'--bind',str(sd/'shared'),str(s),'--bind',str(registry),str(r),'--bind',str(st),str(st),*([v for n in plan['files'] for v in ('--ro-bind',str(subsrc/n),str(w/n))] if rv else []),'--ro-bind',str(imgs[arm]),str(origdrv),'--ro-bind',str(sdk/'bin/cargo'),str(host/'bin/cargo'),'--tmpfs','/tmp','--chdir',str(w),'--']
   (d/'trace').mkdir()
   z=val(['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/run',*cmd],ns,env2,d/'cargo')
   assert z.returncode==0,(arm,tag,z.stderr[-600:])
   js=[json.loads(y)for y in z.stdout.splitlines()];assert js[-1]=={'reason':'build-finished','success':True}; units=[x for x in js if x['reason']=='compiler-artifact'];xone,=[m for m in units if m['target']['name']=='annotate_snippets'and m['package_id'].startswith('path+')];assert not xone['fresh']
   lib,=[Path(y)for y in xone['filenames'] if y.endswith('.rlib')];md=lib.with_suffix('.rmeta');realmd=sd/'target'/md.relative_to(t);reallib=sd/'target'/lib.relative_to(t)
   shutil.copyfile(realmd,d/'producer.rmeta');shutil.copyfile(reallib,d/'producer.rlib')
   aa=next(f.read_bytes()for f in(d/'trace').glob('run.*')if b'"--crate-name", "annotate_snippets"'in f.read_bytes()and b'"--out-dir"'in f.read_bytes());line,=[l for l in aa.splitlines()if b'"--crate-name", "annotate_snippets"'in l and b'"--out-dir"'in l];args=ast.literal_eval(re.search(rb'execve\("(?:[^"\\]|\\.)*",\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)[1].decode());assert b'+++ exited with 0 +++'in aa
   paths={k:Path(v)for i,z in enumerate(args[:-1])if z=='--extern'for k,v in[args[i+1].split('=',1)]};val_ref=val(['rustc','+ohm','-Zls=root',md],ns,env2,d/'header');assert val_ref.returncode==0;pr,si,pu=read_root(val_ref.stdout)
   ex={n:sha(sd/'target'/f.relative_to(t))for n,f in paths.items()};dirs=sorted({str(Path(y).parent)for a in units for y in a['filenames']});out=st/(arm+'-'+tag+'-reader')
   # This executable is outside the timed build process and binds the current actual producer.
   rc=val(['rustc','+ohm','--edition=2024',q/'ops/reader.rs','--extern','annotate_snippets='+str(lib),*[v for y in dirs for v in('-L','dependency='+y)],'-o',out],ns,env2,d/'compile-reader');assert rc.returncode==0,rc.stderr[-600:]
   rr=val([out],ns,env2,d/'read');assert (rr.returncode==101 and b'index out of bounds'in rr.stderr)if rv else(rr.returncode==0 and b'fixed line 13'in rr.stdout)
   row={'arm':arm,'role':tag,'variant':'edited'if rv else'original','actual_args':args,'physical_trace_sha':H(aa),'source':plan['sha_edit'if rv else'sha_original'],'externs':ex,'header':[pr,si,pu],'units':len(units),'rmeta':sha(realmd),'rlib':sha(reallib),'reader':[rr.returncode,H(rr.stdout),H(rr.stderr)],'fresh':sum(x['fresh']for x in units)}
   put(d/'result.json',row);print(arm,tag,row['header'],row['rmeta'],rr.returncode,flush=True)
 put(root/'complete.json',{'rows':15,'images':cfg,'status':0,'source':plan['pin']})
