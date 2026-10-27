"""Join real Wild selected-member ranges to physical Rust archive members and ELF sections."""
from collections import Counter
from pathlib import Path
import hashlib,json,re,struct

p=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def stable(n):
    return re.sub(r"\.[0-9a-z]{7}\.rcgu\.o$",".rcgu.o",n)
def archive(b):
    assert b.startswith(b"!<arch>\n")
    i=8;names=b"";rows={};idx={};table=None
    while i<len(b):
        head=i;h=b[i:i+60];assert h[-2:]==b"`\n";n=h[:16].rstrip();l=int(h[48:58])
        s=head+60;e=s+l;v=b[s:e];assert len(v)==l;i=e+(e%2)
        if n==b"//":names=v;continue
        if n==b"/":table=v;continue
        n=names[int(n[1:]):].split(b"/\n")[0] if n.startswith(b"/") else n.rstrip(b"/")
        n=n.decode();k=stable(n);assert k not in rows
        idx[head]=k;rows[k]=(n,s,e,v)
    assert i==len(b) and table
    count=int.from_bytes(table[:4],"big");syms=table[4+count*4:].split(b"\0")[:count]
    assert len(syms)==count;index=[(sym.decode(),idx[struct.unpack_from(">I",table,4+4*j)[0]]) for j,sym in enumerate(syms)]
    return rows,index
def elf(b):
    assert b[:7]==b"\x7fELF\x02\x01\x01"
    off,=struct.unpack_from("<Q",b,40);size,num,names=struct.unpack_from("<HHH",b,58);assert size==64
    heads=[struct.unpack_from("<IIQQQQIIQQ",b,off+i*size) for i in range(num)]
    string=lambda o:b[o:b.index(b"\0",o)].decode()
    getname=lambda h:string(heads[names][4]+h[0])
    seen=Counter();secs={};symt=[];sch={}
    for i,h in enumerate(heads):
        n=getname(h);key=f"{n}#{seen[n]}";seen[n]+=1;idx=i
        data=b[h[4]:h[4]+h[5]] if h[1]!=8 else b""
        assert h[1]==8 or len(data)==h[5]
        sig=(h[1],h[2],h[5],h[6],h[7],h[8],h[9])
        secs[key]=(idx,n,sig,sha(data));sch[i]=key
    for i,h in enumerate(heads):
        if h[1]!=2:continue
        assert h[9]==24;st=heads[h[6]][4]
        for j in range(h[5]//24):
            name,info,other,shndx,value,sz=struct.unpack_from("<IBBHQQ",b,h[4]+24*j)
            if info>>4:
                symt.append((string(name+st),info,other,sch.get(shndx,shndx),value,sz))
    return secs,symt
def decode_layout(b):
    i=0
    def integer():
        nonlocal i
        v=sh=0
        while True:
            x=b[i];i+=1;v|=(x&127)<<sh
            if x<128:return v
            sh+=7;assert sh<70
    def raw():
        nonlocal i
        n=integer();v=b[i:i+n];i+=n;assert len(v)==n;return v
    def opt():
        v=integer();assert v in (0,1);return v
    files=[]
    for f in range(integer()):
        path=raw().decode();ent=(integer(),integer(),raw().decode()) if opt() else None
        secs=[(integer(),integer()) if opt() else None for _ in range(integer())]
        files.append((path,ent,secs,opt()))
    metrics=integer() if i<len(b) else None
    assert i==len(b),(i,len(b));return files,metrics
def digest_rows(a):return sha(json.dumps(a,separators=(",",":")).encode())
def main():
    allrows={};layout={};byf={};summary={};detail={}
    for s in ("seed","reversed","restored"):
        lib=(p/"products"/s/"trivia.rlib").read_bytes();m,syms=archive(lib);allrows[s]=(m,syms)
        if s=="seed":continue
        layout[s]={};byf[s]={}
        for f in (p/"products"/s).glob("*.layout"):
            files,metrics=decode_layout(f.read_bytes());used={}
            for path,ent,sections,tmp in files:
                if not Path(path).name.startswith("libruff_python_trivia-"):continue
                assert ent and not tmp
                start,end,n=ent;k=stable(n);nm,a,z,actual=m[k]
                assert (a,z,nm)==(start,end,n)
                sec,_=elf(actual);assert len(sections)==len(sec),(n,len(sections),len(sec))
                used[k]={key:r for key,(i,_,_,_) in sec.items() if (r:=sections[i]) is not None}
            layout[s][f.stem]=used
            byf[s][f.stem]={"layout_sha256":sha(f.read_bytes()),"all_selected_objects":len(files),"trivia_selected":len(used),"trivia_direct_alloc_sections":sum(len(v) for v in used.values()),"thunks":metrics}
    ma,syma=allrows["reversed"];mb,symb=allrows["restored"]
    changed=sorted(k for k in ma.keys()&mb.keys() if ma[k][3]!=mb[k][3] and k.endswith(".o"))
    for name in sorted(set(ma)^set(mb)):
        if name.endswith(".o"):changed.append(name)
    summary.update(members={k:len(v[0]) for k,v in allrows.items()},added=sorted(mb.keys()-ma.keys()),removed=sorted(ma.keys()-mb.keys()),
        changed_objects=changed,unchanged_object_count=len({k for k in ma.keys()&mb.keys() if k.endswith(".o") and ma[k][3]==mb[k][3]}),
        seed_restored_equal_objects=sorted(k for k in mb if k.endswith(".o") and k in allrows["seed"][0] and allrows["seed"][0][k][3]==mb[k][3]),
        archive_index={s:{"count":len(z[1]),"sha":digest_rows(z[1])} for s,z in allrows.items()},
        same_ordered_index=syma==symb,changed_index_symbols={"only_reversed":sorted((Counter(syma)-Counter(symb)).elements()),"only_restored":sorted((Counter(symb)-Counter(syma)).elements())},layout=byf)
    for name in changed:
        sa,y=elf(ma[name][3]) if name in ma else ({},[]); sb,z=elf(mb[name][3]) if name in mb else ({},[])
        diffs={}
        for k in sorted(set(sa)|set(sb)):
            a=sa.get(k);b=sb.get(k)
            if a and b and a[2:]==b[2:]:continue
            diffs[k]={"reversed":a,"restored":b,"markers":{s:{f:layout[s][f].get(name,{}).get(k) for f in layout[s]} for s in ("reversed","restored")}}
        detail[name]={"selected":{s:{f:name in layout[s][f] for f in layout[s]} for s in ("reversed","restored")},"sections_changed":diffs,
            "symbols":{"only_reversed":sorted((Counter(y)-Counter(z)).elements(),key=str),"only_restored":sorted((Counter(z)-Counter(y)).elements(),key=str)}}
    whole={"summary":summary,"objects":detail,"selected":layout}
    (p/"audit.json").write_text(json.dumps(whole,indent=2,sort_keys=True)+"\n")
    subset={k:v for k,v in summary.items() if k!="seed_restored_equal_objects"}
    print(json.dumps(subset,indent=2)[:6500]);print("restoration object equality",len(summary["seed_restored_equal_objects"]))
    for n,row in detail.items():
        dd=row["sections_changed"]
        print(n.rsplit(".",2)[0][-25:],"selected",row["selected"]["reversed"],"changes",len(dd),"retained",sum(any(l for v in x["markers"].values() for l in v.values()) for x in dd.values()),"symbol deltas",*[len(v) for v in row["symbols"].values()])
if __name__=="__main__":main()
