"""Trace real Cargo mode transitions. All native and oracle observations are unscored."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,time
h=Path.home();p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');q=p/'formatter-transition-1fcdb82-v1';ram=Path('/dev/shm/ohm-formatter-transition-1fcdb82-v1');usr=Path('/run/user/1000/ohm-formatter-transition-1fcdb82-v1');w=Path.home()/'code/oss/ruff-ohm-whole-native-20261027'
plan=json.loads((q/'plan.json').read_bytes());binding=json.loads((q/'binding.json').read_bytes());src=Path(plan['rust_source']);sdk=Path(binding['sdk']);up=sdk.parent/'rustup';l=q/'target';s=q/'shared';g=q/'registry-home';o=q/'receipts';hist={}
floor={p:25*2**30,h:25*2**30,ram:25*2**30,usr:750*2**20};remaining={}
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();H=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(p.read_bytes())
def put(f,x):
 f.parent.mkdir(parents=True,exist_ok=True);t=f.with_suffix(f.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');os.replace(t,f)
def guard():
 for f,lo in floor.items():
  left=shutil.disk_usage(f).free;remaining[str(f)]=min(left,remaining.get(str(f),left));assert left>lo,(f,lo,left)
def paths(st,f):
 py=Path(f)
 for logical,name in [(l,'target'),(s,'shared'),(g,'registry-home')]:
  if py.is_relative_to(logical):return st/name/py.relative_to(logical)
 return py
def catalog(st):
 key=o/(st.name+'-catalog.json')
 return read(key)if key.exists()else[]
def before(st,fs):
 seen={}
 def info(f):
  py=paths(st,f)
  if not py.is_file():return None
  z=py.stat();key=(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)
  if key not in seen:seen[key]=sha(py)
  return [z.st_size,z.st_mtime_ns,seen[key]]
 return {f:info(f)for f in sorted(set(fs))}
def ns(st,view,d):
 return ['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(d),str(d),*[z for ref,phy in [(l,'target'),(s,'shared'),(g,'registry-home')]for z in ['--bind',str(st/phy),str(ref)]],'--ro-bind',str(q/view/src),str(w/src),'--chdir',str(w),'--']
env=dict(HOME=str(h),PATH=str(h/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(up),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(g),CARGO_TARGET_DIR=str(l),CARGO_BUILD_BUILD_DIR=str(s),CARGO_BUILD_JOBS='6',CARGO_NET_OFFLINE='true',LC_ALL='C.UTF-8',LANG='C.UTF-8',GIT_OPTIONAL_LOCKS='0',CARGO_TERM_COLOR='never')
def run(argv,so,se,expect=None):
 guard()
 with so.open('xb')as out,se.open('xb')as err:
  child=subprocess.Popen(list(map(str,argv)),env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
  try:
   while True:
    try:r=child.wait(timeout=1);break
    except subprocess.TimeoutExpired:guard()
  except BaseException:os.killpg(child.pid,signal.SIGTERM);child.wait();raise
 if expect is not None:assert r in expect,(r,argv[-5:],se.read_bytes()[-900:])
 return r
def stable():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()==plan['source']and not subprocess.check_output(['git','status','--porcelain','-z'],cwd=w)
def state(scope,flow):
 return (usr if flow=='B-T-C-B'else ram)/(scope+'-'+flow)
def init(st):
 st.mkdir(mode=0o700);(st/'target').mkdir();(st/'shared').mkdir()
 source=sdk.parent/'graph-registry';assert source.is_dir()
 run(['cp','-a','--reflink=auto','--',source,st/'registry-home'],o/(st.name+'-registry.stdout'),o/(st.name+'-registry.stderr'),{0})
def ords(flow):
 return plan['workflows']['C-B-T-B'if flow=='gold'else flow]
def jobs(d,st,scope,arts,view,phase):
 calls=[];host_images={};products={f:r for r in arts for f in r['filenames']+([r['executable']]if r['executable']else[])}
 for fil in sorted((d/'trace').glob('exec.*')):
  data=fil.read_bytes();end=re.findall(rb'\+\+\+ exited with (\d+) \+\+\+',data);end=int(end[-1])if end else None; pending=None
  for line in data.splitlines():
   if line.startswith(b'execve(')and line.endswith(b'<unfinished ...>'):assert pending is None;pending=line[:-len(b'<unfinished ...>')];continue
   if line.startswith(b'<... execve resumed>'):assert pending;line=pending+line[len(b'<... execve resumed>'):];pending=None
   if not line.startswith(b'execve(')or not re.search(rb'\)\s+= 0$',line):continue
   ma=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert ma
   image=ast.literal_eval(ma[1].decode());a=ast.literal_eval(ma[2].decode());nm=Path(image).name;kind=None;name=None;unit=None;outputs=[];exs=[]
   if nm=='rustc' and '--crate-name'in a and '--out-dir'in a and '--print=file-names'not in a:
    name=a[a.index('--crate-name')+1]
    if name in ('___','__'):continue
    kind='partial'if any(v in ('-Zlink-only','-Zlink-only=yes')for v in a)or any(v=='-Z'and w.split('=')[0]=='link-only'for v,w in zip(a,a[1:]))else'full'
    unit=Path(a[a.index('--out-dir')+1]).parent.name
    for i,k in enumerate(a[:-1]):
     if k=='--extern'and '='in a[i+1]:
      en,ef=a[i+1].split('=',1);exs.append([en,ef])
    outputs=[f for f,r in products.items()if r['target']['name']==name and (unit in Path(f).name or (r['target']['kind']==['bin']and a[a.index('--crate-type')+1]=='bin'if '--crate-type'in a else False))]
    if not outputs:
     outputs=[f for f,r in products.items()if r['target']['name']==name and unit in Path(f).parts]
   elif nm=='ld.bfd'and 'wild-ld'in Path(image).parts:
    kind='wild';name=a[a.index('-o')+1];od=Path(name);unit=next((part for part in reversed(od.parts)if re.fullmatch('[0-9a-f]{16}',part)),None)
    outputs=[f for f,r in products.items()if f==name or (unit and (unit in Path(f).name or unit in Path(f).parts))]
   elif nm.startswith(('build-script-build','build_script_build'))and('/run/'in image or'/build/'in image):kind='script'
   if not kind:continue
   assert end==0,(nm,name,end);dx={'kind':kind,'name':name,'unit':unit,'argv_sha256':H(ma[2]),'argv':a,'trace_sha256':H(data),'pid':fil.name,'exit':end,'outputs':sorted(set(outputs))}
   if kind in ('partial','full'):
    # Cold registry closure wasn't the prospective discriminator. Preserve all argv and hash direct actual files for every library of interest, and for every historical transition.
    if phase not in ('cold','train1','train2')or name in ('ruff','ruff_formatter'):
     rec=before(st,[f for _,f in exs]);dx['externs_post_call']=[[n,Path(f).name,rec[f]]for n,f in exs]
   if kind=='wild':
    pos=[v for v in a if not v.startswith('-')and v.endswith(('.rlib','.a','.o','.so'))];ld=before(st,pos)
    dx['direct_persisted_native_inputs']=[[Path(v).name,ld[v]]for v in pos];dx['noncertified_inputs']='Implicit resolutions, absent higher-priority native search candidates and any missing temporary inputs are not proved by this trace.'
   calls.append(dx)
  assert pending is None
 return calls
def compare_oracle(d,st,view,mode,arts,scope):
 en=ns(st,view,d);lib=[v for v in arts if v['target']['name']=='ruff_formatter' and v['target']['kind']==['lib'] and not v['profile']['test']];assert len(lib)==1,[(v['target']['name'],v['target']['kind'],v['profile'])for v in arts if v['target']['name']=='ruff_formatter']
 libs=lib[0]['filenames'];normal=next((e for e in libs if e.endswith('.rmeta')),next((e for e in libs if e.endswith('.rlib')),None));assert normal
 dirs=sorted({str(Path(f).parent)for v in arts for f in v['filenames']});rust=['rustc','+ohm','--edition=2024','--error-format=json','--extern','ruff_formatter='+normal,*[a for v in dirs for a in ['-L','dependency='+v]]]
 c=run(en+[*rust,'--emit=metadata','-o',d/'consumer.rmeta',q/'readers/constant.rs'],d/'constant.stdout',d/'constant.stderr',{0,1})
 ds=[json.loads(z)for z in(d/'constant.stderr').read_bytes().splitlines()if z.startswith(b'{')]
 codes=[v['code']['code'] for v in ds if v.get('code')and v['level']=='error']
 assert (c==0 and not codes)if view=='reversed' else(c==1 and codes==['E0425']),(view,c,codes,[v.get('message')for v in ds])
 res={'constant':{'status':c,'codes':codes,'diagnostics_sha256':sha(d/'constant.stderr'),'metadata_sha256':sha(paths(st,normal))}}
 if mode!='check':
  rlib,=[v for v in libs if v.endswith('.rlib')]
  rust[rust.index('--extern')+1]='ruff_formatter='+rlib
  run(en+[*rust,'-o',d/'newlines',q/'readers/newlines.rs'],d/'newlines-compile.stdout',d/'newlines-compile.stderr',{0})
  out=subprocess.check_output(en+[str(d/'newlines')],env=env);assert out==b'a\\nb\n'*4,out
  res['newlines']={'stdout_hex':out.hex(),'status':0,'consumer_sha256':sha(d/'newlines'),'source_rlib_sha':sha(paths(st,rlib))}
 if mode=='test':
  harness,=[v for v in arts if v['target']['name']=='ruff_formatter'and v['profile']['test']and v['target']['kind']==['lib'] and v['executable'] is not None]
  test=harness['executable'];target='format_element::tests::test_normalize_newlines'
  run(en+[test,'--list','--format','terse'],d/'harness-list.stdout',d/'harness-list.stderr',{0});lines=(d/'harness-list.stdout').read_bytes().splitlines();assert(target+': test').encode()in lines
  run(en+[test,'--exact',target],d/'harness-one.stdout',d/'harness-one.stderr',{0});out=(d/'harness-one.stdout').read_bytes();assert b'1 passed; 0 failed;'in out
  res['harness']={'name':Path(test).name,'list':sha(d/'harness-list.stdout'),'entries':len(lines),'outside_cargo_exact':target,'passed':True,'harness_sha':sha(paths(st,test))}
 if scope=='big' and mode!='check':
  exes=[v['executable']for v in arts if v['target']['name']=='ruff'and v['target']['kind']==['bin']and v['executable']and not v['profile']['test']]
  if exes:
   cli,=set(exes);args=[cli,'format','--isolated','--no-cache','--config','format.line-ending="lf"','--stdin-filename','example.py','-'];z=subprocess.run(en+args,env=env,input=b'x=1\r\n',capture_output=True)
   assert z.returncode==0 and z.stdout==b'x = 1\n',(z.returncode,z.stderr[-300:],z.stdout);res['ruff_format']={'sha':sha(paths(st,cli)),'status':0,'input_hex':'783d310d0a','output_hex':z.stdout.hex()}
 return res
def step(st,scope,view,group,i,mode):
 d=o/st.name/f'{group}-{i}-{mode}';d.mkdir(parents=True);(d/'trace').mkdir()
 en=ns(st,view,d);known=catalog(st);pre=before(st,known)
 assert subprocess.check_output(en+['sha256sum',str(w/src)],env=env,text=True).split()[0]==binding['sha_'+view]
 cmd=['cargo','+ohm',mode]+(['--no-run']if mode=='test'else[])+['--locked','--offline','--message-format=json','-p','ruff_formatter']+(['-p','ruff']if scope=='big'else[])
 run(en+['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/exec',*cmd],d/'stdout',d/'stderr',{0})
 rows=[json.loads(v)for v in(d/'stdout').read_bytes().splitlines()];assert rows[-1]=={'reason':'build-finished','success':True};arts=[v for v in rows if v['reason']=='compiler-artifact']
 files=sorted({f for v in arts if v['package_id'].startswith('path+file://'+str(w)+'/') for f in v['filenames']+([v['executable']]if v['executable']else[])})
 after=before(st,files);assert all(e is not None for e in after.values())
 native=jobs(d,st,scope,arts,view,group);oracle=compare_oracle(d,st,view,mode,arts,scope)
 ro=[{k:v[k]for k in ('package_id','target','profile','features','filenames','executable','fresh')}for v in arts];diag=[v for v in rows if v['reason']=='compiler-message']
 put(d/'all-native.json',native);put(d/'products.json',{'before':{k:pre.get(k) for k in files},'after':after});put(d/'units.json',ro);put(d/'diagnostics.json',diag);put(o/(st.name+'-catalog.json'),sorted(set(known)|set(files)))
 physical=dict(collections.Counter(k['kind']for k in native));data={'state':st.name,'group':group,'view':view,'source':binding['sha_'+view],'slot':i,'command':cmd,'mode':mode,'units':len(arts),'fresh':sum(v['fresh']for v in arts),'physical':physical,'oracle':oracle,'kept_raw':{v:sha(d/v)for v in ('stdout','stderr','all-native.json','products.json','units.json','diagnostics.json')},'storage':remaining}
 put(d/'end.json',data);print(st.name,group,i,mode,data['units'],data['fresh'],physical,oracle['constant']['codes'],flush=True);return data
def cycle(st,scope,flow,view,group):return [step(st,scope,view,group,i,mode)for i,mode in enumerate(ords(flow),1)]
def train(st,scope,flow,view):
 rows=cycle(st,scope,flow,view,'cold')
 for tag in ('train1','train2','train3'):
  rows=cycle(st,scope,flow,view,tag)
  if all(u['fresh']==u['units']and not u['physical']for u in rows):return tag
 raise AssertionError((st,'native modes never jointly settled',[(u['mode'],u['physical'])for u in rows]))
def main():
 scope,flow=sys.argv[1:];assert scope in ('small','big')and flow in ('C-B-T-B','B-T-C-B','gold');st=state(scope,flow);guard();stable()
 with (p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);(o/st.name).mkdir(mode=0o700);init(st);stablephase=train(st,scope,flow,'reversed'if flow=='gold'else'original')
  if flow!='gold':
   for tag,view in [('first-edit','reversed'),('repeat-edit','reversed'),('restore','original'),('repeat-restore','original')]:
    cycle(st,scope,flow,view,tag)
  stable();put(o/st.name/'complete.json',{'flow':flow,'scope':scope,'settled':stablephase,'source':plan['source'],'remaining':remaining})
if __name__=='__main__':main()
