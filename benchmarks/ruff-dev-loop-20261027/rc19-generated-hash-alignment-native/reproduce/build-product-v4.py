"""Build both real source images from an identical release profile and exact compiler."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys,tarfile,time,traceback
H=Path.home();D=H/'.cache/ohm-align-script-hash-product-20261028-v1';SDK=H/'.cache/ohm-ron-producer-freshness-20261028/official-sdk';o=SDK.parent/'official-installer-state/rustup';src=D/'canonical-source';out=D/'images-v4';arm_ids={'A':'235f9228651b74c591e6f62cae4c9b761448dd2d','B':'2f6f0d690ac1f787832ad86d2205d2a7429ad171'}
def sha(p):
 with p.open('rb')as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
def verify_tree(p,leaves):
 members={str(x.relative_to(p))for x in p.rglob('*')if x.is_symlink() or x.is_file()};assert members==set(leaves)|{'git-commit-info'},len(members)
 for k,(mode,oid)in leaves.items():
  f=p/k; b=os.fsencode(os.readlink(f))if f.is_symlink() else f.read_bytes();assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==oid,k
  assert f.is_symlink()==(mode=='120000') and (mode=='120000' or bool(f.stat().st_mode&0o111)==(mode=='100755')),k
def main():
 assert os.uname().nodename==os.environ['OHM_BENCH_PRIMARY_HOST'] and shutil.disk_usage(D).free>45*2**30
 stage=os.environ.get('OHM_BUILD_STAGE','ab');assert stage=='ab'
 assert "('B', 'src/bin/cargo/main.rs', 0)" in (D/'build-v2-failure.txt').read_text();out.mkdir();stamp=f"{arm_ids['A']}\n{arm_ids['A'][:9]}\n2026-10-28\n";sources={};keys=[]
 common={}
 for rel in ('bin/cargo','bin/rustc',*map(lambda x:str(x.relative_to(SDK)),(SDK/'lib').glob('librustc_driver-*.so'))):common[rel]=sha(SDK/rel)
 assert common['bin/cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573' and sha(D/'rustc-pgo.profdata')=='481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7';common['profile']=sha(D/'rustc-pgo.profdata');common['compiler_version']=subprocess.check_output([SDK/'bin/rustc','-vV'],text=True)
 for arm,commit in arm_ids.items():
  spec=json.loads((D/(commit[:8]+'-source.json')).read_bytes());assert spec['head']==commit and len(spec['leaves'])>=3108
  f=D/('source-v2-'+arm);assert (f/'git-commit-info').read_text()==stamp;verify_tree(f,spec['leaves']);sources[arm]=f;keys.append(spec)
 assert [k for k in keys[0]['leaves'] if keys[0]['leaves'][k]!=keys[1]['leaves'].get(k)]==['src/compiler/fingerprint/worktree.rs']
 env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTC_','RUSTUP_')) and k not in ('RUSTFLAGS','RUSTDOCFLAGS','RUSTC','RUSTDOC','LD_PRELOAD')}
 env.update(PATH=str(H/'.cargo/bin')+':'+env['PATH'],RUSTUP_HOME=str(o),CARGO_HOME=str(D/'build-home'),CARGO_TARGET_DIR=str(D/'cargo-target'),CARGO_BUILD_BUILD_DIR=str(D/'cargo-shared'),RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',CARGO_PROFILE_RELEASE_INCREMENTAL='false',CFG_RELEASE_CHANNEL='dev',RUSTFLAGS=f'-Cprofile-use={D}/rustc-pgo.profdata -Cllvm-args=-pgo-warn-missing-function=false')
 versions={}
 for arm,commit in arm_ids.items():
  f=sources[arm];od=out/arm;od.mkdir();[os.utime(f/x,None)for x in ('build.rs','src/lib.rs','src/bin/cargo/main.rs','src/compiler/fingerprint/worktree.rs')]
  backup=od/'prior-cargo-units';backup.mkdir(); prior_dir=D/'images-v3/A' if arm=='A'else out/'A';unit_dirs={}
  for l in (prior_dir/'compiler.exec').read_text().splitlines():
   if '"--crate-name", "cargo"' in l and 'profile-use=' in l and ('"src/lib.rs"' in l or '"src/bin/cargo/main.rs"' in l) and '= -1 ' not in l:
    argv=ast.literal_eval('['+l.split(', [',1)[1].split('], ',1)[0]+']'); unit=Path(argv[argv.index('--out-dir')+1]).parent;assert unit.parent.name=='cargo' and unit.is_relative_to(D/'cargo-target/release/build/workspaces') and (unit/'fingerprint').is_dir();unit_dirs[unit.name]=unit
  assert len(unit_dirs)==2
  for key,unit in unit_dirs.items():unit.rename(backup/key)
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(D),str(D),'--ro-bind',str(f),str(src),'--chdir',str(src),'--','taskset','-c','0-15',str(H/'.cargo/bin/cargo'),'+ohm','build','--release','--locked','--offline','-p','cargo','--bin','cargo','--features','ohm-defaults','-j12']
  with (od/'build.log').open('xb')as log:
   rc=subprocess.run(['strace','-f','-qq','-s','65535','-e','trace=execve,execveat','-o',od/'compiler.exec',*cmd],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
  assert rc==0,(arm,(od/'build.log').read_text()[-2500:]);b=od/'cargo';shutil.copy2(D/'cargo-target/release/cargo',b);v=subprocess.check_output([b,'-Vv'],text=True);assert arm_ids['A'] in v,v
  versions[arm]=v;rows={};trace=od/'compiler.exec'
  for k in ('src/lib.rs','src/bin/cargo/main.rs'):
   hit=[l for l in trace.read_text().splitlines()if '"--crate-name", "cargo"' in l and '"'+k+'"'in l and 'profile-use='in l and '"link-only"' not in l and '= -1 'not in l];assert len(hit)==1,(arm,k,len(hit));l=hit[0];argv=ast.literal_eval('['+l.split(', [',1)[1].split('], ',1)[0]+']');deps={}
   for i,x in enumerate(argv[:-1]):
    if x=='--extern' and '=' in argv[i+1]:
     name,loc=argv[i+1].split('=',1);deps[name]=[loc,sha(Path(loc))]
   assert len(deps)>70;rows[k]={'argv':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'externs':deps}
  result={'arm':arm,'head':commit,'tree':keys['AB'.index(arm)]['tree'],'cargo':sha(b),'stamp':sha(f/'git-commit-info'),'builder':common,'invocations':rows,'trace':sha(trace),'version':v,'source_count':len(spec['leaves'])};save(od/'receipt.json',result)
  if arm=='B':
   a=json.loads((out/'A/receipt.json').read_bytes());assert a['version']==v and a['builder']==common and a['stamp']==result['stamp'];assert a['cargo']!=result['cargo']
   for key,x in rows.items():
    old=a['invocations'][key];assert old['argv']==x['argv']and set(old['externs'])==set(x['externs']),key
    for name,j in x['externs'].items():
     if key=='src/bin/cargo/main.rs'and name=='cargo':continue
     assert old['externs'][name]==j,(key,name)
  verify_tree(f,keys['AB'.index(arm)]['leaves']);print(arm,commit,result['cargo'],flush=True)
 save(D/'terminal.json',{'qualified':True,'arms':{a:{'image':sha(out/a/'cargo'),'receipt':sha(out/a/'receipt.json')}for a in arm_ids},'builder':common})
try:main()
except BaseException:(D/'build-v4-failure.txt').write_text(traceback.format_exc());raise
