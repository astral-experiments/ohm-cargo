"""Inspect the final compiler's serialized retained-definition hashes and actual physical spans."""
from pathlib import Path
from functools import lru_cache
import bisect,json,re,runpy,sys
E=Path(__file__).resolve().parent
W=Path('/home/dev-user/code/oss/ohm-rust-private-native-20261027')
Reader=runpy.run_path('/home/dev-user/.cache/ohm-ruff-cargo-link-skip-20261027/link-export-inventory.py')['Reader']
names=re.findall(r'^\s*(\w+): Table<',(W/'compiler/rustc_metadata/src/rmeta/mod.rs').read_text().split('\ndefine_tables! {',1)[1].split('\n}',1)[0],re.M)
kinds="CrateRoot Impl ForeignMod Use GlobalAsm TypeNs ValueNs MacroNs LifetimeNs Closure Ctor AnonConst OpaqueTy OpaqueLifetime AnonAssocTy SyntheticCoroutineBody NestedStatic".split()

def decode(p, source_fragment):
    m=p.read_bytes();r=Reader(m);assert r.u()==0; triple=r.text(); full=r.raw(32);name=r.symbol()
    assert r.raw(2)==bytes(2);suffix=r.text();crate=r.raw(8)
    if r.u(): r.u()
    r.u();r.u();r.raw(4)
    for _ in range(13):r.array()
    assert r.u()==1
    for _ in range(3):r.array()
    assert r.u()==0
    for _ in range(5):r.array()
    def lazy():
        delta=r.u(); r.prev=r.prev+delta if r.prev is not None else r.root-delta;assert 0<r.prev<=r.root;return r.prev
    def table(): return r.u(),r.u(),lazy()
    ts={label:table()for label in names}
    ctxt,expn,expn_hash=table(),table(),table();lazy();sf=table()
    for _ in range(2):r.array()
    flags=r.raw(9); assert max(flags)<4 and r.u()==1
    public,epublic=table(),table();global_fp=r.raw(16).hex()
    def entries(t):
        width,n,at=t;sparse=bool(width&128);width&=127;assert width<=17
        mapping=[True]*n
        if sparse:
            mapping=[]; prior=0
            for lo in range(0,n,64):
                bits=int.from_bytes(m[at:at+8],'little');count=int.from_bytes(m[at+8:at+12],'little');at+=12;assert count==prior;prior+=bits.bit_count()
                mapping.extend(bool(bits&(1<<bit))for bit in range(min(64,n-lo)))
        out=[]
        for b in mapping:
            if b:out.append(int.from_bytes(m[at:at+width],'little'));at+=width
            else:out.append(0)
        return out
    @lru_cache(None)
    def span(at):
        if not at:return None
        r.i=at;tag=r.raw(1)[0];k=tag&3;root=bool(tag&4);n=tag>>3
        if k==3:
            z=int.from_bytes(r.raw(n),'little');return span(at-z if root else z)
        ctx=0 if root else r.u()
        if k==2:return [k,ctx]
        lo=r.u();sz=r.u() if n==31 else n
        return [k,ctx,lo,sz,r.u(),r.u() if k==1 else 0]
    ids=entries(ts['def_path_hashes']); retained=entries(public);sps=entries(ts['def_span']);idents=entries(ts['def_ident_span']);keys=entries(ts['def_keys'])
    @lru_cache(None)
    def defname(i):
        r.i=keys[i];parent=r.u();assert parent in (0,1),(name,i,parent)
        par=r.u() if parent else None;tag=r.u();assert tag<len(kinds),(i,tag)
        arg=r.symbol() if tag in (5,6,7,8,13,14)else None;dis=r.u()
        s=str(arg)if arg is not None else '{'+kinds[tag]+'}';s+=('#'+str(dis))if dis else ''
        return (defname(par)+'::'+s)if par is not None else str(name)
    files=[]
    for at in entries(sf):
        r.i=at;ty,local=r.u(),r.u();assert(ty,local)==(0,0),(name,ty,local)
        path,wd,fullpath=r.text(),r.text(),r.text();r.u()
        def shash():
            k=r.u();assert r.u()==32;return r.raw(32).hex()
        sk=shash();ch=shash()if r.u()else None
        norm,orig,nl=r.u(),r.u(),r.u();w=r.u()if nl else 0;raw=r.raw(w*max(0,nl-1));starts=[0] if nl else []
        for lo in range(0,len(raw),w or 1):
            starts.append(starts[-1]+int.from_bytes(raw[lo:lo+w],'little'))
        files.append((path,norm,starts,sk))
    focus=[i for i,(v,*rest) in enumerate(files)if source_fragment in v]
    def physical(x):
        if not x:return None
        k=x[0]
        if k!=0 or x[4]not in focus:return x
        f=files[x[4]]
        def lc(o):
            l=bisect.bisect_right(f[2],o)-1;return[l+1,o-f[2][l]+1]
        return [*x,lc(x[2]),lc(x[2]+x[3])]
    facts={}; focused=[]
    for i,dp in enumerate(ids):
        fp=retained[i] if i<len(retained) else 0;h=fp.to_bytes(17,'little')[1:].hex() if fp else None
        ds=span(sps[i]) if i<len(sps) else None;di=span(idents[i]) if i<len(idents)else None
        if h:facts[f'{dp:016x}']=[h,defname(i)]
        if any(v and len(v)>3 and v[0]==0 and v[4]in focus for v in (ds,di)):
            focused.append({"id":i,"path_hash":f'{dp:016x}',"name":defname(i),"retained_scc":h,"def":physical(ds),"ident":physical(di)})
    return {"name":name,"private_public_raw":full.hex(),"global":global_fp,"files":[[i,files[i][0],files[i][1],files[i][3]]for i in focus],"source_table":[[i,f[0],f[1],f[3]]for i,f in enumerate(files)],"defs":facts,"focus":focused}

if __name__=="__main__":
    p=Path(sys.argv[1]);o=decode(p,sys.argv[2]);print(o['name'],o['global'],len(o['defs']),o['files'],len(o['focus']));print(o['focus'][:4])
    if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(o)+'\n')
