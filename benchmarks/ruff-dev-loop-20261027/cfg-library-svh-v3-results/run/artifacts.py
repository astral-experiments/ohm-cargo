"""Hash the actual indexed Rust archive members and native ELF sections; retain every missing table."""
import hashlib,mmap,struct
from pathlib import Path
def H(b):return hashlib.sha256(b).hexdigest()
def archive(path,source,md5s):
 with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as b:
  assert b[:8]==b'!<arch>\n';ofs=8;names=b'';a=[]; special=[]
  while ofs<len(b):
   hdr=b[ofs:ofs+60];assert hdr[-2:]==b'`\n';ident=hdr[:16].rstrip();n=int(hdr[48:58]);st=ofs+60;e=st+n
   if ident in (b'/',b'//'):
    if ident==b'//':names=b[st:e]
    special.append([ident.decode(),n,H(memoryview(b)[st:e])])
   else:
    name=(names[int(ident[1:]):].split(b'/\n')[0] if ident.startswith(b'/') and ident[1:].isdigit() else ident.rstrip(b'/')).decode();data=b[st:e];o={'name':name,'size':n,'sha256':H(data),'is_cgu':name.endswith('.rcgu.o')}
    if data[:6]==b'\x7fELF\x02\x01':
     shoff=struct.unpack_from('<Q',data,40)[0];sz,count,ni=struct.unpack_from('<HHH',data,58);assert sz==64;ss=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*sz) for i in range(count)];ns0=ss[ni];ns=data[ns0[4]:ns0[4]+ns0[5]];bygroup={};facts={'input_path_occurrences':0,'changed_source_file_md5':{k:0 for k in md5s}}
     for s in ss:
      key=ns[s[0]:ns.index(b'\0',s[0])].decode(errors='replace');buf=data[s[4]:s[4]+s[5]] if s[1]!=8 else b'';grp=key if key.startswith(('.debug','.zdebug')) else '#alloc' if s[2]&2 else '#other';g=bygroup.setdefault(grp,hashlib.sha256());g.update(key.encode()+b'\0');g.update(struct.pack('<Q',len(buf)));g.update(buf)
      if key.startswith(('.debug','.zdebug')):
       facts['input_path_occurrences']+=buf.count(source.encode())
       for k in md5s:facts['changed_source_file_md5'][k]+=buf.count(md5s[k])
     o['section_content_digests']={k:v.hexdigest() for k,v in bygroup.items()};o['debug_source']=facts
    a.append(o)
   ofs=e+(e%2)
  assert ofs==len(b);return {'bytes':len(b),'sha256':H(b),'index_and_names':special,'members':a}
def metadata(path,md5s):
 b=path.read_bytes();return {'sha256':H(b),'bytes':len(b),'source_md5':{k:{'hex':v.hex(),'count':b.count(v),'first':b.find(v)} for k,v in md5s.items()}}
