"""Allow variation only in the Wild build ID and .rodata sh_entsize."""
from pathlib import Path
import hashlib
import mmap
import struct
import tempfile

def normalize(path):
    with path.open('rb') as s,mmap.mmap(s.fileno(),0,access=mmap.ACCESS_READ) as b:
        assert b[:6]==b'\x7fELF\x02\x01'
        sh=struct.unpack_from('<Q',b,40)[0];size,num,idx=struct.unpack_from('<HHH',b,58);assert size==64 and num>idx
        entries=[struct.unpack_from('<IIQQQQIIQQ',b,sh+size*i) for i in range(num)];strings=entries[idx][4];limit=strings+entries[idx][5]
        sections={}
        for i,k in enumerate(entries):
            start=strings+k[0];end=b.find(b'\0',start,limit)
            assert strings<=start<=end<limit
            sections[b[start:end].decode()]=(i,k)
        i,ro=sections['.rodata'];_,note=sections['.note.gnu.build-id'];off=note[4];n,ds,kind=struct.unpack_from('<III',b,off)
        assert note[1]==7 and n==4 and kind==3 and b[off+12:off+16]==b'GNU\x00' and 8<=ds<=64
        assert ro[9] in (0,1,2,4,8,16,32,64,128,256)
        h=hashlib.sha256();lo=0
        for start,length in sorted([(off+16,ds),(sh+i*size+56,8)]):
            assert start>=lo and start+length<=len(b)
            h.update(memoryview(b)[lo:start]);h.update(bytes(length));lo=start+length
        h.update(memoryview(b)[lo:])
        return dict(bytes=len(b),normalized=h.hexdigest(),build_id=b[off+16:off+16+ds].hex(),rodata_entsize=ro[9])

def selftest():
    src=Path('/bin/true');raw=src.read_bytes();sh=struct.unpack_from('<Q',raw,40)[0]
    size,num,idx=struct.unpack_from('<HHH',raw,58);heads=[struct.unpack_from('<IIQQQQIIQQ',raw,sh+size*i) for i in range(num)]
    names=heads[idx][4];sections={raw[names+k[0]:raw.index(0,names+k[0])].decode():(i,k) for i,k in enumerate(heads)}
    old=normalize(src);idx,head=sections['.rodata'];_,note=sections['.note.gnu.build-id'];_,code=sections['.text']
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/'copy';m=bytearray(raw)
        m[note[4]+16]^=1;struct.pack_into('<Q',m,sh+size*idx+56,0 if head[9] else 8);f.write_bytes(m)
        narrow=normalize(f);assert narrow['normalized']==old['normalized'] and narrow['build_id']!=old['build_id'] and narrow['rodata_entsize']!=old['rodata_entsize']
        m[code[4]]^=1;f.write_bytes(m);assert normalize(f)['normalized']!=old['normalized']
    return {'identical_control':True,'two_permitted_fields':True,'different_text_rejected':True}

