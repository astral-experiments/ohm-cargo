from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
receipts=q/'receipts';banks=ram/'banks';banks.mkdir(exist_ok=True)
def native(d):
 calls=[]
 for f in sorted((d/'trace').glob('run.*')):
  data=f.read_bytes();status=re.findall(rb'\+\+\+ exited with (\d+) \+\+\+',data);st=int(status[-1])if status else None;pending=None
  for full in data.splitlines():
   line=full
   if line.startswith(b'execve(')and line.endswith(b'<unfinished ...>'):assert pending is None;pending=line[:-len(b'<unfinished ...>')];continue
   if line.startswith(b'<... execve resumed>'):assert pending;line=pending+line[len(b'<... execve resumed>'):];pending=None
   if not line.startswith(b'execve(') or not re.search(rb'\)\s+= 0$',line):continue
   m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
   image=ast.literal_eval(m[1].decode());args=ast.literal_eval(m[2].decode());nm=Path(image).name;kind=None;name=None
   if nm=='rustc'and '--crate-name'in args and '--out-dir'in args and '--print=file-names'not in args:
    name=args[args.index('--crate-name')+1]
    if name in ('___','__'):continue
    kind='partial'if any(z in ('-Zlink-only','-Zlink-only=yes')for z in args)or any(z=='-Z'and v.split('=')[0]=='link-only'for z,v in zip(args,args[1:]))else'full'
   elif nm=='ld.bfd'and '/wild-ld/'in image:kind='wild';name=args[args.index('-o')+1]
   elif nm.startswith(('build_script_build','build-script-build'))and('/run/'in image or'/build/'in image):kind='script';name=nm
   elif nm=='git'and 'log'in args:kind='gitlog';name=nm
   if kind:
    assert st==0,(kind,st);row={'kind':kind,'name':name,'argv':args,'image':image,'pid':f.name,'exit':st,'raw_argv_sha':H(m[2]),'raw_exec_sha':H(data)}
    if kind in ('full','partial'):
     row['crate_type']=args[args.index('--crate-type')+1]if '--crate-type'in args else None
     if name=='ruff':
      # Rustc binds the specific named extern, including proc-macro dylibs, at the copied canonical path.
      row['externs']={args[i+1].split('=',1)[0]:[v,Path(v).stat().st_size,sha(v)]for i,tok in enumerate(args[:-1])if tok=='--extern'and'='in args[i+1]for v in [args[i+1].split('=',1)[1]]}
    calls.append(row)
  assert pending is None
 return calls
