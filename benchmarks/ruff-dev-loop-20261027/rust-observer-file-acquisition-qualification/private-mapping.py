"""Show which bytes a held private mapping returns after an in-place write and an ABA."""
from pathlib import Path
import hashlib,json,mmap,os,subprocess,sys
root=Path(__file__).resolve().parent/'mapping-controls';root.mkdir(exist_ok=True)
def digest(buf):return hashlib.sha256(buf).hexdigest()
def stat(path):
 s=path.stat();return dict(inode=s.st_ino,bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,digest=digest(path.read_bytes()))
def change(path,value,times):
 code='''import os,sys;from pathlib import Path;p=Path(sys.argv[1]);f=p.open("r+b");f.write(sys.argv[2].encode());f.flush();os.fsync(f.fileno());f.close();os.utime(p,ns=(int(sys.argv[3]),int(sys.argv[4])))'''
 subprocess.run([sys.executable,'-c',code,str(path),value,str(times[0]),str(times[1])],check=True)
rows={}
for mode in ('in-place','aba'):
 p=root/(mode+'.data');p.write_bytes(b'17');first=stat(p);times=(p.stat().st_atime_ns,p.stat().st_mtime_ns)
 with p.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_COPY) as memo:
  early=digest(memo[:]);assert early==first['digest']
  if mode=='in-place':
   seen=memo[:].decode();change(p,'29',times)
  else:
   change(p,'29',times);seen=memo[:].decode();change(p,'17',times)
  final_held_bytes=memo[:];f.seek(0);final_fd=f.read()
 last=stat(p)
 assert first['inode']==last['inode'] and first['mtime_ns']==last['mtime_ns'] and first['bytes']==last['bytes']
 assert digest(final_fd)==digest(final_held_bytes)==last['digest'] and seen!=final_fd.decode()
 assert (early==last['digest'])==(mode=='aba')
 rows[mode]=dict(initial=first,read_value=seen,final=last,final_mmap=final_held_bytes.decode(),final_fd=final_fd.decode(),pre_equals_post=(early==last['digest']),ctime_changed=(first['ctime_ns']!=last['ctime_ns']))
(root/'result.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n');print({k:(v['read_value'],v['final_mmap'],v['pre_equals_post'],v['ctime_changed']) for k,v in rows.items()})
