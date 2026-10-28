"""Attribute actual ELF byte differences to named sections and exact Cargo namespace strings."""
import hashlib
import mmap
import struct

def describe(b, prefix):
    assert b[:6]==b'\x7fELF\x02\x01'
    sh=struct.unpack_from('<Q',b,40)[0];size,num,idx=struct.unpack_from('<HHH',b,58)
    headers=[struct.unpack_from('<IIQQQQIIQQ',b,sh+i*size) for i in range(num)]
    strings=headers[idx][4];limit=strings+headers[idx][5]
    areas=[];lookup={};spans=[]
    for i,h in enumerate(headers):
        pos=strings+h[0];name=b[pos:b.find(b'\x00',pos,limit)].decode()
        lookup[name]=(i,h)
        if h[1]!=8 and h[5] and h[4]+h[5]<=len(b):areas.append((h[4],h[4]+h[5],name))
    areas.extend([(0,64,'ELF header'),(sh,sh+num*size,'section table')])
    i,h=lookup['.rodata'];spans.append((sh+i*size+56,8,'rodata_entsize'))
    _,h=lookup['.note.gnu.build-id'];pos=h[4];n,d,kind=struct.unpack_from('<III',b,pos)
    assert n==4 and kind==3 and b[pos+12:pos+16]==b'GNU\x00'
    spans.append((pos+16,d,'build_id'))
    pos=0;found=[]
    while True:
        pos=b.find(prefix,pos)
        if pos==-1: break
        start=pos+len(prefix)-16
        assert b[start:start+16]==prefix[-16:] and b[start+16:start+17]==b'/'
        spans.append((start,16,'namespace'));found.append(start);pos+=len(prefix)
    h=hashlib.sha256();last=0
    for pos,n,kind in sorted(spans):
        assert pos>=last;h.update(memoryview(b)[last:pos]);h.update(bytes(n));last=pos+n
    h.update(memoryview(b)[last:])
    def section(i):
        return next((n for lo,hi,n in areas if lo<=i<hi),'unmapped')
    return h.hexdigest(),[(pos,section(pos)) for pos in found],section

def explain(files,workflow,layout):
    _,ws,bs,cs=layout[workflow]
    with files[0].open('rb') as lf,files[1].open('rb') as rf,mmap.mmap(lf.fileno(),0,access=mmap.ACCESS_READ) as a,mmap.mmap(rf.fileno(),0,access=mmap.ACCESS_READ) as b:
        results=[describe(m,('debug/build/workspaces/'+ws+'/v2-'+arm).encode()) for m,arm in [(a,bs),(b,cs)]]
        counts={};first=[]
        if len(a)==len(b):
            for lo in range(0,len(a),8192):
                x=a[lo:lo+8192];y=b[lo:lo+8192]
                if x!=y:
                    for i,(u,v) in enumerate(zip(x,y)):
                        if u!=v:
                            name=results[0][2](lo+i);counts[name]=counts.get(name,0)+1
                            if len(first)<18:first.append([lo+i,name])
        return dict(sizes=[len(a),len(b)],differing_bytes_by_section=counts,first_offsets=first,
                    namespace_occurrences=[r[1] for r in results],
                    digests_after_exact_namespace_and_two_fields=[r[0] for r in results])
