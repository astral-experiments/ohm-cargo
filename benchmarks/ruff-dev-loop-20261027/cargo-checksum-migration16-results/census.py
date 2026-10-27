"""Independently decode old/new Cargo records and authenticate the exact optional OBS1 trailer."""
from pathlib import Path
import collections,ctypes,hashlib,json,os,struct,sys
def census(state,helper):
    fn=ctypes.CDLL(str(Path(helper).resolve())).cargo_depinfo_b3;fn.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p)
    def parse(b):
        pos=0
        def take(n):
            nonlocal pos
            assert 0<=n<=len(b)-pos
            v=b[pos:pos+n];pos+=n;return v
        def u8():return take(1)[0]
        def u32():return int.from_bytes(take(4),'little')
        def s():return take(u32())
        assert take(5)==b'\x01\0\0\0\xff';v=u8();assert v in (2,3);n=u32();files=[]
        for _ in range(n):
            ty=u8();assert ty in (0,1);name=s();ch=u8();assert ch in (0,1)
            if ch:take(8);checksum=s();assert checksum
            files.append((name,ch,ty))
        ne=u32()
        for _ in range(ne):
            s();vv=u8();assert vv in (0,1)
            if vv:s()
        nc=sum(r[1] for r in files);sps=sum(b' ' in r[0]for r in files);abs_=sum(os.path.isabs(r[0]) for r in files);obs=False;complete=None;auth=False
        if pos<len(b):
            obs=True;assert take(4)==b'OBS1';i=u32();assert 0<=i<len(files) and files[i][0].split(b'/')[-1]==b'ohm-foreign-span-bytes' and not files[i][1]
            co=u8();assert co in (0,1);complete=bool(co);body=b[:pos];want=take(32);out=ctypes.create_string_buffer(32);fn(body,len(body),out);assert out.raw==want;auth=True
        assert pos==len(b)
        cl=('obs1-pending' if not complete else ('obs1-spaced-pending-on-v3-reader'if v==2 and sps else 'obs1-safe-complete')) if obs else ('legacy-ordinary-checksum-retrain' if v==2 and nc else ('current-ordinary-checksum' if nc else 'ordinary-mtime'))
        return {'class':cl,'version':v,'total_files':n,'checksum_files':nc,'mtime_files':n-nc,'space_names':sps,'absolute_names':abs_,'env_entries':ne,'obs1':obs,'complete':complete,'auth':auth}
    rows={}
    for n in ('target','shared'):
        based=state/n
        for cur,dirs,files in os.walk(based):
            dirs[:]=[v for v in dirs if v not in ('incremental','deps','examples','native')]
            for file in files:
                if not file.startswith('dep-'):continue
                f=Path(cur)/file
                if f.parent.name!='fingerprint' and '.fingerprint'not in f.parts:continue
                b=f.read_bytes(); key=n+'/'+str(f.relative_to(based));digest=hashlib.sha256(b).hexdigest()
                # Retain malformed or unfamiliar records in the denominator rather than dropping them.
                if not b.startswith(b'\x01\0\0\0\xff'):
                    rows[key]={'class':'unrecognized','bytes':len(b),'sha256':digest};continue
                data=parse(b);data['bytes']=len(b);data['sha256']=digest;rows[key]=data
    counts=dict(collections.Counter(v['class']for v in rows.values()))
    assert rows
    return {'counts':counts,'rows':rows}
if __name__=='__main__':
    st,helper,out=map(Path,sys.argv[1:4]);r=census(st,helper);out.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n');print(r['counts'])
