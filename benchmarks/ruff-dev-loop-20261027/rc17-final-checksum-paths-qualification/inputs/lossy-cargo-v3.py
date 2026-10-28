"""Change the actual rlib behind an ASCII extern symlink, with a colliding rendered path."""
from pathlib import Path
import os
boot=Path(__file__).with_name("complete-matrix-final.py").read_text().split('cases={}')[0]
if os.environ.get('DROP_RELINK')=='1':boot=boot.replace("['cargo','+ohm','build'","['cargo','+ohm','-Zrelink-only=no','build'")
exec(compile(boot,"matrix setup","exec"),globals())
check_mode=os.environ.get("ONLY_CHECK")=="1"
if check_mode:
 def cargo(st,e,phase,ck,real,shadow):
  rec=st/'records'/phase;rec.mkdir(parents=True);out=run(['cargo','+ohm','check','--offline','-p','hold_direct','--message-format=json'],st/'code',e,ck,rec/'exec');(rec/'stdout.jsonl').write_bytes(out.stdout);(rec/'stderr').write_bytes(out.stderr);events=[json.loads(line) for line in out.stdout.splitlines()];rows=[j for j in events if j.get('reason')=='compiler-artifact'];roots=[j for j in rows if j['target']['name']=='hold_direct'];diags=[j['message'] for j in events if j.get('reason')=='compiler-message' and j['message']['level']=='error'];assert out.returncode==0 or any((d.get('code') or {}).get('code')=='E0308' for d in diags),(phase,out.stderr[-7000:],diags)
  paths=[Path(e['CARGO_TARGET_DIR']),Path(e['CARGO_BUILD_BUILD_DIR'])];fds=[f for base in paths for f in base.rglob('dep-bin-hold_direct') if f.is_file() and b'OBS' in f.read_bytes()];dep=[f for base in paths for f in base.rglob('hold_direct*.d') if f.parent.name=='out' and b'ohm-foreign-span-bytes' in f.read_bytes()];assert len(fds)<=1 and len(dep)<=1,(fds,dep)
  if fds:shutil.copy2(fds[0],rec/'fingerprint')
  if dep:shutil.copy2(dep[0],rec/'rustc.d')
  else:(rec/'rustc.d').write_bytes(b'')
  b=fds[0].read_bytes() if fds else b'';res={'exit':out.returncode,'diagnostics':diags,'value':17 if out.returncode==0 else 29,'fresh':roots[0]['fresh'] if roots else None,'all_fresh':bool(roots) and all(x['fresh'] for x in rows),'complete':b[-33] if b else None,'version':b[5] if b else None,'real':sha(real),'shadow':sha(shadow) if shadow.is_file() else None};(rec/'row.json').write_text(json.dumps(res,indent=2)+'\n');print(st.name,phase,ck,o.rust,res['exit'],res['fresh'],res['complete'],flush=True);return res
all_results={}
for mode in os.environ.get('GUARD_MODES','ab,ba,only-valid').split(','):
 st=root/mode;st.mkdir();work=st/'code';shutil.copytree(tmpl,work);reader=work/'hold_direct/src/main.rs';order=mode if mode!='only-valid' else 'b'
 value='external_a::value()' if 'a' in order else 'external_b::value()'
 reader.write_text(''.join('extern crate external_'+s+';\n' for s in order)+reader.read_text().replace(');}',');let _ = external_b::value(); println!("escape-value={}",'+value+');}'))
 if check_mode:reader.write_text(reader.read_text()+'\nconst _: [();17] = [(); external_'+('a' if 'a' in order else 'b')+'::VALUE];\n')
 a=Path(os.fsdecode(os.fsencode(st)+b'/key-\xff'));b=st/'key-\ufffd';a.mkdir();b.mkdir();r=[a/'libsame.rlib',b/'libsame.rlib'];link=[st/'libexternal_a.rlib',st/'libexternal_b.rlib'];rootnames=['external_a','external_b'];start='old' if o.cargo=='upgrade' else o.cargo
 args=[]
 for ix in map('ab'.index,order):args+=['--extern',rootnames[ix]+'='+str(link[ix])]
 e=dict(base,CARGO_HOME=str(st/'home'),CARGO_TARGET_DIR=str(st/'target'),CARGO_BUILD_BUILD_DIR=str(st/'shared'),CARGO_ENCODED_RUSTFLAGS='\x1f'.join(args),CARGO_BUILD_JOBS='3')
 def compile_rlib(i,val,dst):
  src=st/'dep.rs';src.write_text('pub const VALUE:usize='+str(val)+'; pub fn value()->u32{'+str(val)+'}\n');out=st/'library.rlib';c=run(['rustc','+ohm','--crate-name',rootnames[i],src,'--crate-type','rlib','-Copt-level=1','-Cmetadata=kept-stable','-Cdebuginfo=0','-o',out],st,e,start)
  assert c.returncode==0,c.stderr[-1200:];shutil.copy2(out,dst)
 for i in range(2):compile_rlib(i,17 if i==0 or mode=='only-valid' else 39,r[i]);link[i].symlink_to(r[i])
 changed=0 if 'a' in order else 1;compile_rlib(changed,29,st/'future')
 rec={};target=r[changed];shadow=r[1-changed] if mode!='only-valid' else st/'absent'
 for phase in ['first','train','unchanged']:rec[phase]=cargo(st,e,phase,start,target,shadow)
 stat=target.stat();new=(st/'future').read_bytes();assert len(new)==stat.st_size,(mode,len(new),stat.st_size);target.write_bytes(new);os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns));rec['changed']=cargo(st,e,'changed',start,target,shadow)
 if o.cargo=='upgrade':
  rec['upgrade']=cargo(st,e,'upgrade','fixed',target,shadow);rec['upgrade-repeat']=cargo(st,e,'upgrade-repeat','fixed',target,shadow)
 end='fixed' if o.cargo=='upgrade' else start;rec['empty']=cargo(st,dict(e,CARGO_TARGET_DIR=str(st/'empty-target'),CARGO_BUILD_BUILD_DIR=str(st/'empty-shared')),'empty',end,target,shadow)
 assert rec['first']['value']==17 and rec['empty']['value']==29
 for phase in rec:
  d=(st/'records'/phase/'rustc.d').read_text();rec[phase]['raw_header']=d.splitlines()[0] if d.startswith('# ohm-raw-') else None;actual_path=str(b/'libsame.rlib');rec[phase]['replacement_checksums']=[line for line in d.splitlines() if line.startswith('# checksum:') and line.endswith(' '+actual_path)]
 if check_mode:
  for v in rec.values():
   if v['value']==29:assert v['diagnostics']==rec['empty']['diagnostics']
 all_results[mode]=rec
(root/'result.json').write_text(json.dumps(all_results,indent=2)+'\n');(root/'identity.json').write_text(json.dumps({'rust':o.rust,'cargo':o.cargo,'old_cargo':sha(old_c),'fixed_cargo':sha(new_c),'frontend':sha(logical/'bin/rustc'),'driver':sha(logical/'lib'/__import__('re').search(rb'Shared library: \[(librustc_driver[^\]]+)\]',subprocess.check_output(['readelf','-d',logical/'bin/rustc'])).group(1).decode())},indent=2)+'\n')
