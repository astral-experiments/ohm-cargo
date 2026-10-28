"""Compare supplied complete original rlibs with the portable inventory."""
from pathlib import Path
import struct,sys,json,gzip,hashlib
h=lambda b:hashlib.sha256(b).hexdigest()
def ar_members(b):
 assert b.startswith(b'!<arch>\n');off=8;names=b'';parts=[]
 while off<len(b):
  hd=b[off:off+60];assert hd[-2:]==b'\x60\n';dim=int(hd[48:58]);v=b[off+60:off+60+dim];assert len(v)==dim
  name=hd[:16].strip().decode()
  if name=='//':names=v
  elif name.startswith('/')and name[1:].isdigit():
   k=int(name[1:]);name=names[k:names.index(b'/\n',k)].decode()
  elif name.endswith('/')and name not in('/','/SYM64/'):name=name[:-1]
  parts.append([off,name,v]);off+=60+dim+(dim%2)
 assert off==len(b);return parts
def semantic_symbols(parts):
 pos={off:i for i,(off,name,v)in enumerate(parts)}
 assert parts[0][1]in('/','/SYM64/');size=4 if parts[0][1]=='/'else 8
 raw=parts[0][2];cnt=int.from_bytes(raw[:size],'big');ofs=raw[size:(1+cnt)*size];strings=raw[(1+cnt)*size:].split(b'\0')
 assert len(strings)>=cnt and all(v==b''for v in strings[cnt:])
 syms=[[s.decode(),pos[int.from_bytes(ofs[index*size:(index+1)*size],'big')]]for index,s in enumerate(strings[:cnt])]
 return syms
def sections(b):
 assert b[:6]==b'\x7fELF\x02\x01';off=struct.unpack_from('<Q',b,40)[0];w,n,idx=struct.unpack_from('<HHH',b,58)
 sh=[struct.unpack_from('<IIQQQQIIQQ',b,off+w*k)for k in range(n)];ss=sh[idx];nm=b[ss[4]:ss[4]+ss[5]];res={}
 for ix,x in enumerate(sh):
  if x[1]==8:continue
  name=nm[x[0]:nm.index(0,x[0])].decode()
  if name in res:name=name+'#'+str(ix)
  res[name]=b[x[4]:x[4]+x[5]]
 return res
if __name__=='__main__':
    actual=json.loads(gzip.decompress((Path(__file__).resolve().parent/'native-members.json.gz').read_bytes()))
    if not sys.argv[1:]:raise SystemExit('Supply one or more original native rlib files')
    for name in sys.argv[1:]:
        b=Path(name).read_bytes();r=actual[h(b)];parts=ar_members(b)
        assert r['whole']==[len(b),h(b)]
        assert r['ordered_archive_members']==[[n,len(v),h(v)]for _,n,v in parts]
        assert r['index_by_symbol_and_member_ordinal']==semantic_symbols(parts)
        assert r['native_object_sections']==[{k:[len(v),h(v)]for k,v in sections(raw).items()}for _,n,raw in parts if n.endswith('.o')]
        print(h(b))
