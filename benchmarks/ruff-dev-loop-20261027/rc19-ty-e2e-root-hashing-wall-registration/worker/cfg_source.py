"""Bind each cfg span to a specific token in the exact libc and Rust source distribution."""
import hashlib,io,re,subprocess,tarfile
from pathlib import Path
D=Path(__file__).resolve().parent
COMMIT='ca780121cea38bb9b0538d020d4bcce76ca30cbc';LIBC_ARCHIVE='3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2';LIBC_SOURCE='999588f6f4ac24156c1bf9260d639a64247a83d7b6db187f4f94f7305c5cde47';UNWIND_BLOB='69b5e81a392152805364d14182ec8dc448586f6a';TOKEN=b'target_feature = "crt-static"'
def sha(b):return hashlib.sha256(b).hexdigest()
def declarations(b):
 ds=[]
 for m in re.finditer(rb'\#\[link\((?:(?!\)\]).)*?\)\]',b,re.S):
  s=m[0];name=re.search(rb'\bname\s*=\s*"([a-zA-Z_0-9]+)"',s)
  if name and s.count(TOKEN)==1:
   start=m.start()+s.index(TOKEN);end=start+len(TOKEN);inner=b[start:end]
   assert inner==TOKEN and b[start-1:start]+b[end:end+1]==b'()';ds.append({'library':name[1].decode(),'start':start,'end':end,'negated':b[start-4:start]==b'not(','line':b[:start].count(b'\n')+1,'decl_start':m.start(),'decl_end':m.end()})
 return ds
def select_files():
 rep=Path.home()/'code/oss/ohm-rust-pin-pending-metadata-20261029';cargo=Path.home()/'.cache/ohm-rc20-ty-e2e-proofless-20261029/states/parent-warm/cargo-home/registry'
 src,=cargo.glob('src/*/libc-0.2.189/src/unix/mod.rs');arc,=cargo.glob('cache/*/libc-0.2.189.crate');a=arc.read_bytes();assert sha(a)==LIBC_ARCHIVE
 def git(path):return subprocess.check_output(['git','-C',rep,'show',COMMIT+':'+path])
 lock=git('library/Cargo.lock');assert b'name = "libc"\nversion = "0.2.189"' in lock and LIBC_ARCHIVE.encode() in lock
 with tarfile.open(fileobj=io.BytesIO(a),mode='r:gz')as tar:x=tar.extractfile('libc-0.2.189/src/unix/mod.rs').read()
 assert x==src.read_bytes() and sha(x)==LIBC_SOURCE
 y=git('library/unwind/src/lib.rs');assert hashlib.sha1(b'blob '+str(len(y)).encode()+b'\0'+y).hexdigest()==UNWIND_BLOB
 names=['util','rt','pthread','m','dl','c','gcc_eh','gcc','c','util','rt','pthread','m','dl','c'];ds=declarations(x);expected=list(zip(names,[False]*9+[True]*6));a,=[ds[i:i+15] for i in range(len(ds)-14) if [(d['library'],d['negated'])for d in ds[i:i+15]]==expected];assert a[0]['line']==456
 matches=declarations(y);us,=[d for d in matches if d['library']=='gcc_s' and d['line']==148 and d['negated']];assert b'not(feature = "llvm-libunwind")' in y[us['decl_start']-170:us['decl_start']] and b'not(feature = "system-llvm-libunwind")' in y[us['decl_start']-170:us['decl_start']]
 return {5:{'source':'libc-0.2.189/src/unix/mod.rs','file_sha256':sha(x),'package_sha256':LIBC_ARCHIVE,'stdlib_lock_sha256':sha(lock),'declarations':a,'data':x},7:{'source':'library/unwind/src/lib.rs','file_sha256':sha(y),'git_blob':UNWIND_BLOB,'git_source':COMMIT,'declarations':[us],'data':y}}
def bind(rec,sources,buf,num):
 positions=[];bases={};r=rec['spans'];assert len(r)==23 and rec['indexed_crates']==233
 assert set(rec['libraries'])=={'5','7','146'} and {k:v[0]for k,v in rec['libraries'].items()}=={'5':'libc','7':'unwind','146':'psm'}
 for x in r:
  owner,i,name,*kinds=x['context'];sf=sources[owner];decl=sf['declarations'][i];assert decl['library']==name
  child=kinds[-1]==['target_feature','crt-static'];inner=[4,['target_feature','crt-static']];neg=decl['negated'];assert kinds==([4,inner[1]] if not neg else [2,4,inner[1]] if child else [2,inner])
  a=decl['start']-(not child);b=decl['end']+(not child);text=sf['data'][a:b];assert text==(TOKEN if child else b'('+TOKEN+b')')
  inferred=x['lo']-a; assert bases.setdefault(owner,inferred)==x['hi']-b==inferred
  assert buf[x['offset']:x['end']]==num(x['lo'])+num(x['hi'])
  positions.append({**x,'source':sf['source'],'sha256':sf['file_sha256'],'local_lo':a,'local_hi':b,'line':decl['line'],'annotated_text':text.decode(),'inferred_source_base':inferred})
 assert set(bases)==set(sources);return bases,positions
