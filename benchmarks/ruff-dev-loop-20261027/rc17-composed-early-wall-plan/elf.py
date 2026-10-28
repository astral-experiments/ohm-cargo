"""Require the exact same bytes outside the two independently observed Wild fields."""
import hashlib
import mmap
import struct


def fingerprint(path):
    with path.open('rb') as fd, mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ) as b:
        assert b[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', b,18)[0]==62
        sh = struct.unpack_from('<Q',b,40)[0]
        width,count,idx = struct.unpack_from('<HHH',b,58)
        assert width == 64 and 0 < idx < count and sh+width*count <= len(b)
        rows = [struct.unpack_from('<IIQQQQIIQQ',b,sh+i*width) for i in range(count)]
        start, size = rows[idx][4:6]
        assert start+size <= len(b)
        wanted = {}
        for i, row in enumerate(rows):
            pos=start+row[0];end=b.find(b'\0',pos,start+size)
            assert start <= pos <= end < start+size
            name=b[pos:end]
            if name in (b'.rodata',b'.note.gnu.build-id'):
                assert name not in wanted
                wanted[name]=(i,row)
        i, ro = wanted[b'.rodata']; _, note = wanted[b'.note.gnu.build-id']
        pos = note[4]; ns, ds, kind = struct.unpack_from('<III', b, pos)
        assert note[1] == 7 and (ns,ds,kind)==(4,32,3) and note[5]==48 and b[pos+12:pos+16]==b'GNU\0'
        assert ro[9] in (0,1,2,4,8,16,32,64)
        digest=hashlib.sha256();previous=0
        for off,n in sorted([(pos+16,ds),(sh+i*width+56,8)]):
            assert previous <= off < off+n <= len(b)
            digest.update(memoryview(b)[previous:off]);digest.update(bytes(n));previous=off+n
        digest.update(memoryview(b)[previous:])
        return {'normalized':digest.hexdigest(),'bytes':len(b),'build_id':b[pos+16:pos+16+ds].hex(),'rodata_entsize':ro[9]}
