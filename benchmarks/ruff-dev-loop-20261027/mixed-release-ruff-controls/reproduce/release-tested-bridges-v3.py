"""Build ordinary Rust consumers in both directions and probe the sealed real Ruff shared objects."""
from pathlib import Path
import ctypes,hashlib,json,os,shutil,subprocess as sp,sys
h=Path('/home/dev-user/.cache/ohm-mixed-release-pilot-20261027')
scope={}; exec(compile((h/'release-ruff.py').read_text().split("if sys.argv[1]=='init':")[0],str(h/'release-ruff.py'),'exec'),scope)
d=scope['d']; tool=scope['tool']; release=scope['release']; driver=scope['driver']; son=scope['son']; sha=scope['sha']; write=scope['write']
assert (h/'tested-run-v3.rc').read_text().strip()=='0'
out=h/'ordinary-tested-bridges';out.mkdir();(out/'source').mkdir();inp=out/'canonical-input';inp.mkdir();outcanon=d/'args'
for p in (out/'source',inp,outcanon):assert p.is_dir()
cenv=dict(os.environ,RUSTUP_HOME=str(d/'rustup'),RUSTUP_AUTO_INSTALL='0',LD_LIBRARY_PATH=str(tool/'lib'),LC_ALL='C.UTF-8')
env={k:v for k,v in cenv.items() if k not in {'RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'}}
sources=out/'source'
(sources/'caller.rs').write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
def rust(arm,label,args,bridge=None):
 to=out/label;to.mkdir();scope['space']()
 cmd=['taskset','-c','0-7','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(release),str(tool),'--ro-bind',str(driver),str(tool/'lib'/son),'--bind',str(to),str(outcanon)]
 if bridge:cmd+=['--ro-bind',str(bridge),str(inp)]
 for field in ('target','shared','registry-home'):cmd+=['--ro-bind',str(h/arm/field),str(d/field)]
 cmd+=['--chdir',str(scope['src']),'--','/home/dev-user/.cargo/bin/rustc','+ohm','--sysroot',str(tool),'--edition=2024','-C','debuginfo=line-tables-only','-C','link-arg=-B'+str(tool/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),*map(str,args)]
 proc=sp.run(cmd,env=env,capture_output=True);(to/'stderr').write_bytes(proc.stderr);write(to/'args.json',cmd)
 assert proc.returncode==0,(label,proc.stderr.decode()[-1400:]);return to
def native(so):
 syms=[l.split()[-1] for l in sp.check_output(['nm','-D','--defined-only',so],text=True).splitlines()]
 assert len(syms)>=8
 py="""import ctypes,json,sys
l=ctypes.CDLL(sys.argv[1]); s=json.loads(sys.argv[2]); [getattr(l,n) for n in s]
alloc=getattr(l,'__wbindgen_malloc'); alloc.argtypes=[ctypes.c_uint32]*2;alloc.restype=ctypes.c_uint32
free=getattr(l,'__wbindgen_free');free.argtypes=[ctypes.c_uint32]*3;free.restype=None
v=[alloc(0,a) for a in (1,2,4,8,16,32)]
for a in v:free(a,0,a)
print(json.dumps(v))"""
 vals=json.loads(sp.check_output([sys.executable,'-c',py,so,json.dumps(syms)]));assert vals==[1,2,4,8,16,32]
 return {'exports':syms,'zero_width_alloc':vals,'zero_width_free':True,'so_sha256':sha(so)}
def members(rlib):
 names=sp.check_output(['ar','t',rlib],text=True).splitlines();assert len(set(names))==len(names)
 return [[n,hashlib.sha256(sp.check_output(['ar','p',rlib,n])).hexdigest()] for n in names]
def actual_argv(arm,where,crate):
 for f in (h/'evidence'/arm/where).glob('rustc-*.json'):
  x=json.loads(f.read_bytes());
  if x[x.index('--crate-name')+1]==crate:return x
 raise RuntimeError(crate)
def libs(args):
 a=[]
 for i,s in enumerate(args):
  if s=='-L':a+=['-L',args[i+1]]
  elif s.startswith('-L'):a.append(s)
 return a
cases={};arms=['pair','forced']
for crate,expr,want in [('ruff_wasm','ruff_wasm::Workspace::version()','0.17.0'),('ty_wasm','ty_wasm::version()','93526150d')]:
 src=sources/(crate+'-bridge.rs');src.write_text('pub fn observed() -> String { '+expr+'.to_string() }\n')
 c=cases[crate]={'native':{},'members':{},'bridge_metadata':{},'combinations':{}}
 locations=[];search={}
 for arm,label in [('pair','tested-edit'),('forced','tested-full-edit')]:
  rec=h/'evidence'/arm/label
  a=next(j for line in (rec/'stdout').read_bytes().splitlines() if (j:=json.loads(line)).get('reason')=='compiler-artifact' and j['target']['name']==crate)
  rlib,=map(Path,[p for p in a['filenames'] if p.endswith('.rlib')]); so,=map(Path,[p for p in a['filenames'] if p.endswith('.so')]);locations.append(rlib)
  phys=h/arm/'target';c['native'][arm]=native(phys/so.relative_to(d/'target'));c['members'][arm]=members(phys/rlib.relative_to(d/'target'))
  args=actual_argv(arm,label,crate);search[arm]=libs(args)
  dest=rust(arm,crate+'-bridge-'+arm,['--crate-name','ordinary_bridge','--crate-type','rlib',src,'--extern',crate+'='+str(rlib),'-L','dependency='+str(rlib.parent),*search[arm],'-o',outcanon/'libordinary_bridge.rlib'])
  c['bridge_metadata'][arm]=hashlib.sha256(sp.check_output(['ar','p',dest/'libordinary_bridge.rlib','lib.rmeta'])).hexdigest()
 assert locations[0]==locations[1];assert c['native']['pair']==c['native']['forced'] and c['bridge_metadata']['pair']==c['bridge_metadata']['forced']
 for orig in arms:
  for current in arms:
   dest=rust(current,'caller-'+crate+'-'+orig+'-'+current,['--crate-name','ordinary_user',sources/'caller.rs','--extern','ordinary_bridge='+str(inp/'libordinary_bridge.rlib'),'-L','dependency='+str(rlib.parent),*search[current],'-o',outcanon/'ordinary_user'],out/(crate+'-bridge-'+orig))
   exe=dest/'ordinary_user';v=sp.check_output([exe],text=True).strip()
   c['combinations'][orig+'__'+current]={'stdout':v,'elf_sha256':sha(exe),'status':0}
 # The old stage1 native driver reported these same two workspace/version literals; bind the observed program per crate.
 values={v['stdout'] for v in c['combinations'].values()};assert values=={want},(crate,values)
 elfs={v['elf_sha256'] for v in c['combinations'].values()};assert len(elfs)==1,(crate,elfs)
 x,y=c['members']['pair'],c['members']['forced'];assert len(x)==len(y)
 c['archive_comparison']={'members':len(x),'changed_names':sum(a!=b for (a,_),(b,_) in zip(x,y)),'changed_payloads':[[a,b] for (a,s),(b,q) in zip(x,y) if s!=q]}
 write(out/'result.json',cases);print(crate,len(elfs),values,c['archive_comparison'],flush=True)
scope['space']()
