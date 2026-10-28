"""Lossless ELF corpus for Unix filenames, real no-SONAME strings and GNU response parsing."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys
p=Path(sys.argv[1]);w=p/sys.argv[2];w.mkdir();s17=(Path(sys.argv[4]).resolve()/'lib/rustlib/x86_64-unknown-linux-gnu/bin')
wild=s17/'wild-ld/ld.bfd';lld=s17/'rust-lld';candidate=p/sys.argv[3];assert candidate.is_file()
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def asm(f,s):
 q=subprocess.run(['as','--64','-o',f],input=(s+'\n.section .note.GNU-stack,"",@progbits\n').encode(),capture_output=True);assert q.returncode==0,q.stderr
def file(raw):return w/os.fsdecode(raw)
def run_link(tool,args,cwd=w):
 cmd=([lld,'-flavor','gnu'] if tool=='lld' else [wild] if tool=='stock' else [candidate])+['--threads=1',*args]
 q=subprocess.run(cmd,cwd=cwd,capture_output=True);return {'rc':q.returncode,'panic':b'panicked at'in q.stderr,'stderr':q.stderr.decode(errors='backslashreplace').replace(str(w),'<work>'),'stdout':q.stdout.decode(errors='backslashreplace'),'cmd_sha':hashlib.sha256(b'\0'.join(map(os.fsencode,cmd))).hexdigest()}
def needed(f):
 b=f.read_bytes();assert b[:6]==b'\x7fELF\2\1'
 sec=[struct.unpack_from('<IIQQQQIIQQ',b,struct.unpack_from('<Q',b,40)[0]+i*struct.unpack_from('<H',b,58)[0])for i in range(struct.unpack_from('<H',b,60)[0])]
 out=[]
 for s in sec:
  if s[1]!=6:continue
  names=b[sec[s[6]][4]:sec[s[6]][4]+sec[s[6]][5]]
  for ix in range(s[4],s[4]+s[5],16):
   tag,val=struct.unpack_from('<qQ',b,ix)
   if tag==1:out.append(names[val:names.index(b'\0',val)])
 return out
entry=w/'entry.o';asm(entry,'.text\n.globl _start\n_start:call foreign_value;mov %eax,%edi;mov $60,%eax;syscall')
def val(f,x):asm(f,'.text\n.globl foreign_value\n.type foreign_value,@function\nforeign_value: mov $%d,%%eax;ret\n'%x)
ordinary=w/'want.o'; raw=file(b'want real-\xff.o');dec=w/'want real-�.o'
val(raw,41);val(ordinary,41);val(dec,99)
for f in [w/'dso_41.o',w/'dso_99.o']:val(f,41 if '41'in f.name else 99)
raw_dll=file(b'link-\xff.so');dec_dll=w/'link-�.so';plain_dll=w/'link-plain.so'
for dst,src in [(raw_dll,w/'dso_41.o'),(dec_dll,w/'dso_99.o'),(plain_dll,w/'dso_41.o')]:
 # Stock builds the same true no-SONAME DSO at an ASCII path, then publish those bytes at the tested native name.
 tmp=w/'private-so';rr=run_link('stock',['-shared','-o',tmp,src]);assert rr['rc']==0,rr;dst.write_bytes(tmp.read_bytes());tmp.unlink()
assert sha(plain_dll)==sha(raw_dll)!=sha(dec_dll)
dirraw=file(b'libdir-\xff');dird=w/'libdir-�';dirraw.mkdir();dird.mkdir()
for d,f in ((dirraw,raw),(dird,dec)):subprocess.run(['ar','rcs',d/'libprobe.a',f],check=True)
out=[]
for tool in ('stock','candidate','lld'):
 exe=w/'program';body=lambda x: os.fsencode(x)
 inner=file(b'quoted-\xfd.rsp');outer=w/'outer.rsp'
 inner.write_bytes(b'"'+body(raw)+b'"\n');outer.write_bytes(b'@'+body(inner)+b'\n')
 unicode_file=w/'unicode-token.rsp';unicode_file.write_bytes(body(entry)+'\u2003'.encode()+b'"'+body(raw)+b'"\n')
 rawout=file(b'out-\xff');ascii_rsp=w/'untouched.rsp';ascii_rsp.write_text(f'{entry}\n{ordinary}\n')
 prefix=['-m','elf_x86_64','--build-id','-o',exe];ld=w/'nope'
 cases=[
 ('ascii',prefix+[entry,ordinary],exe),('raw',prefix+[entry,raw],exe),('decoy',prefix+[entry,dec],exe),
 ('nested',prefix+[entry,b'@'+body(outer)],exe),('unicode-white',prefix+[b'@'+body(unicode_file)],exe),('ascii-response',prefix+[b'@'+body(ascii_rsp)],exe),
 ('output-separated',['-o',rawout,entry,raw],rawout),('output-long',['--output='+str(rawout),entry,raw],rawout),('output-attached',[b'-o'+body(rawout),entry,raw],rawout),
 ('search-separate',prefix+[entry,'-L',dirraw,'-lprobe'],exe),('search-joined',prefix+[entry,b'-L'+body(dirraw),'-lprobe'],exe),
 ('needed-native',prefix+['--dynamic-linker','/lib64/ld-linux-x86-64.so.2',entry,raw_dll],exe),
 ('needed-decoy',prefix+['--dynamic-linker','/lib64/ld-linux-x86-64.so.2',entry,dec_dll],exe),
 ('ordinary-missing',prefix+[entry,w/'absent.o'],exe),('raw-missing',prefix+[entry,file(b'absent-\xfe.o')],exe),
 ('bad-option',prefix+['--thing-'+os.fsdecode(b'\xfc'),entry,raw],exe),
 ]
 for case,args,target in cases:
  if target.exists():target.unlink()
  r=run_link(tool,args);r.update(tool=tool,case=case,wrote=target.exists(),elf=None,value=None,needed=None)
  if r['rc']==0 and target.exists():
   r['elf']=sha(target);r['value']=subprocess.run([target],capture_output=True).returncode;r['needed']=[s.hex()for s in needed(target)]
   if case=='needed-native':
    assert needed(target)==[body(raw_dll)],(tool,needed(target));saved=w/'save-dso';raw_dll.rename(saved)
    q=subprocess.run([target],capture_output=True);r['missing_dso_rc']=q.returncode;assert q.returncode==127;saved.rename(raw_dll)
  elif case in ('ordinary-missing','raw-missing','bad-option'):assert r['rc'] and not r['wrote']
  out.append(r)
 (w/'controls.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print([(r['tool'],r['case'],r['rc'],r['value'])for r in out],flush=True)
