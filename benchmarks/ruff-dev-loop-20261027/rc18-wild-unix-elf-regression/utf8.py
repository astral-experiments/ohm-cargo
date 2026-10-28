"""Check native ELF, response lexical semantics and stateful option ordering on stock and patched Wild."""
from pathlib import Path
import json,os,struct,subprocess,sys,hashlib
p=Path(sys.argv[1]);d=p/sys.argv[2];d.mkdir();candidate=Path(sys.argv[3]);assert candidate.is_file()
s=Path(sys.argv[4]).resolve()/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
def as_bytes(path,src):
 q=subprocess.run(['as','--64','-o',path],input=(src+'\n.section .note.GNU-stack,"",@progbits\n').encode(),capture_output=True);assert not q.returncode
def sha(v):return hashlib.sha256(v).hexdigest()
def needed(f):
 b=f.read_bytes();sec=[struct.unpack_from('<IIQQQQIIQQ',b,struct.unpack_from('<Q',b,40)[0]+i*struct.unpack_from('<H',b,58)[0])for i in range(struct.unpack_from('<H',b,60)[0])];r=[]
 for secd in sec:
  if secd[1]!=6:continue
  strs=sec[secd[6]];sl=b[strs[4]:strs[4]+strs[5]]
  for ix in range(secd[4],secd[4]+secd[5],16):
   tag,val=struct.unpack_from('<qQ',b,ix)
   if tag==1:r.append(sl[val:sl.index(b'\0',val)].decode())
 return r
entry=d/'entry τ with spaces.o';as_bytes(entry,'.text\n.globl _start\n_start:mov $41,%edi;mov $60,%eax;syscall')
libs=[]
for ix,soname in enumerate(['libretain-one.so','libdrop.so','libretain-two.so']):
 o=d/('obj %s.o'%ix);as_bytes(o,f'.text\n.globl unused_{ix}\nunused_{ix}:ret');so=d/soname;subprocess.run([s,'--threads=1','-shared','-soname',soname,'-o',so,o],check=True);libs.append(so)
primary=d/'program λ';inner=d/'nested tokens.rsp';outer=d/'outer.rsp';inner.write_text('--as-needed\u2003'+repr(libs[1].name)+'\n');outer.write_text(' '.join([repr(entry.name),'--no-as-needed',repr(libs[0].name),'--push-state',repr('@'+inner.name),'--pop-state',repr(libs[2].name),'--build-id',"-rpath '$ORIGIN'",'-o',repr(primary.name)])+'\n')
prefix=['--threads=1','-m','elf_x86_64','--dynamic-linker','/lib64/ld-linux-x86-64.so.2']
direct=[entry.name,'--no-as-needed',libs[0].name,'--push-state','--as-needed',libs[1].name,'--pop-state',libs[2].name,'--build-id','-rpath','$ORIGIN','-o',primary.name]
badfile=d/'bad.rsp';badfile.write_text('"unclosed\n');esc=d/'escaped.rsp';esc.write_text(r'entry\ τ\ with\ spaces.o'+'\n')
raw='raw-'+os.fsdecode(b'\xff');save=None;sentinel=None
tests=[('direct',direct,primary),('nested_utf8',['@'+outer.name],primary),('escaped_utf8',['@'+esc.name,'-o',primary.name],primary),('literal-at-value',[entry.name,'-o','@literal-output'],d/'@literal-output'),('bad-quote',['@'+badfile.name,'-o',primary.name],primary),('raw-rpath',['-rpath='+raw,entry.name,'-o',primary.name],primary),('raw-script',['--version-script',raw,entry.name,'-o',primary.name],primary),('raw-library',['-l:'+raw,entry.name,'-o',primary.name],primary),('saved-raw',[raw,'-o',primary.name],primary),('wasm-raw',['-flavor','wasm',raw,'-o',primary.name],primary)]
rows=[]
for label,linker in [('stock',s),('candidate',candidate)]:
 save=d/('save-artifacts-'+label);save.mkdir();sentinel=save/'untouched';sentinel.write_text('preserve')
 for name,argv,target in tests:
  target.unlink(missing_ok=True);env=os.environ.copy()
  if name=='saved-raw':env['WILD_SAVE_DIR']=str(save)
  q=subprocess.run([linker,*([] if name=='wasm-raw' else prefix),*argv],cwd=d,capture_output=True,env=env);row=dict(tool=label,case=name,exit=q.returncode,panic=b'panicked at'in q.stderr,diagnostic=q.stderr.decode(errors='backslashreplace'),elf=sha(target.read_bytes())if target.is_file() else None,runtime=None,needed=None)
  if q.returncode==0:row['needed']=needed(target);row['runtime']=subprocess.run([target]).returncode
  if name=='saved-raw':row['save_sentinel']=sentinel.is_file()
  rows.append(row)
(d/'complete.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
mp={(r['tool'],r['case']):r for r in rows};assert all(mp[v,'direct']['needed']==mp[v,'nested_utf8']['needed']==['libretain-one.so','libretain-two.so']for v in ('stock','candidate'))
for name in ('direct','nested_utf8','escaped_utf8','literal-at-value'):
 a,b=mp['stock',name],mp['candidate',name];assert a['runtime']==b['runtime']==41 and a['elf']==b['elf'],(name,a,b)
assert mp['stock','direct']['elf']==mp['candidate','nested_utf8']['elf'];assert mp['stock','bad-quote']['diagnostic']==mp['candidate','bad-quote']['diagnostic']
for name in ('raw-rpath','raw-script','raw-library','saved-raw','wasm-raw'):
 r=mp['candidate',name];assert r['exit']==1 and not r['panic'] and r['elf']is None,(name,r)
assert mp['candidate','saved-raw']['save_sentinel'];print([(r['tool'],r['case'],r['exit'],r['runtime'])for r in rows])
