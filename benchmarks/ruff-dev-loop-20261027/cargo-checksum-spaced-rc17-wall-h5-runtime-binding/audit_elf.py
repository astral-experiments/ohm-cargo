"""Describe a failed raw ELF comparison without broadening the timing admission rule."""
import hashlib,mmap,struct
from pathlib import Path

def parts(f):
    with f.open('rb')as fin,mmap.mmap(fin.fileno(),0,access=mmap.ACCESS_READ)as data:
        assert data[:6]==b'\x7fELF\x02\x01'
        off=struct.unpack_from('<Q',data,40)[0];size,n,names=struct.unpack_from('<HHH',data,58);assert size==64
        h=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*size)for i in range(n)]
        start,amount=h[names][4:6];out={}
        for i,row in enumerate(h):
            at=start+row[0];end=data.find(b'\x00',at,start+amount);assert end>=at
            name=data[at:end].decode();pos,length=row[4:6];typ=row[1]
            assert name not in out
            out[name]=[typ,row[2],pos,length,row[6],row[7],row[8],row[9], None if typ==8 else hashlib.sha256(memoryview(data)[pos:pos+length]).hexdigest()]
        return out
def changed(a,b):
    left,right=parts(a),parts(b)
    return {name:[left.get(name),right.get(name)]for name in sorted(set(left)|set(right))if left.get(name)!=right.get(name)}