def prodinfo(label,d,items):
 arts=[x for x in items if x['reason']=='compiler-artifact']; selected=[x for x in arts if x['target']['name']=='ruff'and x['package_id'].split('#')[0].endswith('/crates/ruff')]
 lib,=[x for x in selected if x['target']['kind']==['lib']];bin,=[x for x in selected if x['target']['kind']==['bin']];rlib,=map(Path,[n for n in lib['filenames']if n.endswith('.rlib')])
 md=next((Path(n)for n in lib['filenames']if n.endswith('.rmeta')),rlib.with_suffix('.rmeta'));assert md.is_file()
 head=go(['rustc','+ohm','-Zls=root',md]).stdout;(d/'header.stdout').write_bytes(head)
 regs=re.search(rb'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',head,re.M);assert regs,head[:300]
 exe=Path(bin['executable']);res={}
 for tag,argv,inp,st in [('version',[str(exe),'version','--output-format','json'],None,0),('short_version',[str(exe),'--version'],None,0),('detailed_version',[str(exe),'version'],None,0),('lint',[str(exe),'check','--isolated','--no-cache','--config','lint.select=["F821"]','--stdin-filename','probe.py','--output-format','concise','-'],b'print(missing)\n',1),('format',[str(exe),'format','--isolated','--no-cache','--config','format.line-ending="lf"','--stdin-filename','probe.py','-'],b'x=1\r\n',0)]:
  z=subprocess.run(argv,env=env,cwd=w,input=inp,capture_output=True);(d/(tag+'.stdout')).write_bytes(z.stdout);(d/(tag+'.stderr')).write_bytes(z.stderr);assert z.returncode==st,(argv,z.returncode,z.stderr)
  res[tag]={'command':argv,'status':st,'stdout':z.stdout.decode(),'stderr':z.stderr.decode()}
 assert json.loads(res['version']['stdout'])['commit_info']['commit_hash']==plan['heads'][label],(label,res['version'])
 assert res['short_version']['stdout']=='ruff 0.17.0\n' and plan['heads'][label][:9]in res['detailed_version']['stdout']and 'F821'in res['lint']['stdout']and res['format']['stdout']=='x = 1\n'
 scripts=[x for x in items if x['reason']=='build-script-executed'and x['package_id'].split('#')[0].endswith('/crates/ruff')];assert len(scripts)==1,scripts
 dest=banks/d.name;dest.mkdir()
 manifests=list((t/'debug/build/workspaces').glob('*/*/ruff/*/out/ruff.rlink-cache.json'));assert len(manifests)==1,manifests
 m=manifests[0]; bank_root=m.parent;cache=json.loads(m.read_bytes());codegen=bank_root/'ruff.rlink-objects'
 cachefiles=[m,bank_root/'ruff.rlink',*sorted(x for x in codegen.iterdir()if x.is_file())]
 bankmap={}
 for x in cachefiles:
  rel=x.relative_to(bank_root);v=dest/rel;v.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(x,v);assert sha(x)==sha(v);bankmap[str(rel)]=[x.stat().st_size,sha(x)]
 deps={}
 libraries={Path(x).parent for x in lib['filenames']};roots=sorted({bank_root,*libraries})
 for i,root in enumerate(roots):
  for dep in sorted(root.glob('*.d')):
   raw=dep.read_bytes();n=f'dep-{i}-{dep.name}';(d/n).write_bytes(raw)
   deps[str(dep)]={'file':n,'sha256':H(raw),'bytes':len(raw),'env_deps':[z.decode()for z in raw.splitlines()if z.startswith(b'# env-dep:')]}
 return {'lib':{'private':regs[1].decode(),'stable_id':regs[2].decode(),'public':regs[3].decode(),'rlib':str(rlib),'rlib_sha256':sha(rlib),'metadata':str(md),'metadata_sha256':sha(md),'header_sha256':H(head)},'cli':{'path':str(exe),'sha256':sha(exe)},'oracles':res,'build_script':scripts[0],'deps':deps,'stored_terminal':{'root':str(bank_root),'bank':str(dest),'original':bankmap,'manifest':cache},'units':len(arts),'fresh':sum(x['fresh']for x in arts),'dirty':[[x['target']['name'],x['target']['kind']]for x in arts if not x['fresh']]}
def call(label,tag):
 view(label);d=receipts/tag;cmd=plan['command']
 if d.exists():
  assert tag=='A-train-0'and(d/'procs.json').is_file() and not(d/'result.json').exists()
 else:
  d.mkdir();(d/'trace').mkdir();monitor(['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/run',*cmd],d/'stdout',d/'stderr')
 msgs=[json.loads(x)for x in(d/'stdout').read_bytes().splitlines()];assert msgs[-1]=={'reason':'build-finished','success':True}; calls=native(d);put(d/'procs.json',calls)
 out=prodinfo(label,d,msgs);out.update(command=cmd,physical=dict(collections.Counter(x['kind']for x in calls)),compilers=[[x['kind'],x['name'],x['crate_type']]for x in calls if x['kind']in('full','partial')],head=plan['heads'][label],remaining=guard());put(d/'result.json',out);view(label);print(tag,out['units'],out['fresh'],out['compilers'],out['physical'],out['lib']['public'],flush=True);return out
def main():
 assert(q/'prepared.json').exists()
 with(p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);view('A')
  for i in range(3):
   rec=call('A','A-train-'+str(i))
   if i>=1 and rec['fresh']==rec['units'] and not rec['physical']:break
  else:raise RuntimeError('A does not settle')
  for tag,label in [('B-edit','B'),('B-repeat','B'),('A-restore','A'),('A-repeat','A')]:
   if 'repeat'not in tag:go(['git','switch','--detach',plan['heads'][label]])
   raw=call(label,tag)
   if 'repeat'in tag:assert raw['fresh']==raw['units'] and not raw['physical']
  put(q/'primary.json',{'tags':['B-edit','B-repeat','A-restore','A-repeat'],'source_again':plan['heads']['A'],'remaining':guard()})
if __name__=='__main__':main()
