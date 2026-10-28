"""Observe the two ordinary Rust executables before and after the private suggestion fix."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
def read(p):return json.loads(p.read_bytes())
cache={};latest={};user_code=set()
def dig(n):
 f=Path(n)
 if not f.is_file():return None
 z=f.stat();key=(z.st_dev,z.st_ino,z.st_size,z.st_ctime_ns)
 if key not in cache:cache[key]=sha(f)
 return [z.st_size,cache[key]]
def guard_source(rev):
 dif=sorted(os.fsdecode(x)for x in git('diff','--name-only','-z').split(b'\0')[:-1]);assert dif==(sorted(plan['files'])if rev else[]),dif
 assert git('rev-parse','HEAD').decode().strip()==plan['pin']
 assert all(sha(w/f)==v for f,v in plan['sha_edit'if rev else'sha_original'].items())
def jobs(d):
 out=[]
 for f in sorted((d/'trace').glob('run.*')):
  dat=f.read_bytes();rc=re.findall(rb'\+\+\+ exited with (\d+) \+\+\+',dat);ret=int(rc[-1])if rc else None;pending=None
  for line in dat.splitlines():
   if line.startswith(b'execve(')and line.endswith(b'<unfinished ...>'):assert pending is None;pending=line[:-len(b'<unfinished ...>')];continue
   if line.startswith(b'<... execve resumed>'):assert pending;line=pending+line[len(b'<... execve resumed>'):];pending=None
   if not line.startswith(b'execve(')or not re.search(rb'\)\s+= 0$',line):continue
   m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
   imag=ast.literal_eval(m[1].decode());arg=ast.literal_eval(m[2].decode());nm=Path(imag).name;entry={}
   if nm=='rustc'and '--crate-name'in arg and '--out-dir'in arg and '--print=file-names'not in arg:
    name=arg[arg.index('--crate-name')+1]
    if name in ('___','__'):continue
    assert os.path.samefile(imag,sdk/'bin/rustc')
    partial=any(z in ('-Zlink-only','-Zlink-only=yes')for z in arg)or any(z=='-Z'and v.split('=')[0]=='link-only'for z,v in zip(arg,arg[1:]))
    typ=arg[arg.index('--crate-type')+1]if '--crate-type'in arg else 'test';scope=Path(arg[arg.index('--out-dir')+1]);exs={name0:path for i,tok in enumerate(arg[:-1])if tok=='--extern'and'='in arg[i+1]for name0,path in [arg[i+1].split('=',1)]}
    entry={'kind':'partial'if partial else'full','name':name,'crate_type':typ,'out_dir':str(scope),'args':arg,'src':next((z for z in arg if z.endswith(('.rlink','.rs'))),None),'externs':{n:{'path':v,'after':dig(v),'previous_finished':latest.get(v)}for n,v in exs.items()},'products':{str(p):dig(p)for p in scope.glob('*')if p.is_file()and(p.suffix in('.rmeta','.rlib','.so','.rlink')or not p.suffix)},'object_bank':{str(p.relative_to(scope)):dig(p)for objdir in scope.glob('*.rlink-objects')for p in objdir.glob('*.o')}}
   elif nm=='ld.bfd'and '/wild-ld/'in imag:
    o=arg[arg.index('-o')+1];files=[k for k in arg if k.endswith(('.o','.so','.a','.rlib'))and not k.startswith('-')];entry={'kind':'wild','name':Path(o).name,'out':o,'out_digest':dig(o),'args':arg,'explicit_files_post':[[k,dig(k)]for k in files],'missing_lookups':'Post-command listed files cannot certify temporary native inputs, prior negative lookups, system scripts or native loader/side effects.'}
   elif nm.startswith(('build_script_build','build-script-build'))and('/run/'in imag or'/build/'in imag):entry={'kind':'script','name':nm,'args':arg}
   if entry:
    assert ret==0,(nm,ret);entry.update(pid=f.name,image=imag,exit=ret,argv_sha=H(m[2]),raw_sha=H(dat));out.append(entry)
  assert pending is None
 return out
def external(d,rlib,arts,rev):
 dirs=sorted({str(Path(f).parent)for it in arts for f in it['filenames']})
 exe=ram/('reader-'+d.name);cmd=['rustc','+ohm','--edition=2024','--crate-name','source_map_reader',q/'ops/reader.rs','--extern','annotate_snippets='+str(rlib),*[x for y in dirs for x in('-L','dependency='+y)],'-o',exe];monitor(cmd,d/'reader-build.out',d/'reader-build.err')
 z=subprocess.run([exe],env=env,cwd=w,capture_output=True);(d/'reader.out').write_bytes(z.stdout);(d/'reader.err').write_bytes(z.stderr)
 if rev:assert z.returncode==101 and b'index out of bounds'in z.stderr,(z.returncode,z.stderr[-400:])
 else:assert z.returncode==0 and all(x in z.stdout for x in(b'fixed line 2',b'fixed line 7',b'fixed line 13')),(z.returncode,z.stdout[-260:])
 return {'args':list(map(str,cmd)),'status':z.returncode,'source':plan['caller'],'stdout':H(z.stdout),'stderr':H(z.stderr),'elf':sha(exe),'library':str(rlib),'library_sha':sha(rlib)}
def call(tag,select,rev):
 guard_source(rev);d=q/'receipts'/(tag+'-'+select);d.mkdir();(d/'trace').mkdir()
 cmd=[n.replace('{crate}',select)for n in plan['command']];monitor(['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/run',*cmd],d/'cargo.stdout',d/'cargo.stderr')
 messages=[json.loads(z)for z in(d/'cargo.stdout').read_bytes().splitlines()];assert messages[-1]=={'reason':'build-finished','success':True}
 arts=[v for v in messages if v['reason']=='compiler-artifact'];workspace=[a for a in arts if a['package_id'].startswith('path+file://'+str(w)+'/')]
 inputs={f for v in arts for f in(v['filenames']+([v['executable']]if v['executable']else[]))};subset={f for v in workspace for f in(v['filenames']+([v['executable']]if v['executable']else[]))}
 ro={f:dig(f)for f in sorted(inputs)};assert all(ro.values())
 calls=jobs(d);put(d/'jobs.json',calls)
 for j in calls:
  if j['kind']in('partial','full'):
   j['extern_changes']=sorted(n for n,v in j['externs'].items()if v['previous_finished']!=v['after']);j['changed_products']=sorted(f for f,v in j['products'].items()if v!=latest.get(f))
 put(d/'jobs.json',calls);db={f:{'before':latest.get(f),'after':ro[f]}for f in sorted(subset)};put(d/'workspace-products.json',db)
 la,=[v for v in workspace if v['target']['name']=='annotate_snippets'and v['target']['kind']==['lib']];rlib,=[Path(f)for f in la['filenames']if f.endswith('.rlib')];md=rlib.with_suffix('.rmeta');assert md.is_file()
 root=go(['rustc','+ohm','-Zls=root',md]).stdout;(d/'header.txt').write_bytes(root);hsh=re.search(rb'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',root,re.M);assert hsh
 cli,=[v['executable']for v in workspace if v['target']['name']==select and v['target']['kind']==['bin']and v['executable']];version=go([cli,'--version']);(d/'version').write_bytes(version.stdout)
 if select=='ruff':
  args=[cli,'check','--isolated','--no-cache','--select','F821','--stdin-filename','probe.py','--output-format','concise','-'];oo=subprocess.run(args,input=b'print(missing)\n',env=env,cwd=w,capture_output=True);assert oo.returncode==1 and b'F821'in oo.stdout
 else:
  path=d/'typing.py';path.write_text('answer: int = "not an integer"\n');args=[cli,'check','--project',str(d),str(path),'--output-format','concise'];oo=subprocess.run(args,env=env,cwd=w,capture_output=True);assert oo.returncode==1 and b'invalid-assignment'in oo.stdout+oo.stderr,(oo.returncode,oo.stdout[-350:],oo.stderr[-350:])
 (d/'cli.stdout').write_bytes(oo.stdout);(d/'cli.stderr').write_bytes(oo.stderr)
 if tag in('original','edited','restored'):check=external(d,rlib,arts,rev)
 else:check=None
 row={'source':'reversed'if rev else'original','package':select,'command':cmd,'units':len(arts),'fresh':sum(x['fresh']for x in arts),'counts':dict(collections.Counter(x['kind']for x in calls)),'actual_rustc':[[x['kind'],x['name'],x['crate_type'],x['extern_changes'],len(x['changed_products'])]for x in calls if x['kind']in('full','partial')],'native_outputs':[x['out']for x in calls if x['kind']=='wild'],'producer':{'rlib':[str(rlib),dig(rlib)],'rmeta':[str(md),dig(md)],'public':hsh[3].decode(),'private':hsh[1].decode(),'stable_id':hsh[2].decode()},'cli':{'path':cli,'elf':dig(cli),'version':version.stdout.decode(),'observation':[oo.returncode,H(oo.stdout),H(oo.stderr)]},'caller':check,'storage':guard()};put(d/'result.json',row)
 latest.update(ro)
 for x in calls:
  if x['kind']in('full','partial'):latest.update(x['products']);latest.update({z['path']:z['after']for z in x['externs'].values()})
 print(tag,select,row['units'],row['fresh'],row['counts'],[(x['kind'],x['name'])for x in calls if x['kind']in('partial','full')],row['producer']['public'],None if not check else check['status'],flush=True)
 return row
def main():
 assert(q/'prepared.json').is_file();guard_source(False)
 with(p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  for tag,unit in plan['schedule']:
   if tag=='edited'and unit=='ruff':go(['git','apply','--reverse',q/'ops/edit.patch'])
   if tag=='restored'and unit=='ruff':go(['git','apply',q/'ops/edit.patch'])
   row=call(tag,unit,tag.startswith('edited'))
   if 'repeat'in tag:assert not row['counts']and row['units']==row['fresh']
  guard_source(False);put(q/'complete.json',{'physical_slots':12,'state':plan['pin'],'remaining':guard()})
if __name__=='__main__':main()
