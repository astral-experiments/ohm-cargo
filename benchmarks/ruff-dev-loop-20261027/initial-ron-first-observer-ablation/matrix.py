"""Test the stock+stock, both mixed compiler/Cargo downgrades and the exact cooperating stage1 pair."""
from collections import Counter
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');sys.path.insert(0,str(P/'runner'));from shared import BUILD,CH,FROZEN,SONAME,TARGET,TRANSFER,WT,dump,env,floors,load,need,sha,skeleton,trusted
from replay_processes import records
Q=P/'first-proof-stage1';srcroot=Q/'fixture-root';root=Q/'matrix-v1';s1='librustc_driver-15d35e5526bb94f8.so';e=env();e.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');e.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');e['CARGO_BUILD_JOBS']='4';e['CARGO_LOG']='cargo::compiler::fingerprint=info'
CS={'A':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','P':'014d6a789ae435ee4e22d7fbd2764aa59880352b613b1a345b95952d30c2d2a9'};RS={'A':'c579c7f84a94e9b3c3d22fb54050425d91e48647ce0e3b7c6d8eaab327572e40','P':'a9f76b764c8c63f4888468423c4e4e421358ca540b3797fa18c8976bfa46ba40'}
def gen(st,t):
 s=st/'src'
 if t=='tiny':
  (s/'src').mkdir(parents=True);(s/'tests').mkdir();(s/'Cargo.toml').write_text('[package]\nname="ohm_ron_convergence"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n');(s/'src/lib.rs').write_text('pub fn text(x:u32)->String{ron::to_string(&x).unwrap()}\n');shutil.copy2(WT/'Cargo.lock',s/'Cargo.lock')
  for n in range(4):(s/'tests'/f'pack_{n}.rs').write_text(f'#[test] fn ordinary_rust_caller() {{assert_eq!(ohm_ron_convergence::text({n}),"{n}");}}\n')
 else:shutil.copytree(Q/'heldout-fixture',s)

def setup(pair,t):
 st=root/(t+'-'+pair);need(not st.exists(),st);st.mkdir(mode=0o700);floors();gen(st,t)
 for n in ('target','build','home'):(st/n).mkdir(mode=0o700)
 for nm in ('config','config.toml'):
  if (CH/nm).is_file():shutil.copy2(CH/nm,st/'home'/nm)
 shutil.copytree(P/'rustup',st/'rustup',symlinks=True);op=skeleton(st)
 for a,b in [(root,root),(st/'src',srcroot),(st/'target',TARGET),(st/'build',BUILD),(st/'home',CH),(st/'rustup',P/'rustup')]:op+=['--bind',str(a),str(b)]
 for a,b in [(CH/'registry',CH/'registry'),(Q/'sysroot',FROZEN),(TRANSFER/'A' if pair[0]=='A' else Q/'candidate-cargo',FROZEN/'bin/cargo'),(Q/('old-driver' if pair[1]=='A' else 'candidate-driver'),FROZEN/'lib'/s1)]:op+=['--ro-bind',str(a),str(b)]
 subprocess.run([*op,'--','taskset','-c','0-7',sys.executable,'-B',__file__,'inside',t,pair],env=e,check=True)

def inside(t,pair):
 st=root/(t+'-'+pair);trusted();need(sha(FROZEN/'bin/cargo')==CS[pair[0]] and sha(FROZEN/'lib'/s1)==RS[pair[1]],'actual runtime');cmd=['cargo','+ohm',*(['test','--no-run'] if t=='tiny' else ['build','-p','hold_direct','-p','hold_indirect','-p','hold_plain']),'--offline','--locked','--message-format=json'];subprocess.run(['cargo','+ohm','metadata','--offline','--format-version','1'],cwd=srcroot,env=e,check=True,stdout=subprocess.DEVNULL);res={}
 phases=['cold','unchanged-1','unchanged-2'] if t=='tiny' else ['cold','unchanged-1','unchanged-2','true-private-edit','fresh-edit','restore','fresh-restored','remove-observer','fresh-plain','reintroduce-observer','fresh-reintroduced']
 for lab in phases:
  if t=='held':
   f=srcroot/'hold_shapes/src/types.rs';m=srcroot/'hold_probe/src/lib.rs';old='/// One private shape\n';new='/// One private shapes\n';expr='format!("{:?}",format!("{marker:?}")).parse().unwrap()';plain='let _=marker; "\\\"plain\\\"".parse().unwrap()'
   for file,lhs,rhs,at in [(f,old,new,'true-private-edit'),(f,new,old,'restore'),(m,expr,plain,'remove-observer'),(m,plain,expr,'reintroduce-observer')]:
    if lab==at:
     data=file.read_text();need(data.count(lhs)==1,(file,lab));file.write_text(data.replace(lhs,rhs))
  d=st/lab;d.mkdir();ret=subprocess.run(['strace','-ff','-qq','-s','131072','-e','trace=execve,execveat','-o',str(d/'exec'),*cmd],cwd=srcroot,env=e,capture_output=True);(d/'stdout').write_bytes(ret.stdout);(d/'stderr').write_bytes(ret.stderr);need(ret.returncode==0,(t,pair,lab,ret.stderr[-600:]));rows=[json.loads(l) for l in ret.stdout.splitlines()];arts=[v for v in rows if v.get('reason')=='compiler-artifact'];jobs=[];link=[];probe=[]
  for pid,x,a in records(d):
   if Path(x).name=='rustc' and '--crate-name' in a and not any(v.startswith('--print=') for v in a):
    cr=a[a.index('--crate-name')+1];mode='rlink' if '-Zlink-only' in a else 'full';jobs.append([cr,mode,'-Zohm-observer-dep-info' in a,'-Zbinary-dep-depinfo' in a,'-Zchecksum-hash-algorithm=blake3' in a])
   if Path(x).name in ('ld','ld.bfd','ld.lld','wild','rust-lld') and '-o' in a:link.append([pid,Path(x).name,Path(a[a.index('-o')+1]).name]);
   if Path(x).name=='rustc' and '-Zohm-observer-dep-info' in a and '--print=sysroot' in a:probe.append(pid)
  outputs={};native={}
  for art in arts:
   if not art.get('executable'):continue
   b=Path(art['executable']);n=art['target']['name'];out=subprocess.run([b,*(['--exact','ordinary_rust_caller'] if t=='tiny' else [])],cwd=srcroot,env=e,capture_output=True);need(out.returncode==0,(n,out.stderr));s=out.stdout.decode().strip();outputs[n]=s if t!='tiny' else ('1 passed' in s if n.startswith('pack_') else '0 tests' in s);native[n]=sha(b)
  fps=[]
  for base in (TARGET,BUILD):
   for x in base.rglob('dep-*'):
    if not x.is_file() or b'ohm-foreign-span-bytes' not in (raw:=x.read_bytes()):continue
    at=raw.rfind(b'OBS1');fps.append({'name':x.name,'complete':None if at<0 else raw[at+8]==1,'signed':at>=0 and len(raw)-at==41,'sha256':sha(x)})
  res[lab]={'jobs':jobs,'links':link,'probes':probe,'fresh':sum(a['fresh'] for a in arts),'units':len(arts),'runtime':outputs,'native':native,'marker_receipts':fps};dump(st/'matrix.json',res);print(t,pair,lab,len(jobs),len(link),[(i['name'],i['complete']) for i in fps],flush=True)
if sys.argv[1]=='inside':inside(*sys.argv[2:]);sys.exit(0)
need(not root.exists() and not srcroot.exists(),'prior matrix');root.mkdir(mode=0o700);srcroot.mkdir(mode=0o700)
for pair in ('PP','PA','AP','AA'):
 for t in ('tiny','held'):setup(pair,t)
