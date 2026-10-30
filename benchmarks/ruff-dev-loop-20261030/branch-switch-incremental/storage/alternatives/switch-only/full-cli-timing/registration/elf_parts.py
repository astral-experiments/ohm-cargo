from pathlib import Path
import hashlib,json,mmap,struct,sys
def sha(x):return hashlib.sha256(x).hexdigest()
def image(mm):
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',mm)
    ident,_,machine,_,_,pho,sho,_,_,psz,pnum,ssz,snum,namesid=header
    assert ident[:6]==b'\x7fELF\x02\x01' and machine==62 and psz==56 and ssz==64
    secs=[struct.unpack_from('<IIQQQQIIQQ',mm,sho+i*ssz) for i in range(snum)]
    no,ns=secs[namesid][4:6];name_table=mm[no:no+ns]
    def get(n):return name_table[n:name_table.index(0,n)].decode('ascii')
    info={};build_desc=None;rostr=None
    for i,x in enumerate(secs):
        name=get(x[0]);off,sz=x[4:6]
        assert off>=0 and sz>=0 and (x[1]==8 or off+sz<=len(mm))
        raw='' if x[1]==8 else sha(memoryview(mm)[off:off+sz])
        info[name]={'offset':off,'size':sz,'type':x[1],'flags':x[2],'sha256':raw,'entsize':x[9]}
        if name=='.rodata':rostr=sho+i*ssz+56
        if name=='.note.gnu.build-id':
            nsize,dsize,kind=struct.unpack_from('<III',mm,off)
            pos=off+12+((nsize+3)//4)*4
            assert kind==3 and mm[off+12:off+12+nsize]==b'GNU\0' and pos+dsize<=off+sz
            build_desc=pos,dsize
    phdr=[struct.unpack_from('<IIQQQQQQ',mm,pho+i*psz) for i in range(pnum)]
    return info,phdr,build_desc,rostr,sha(mm),len(mm)
def compare(a,b):
    with Path(a).open('rb') as fa,Path(b).open('rb') as fb,mmap.mmap(fa.fileno(),0,access=mmap.ACCESS_READ) as ma,mmap.mmap(fb.fileno(),0,access=mmap.ACCESS_READ) as mb:
        la,pa,ba,ra,ha,na=image(ma);lb,pb,bb,rb,hb,nb=image(mb)
        names=sorted(set(la)|set(lb));sections={n:{'a':la.get(n),'b':lb.get(n)} for n in names if la.get(n)!=lb.get(n)}
        hit_header=ra==rb and ra is not None and {la['.rodata']['entsize'],lb['.rodata']['entsize']}=={0,8}
        permit=(na==nb and ba==bb and ba and ba[1] in (20,32) and pa==pb and ra==rb and ra is not None)
        def mask(mm,off,sz,allow):
            digest=hashlib.sha256()
            end=off+sz
            spans=[(ba[0],ba[0]+ba[1])]
            if allow:spans.append((ra,ra+8))
            start=off
            for x,y in sorted(spans):
                a=max(start,x);b=min(end,y)
                if a<b:digest.update(memoryview(mm)[start:a]);digest.update(bytes(b-a));start=b
            digest.update(memoryview(mm)[start:end]);return digest.hexdigest()
        loads=[]
        if permit:
            for i,p in enumerate(pa):
                if p[0]==1:
                    off,sz=p[2],p[5];loads.append({'index':i,'offset':off,'size':sz,'masked_a':mask(ma,off,sz,False),'masked_b':mask(mb,off,sz,False)})
        norm=[mask(ma,0,len(ma),bool(hit_header)),mask(mb,0,len(mb),bool(hit_header))] if permit else []
        return {'raw_sha256':[ha,hb],'sizes':[na,nb],'raw_equal':ha==hb,'changed_sections':sections,'build_id_offset_size':[ba,bb],'rodata_header_offsets':[ra,rb],'all_PT_LOAD':loads,'normalized_full_sha256':norm,'complete_wild_header_equivalence_only':bool(ha!=hb and permit and hit_header and norm[0]==norm[1] and all(p['masked_a']==p['masked_b'] for p in loads))}
if __name__=='__main__':print(json.dumps(compare(*sys.argv[1:]),sort_keys=True,indent=2))
