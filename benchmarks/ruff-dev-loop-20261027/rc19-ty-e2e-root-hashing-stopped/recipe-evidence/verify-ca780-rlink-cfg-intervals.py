"""Validate the source spans and every surrounding byte from CrateInfo through EncodedMetadata."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib

def sha(b): return hashlib.sha256(b).hexdigest()
def leb(n):
    b=bytearray()
    while n>=128:
        b.append(128+(n&127));n>>=7
    return bytes(b)+bytes([n])

spec=importlib.util.spec_from_file_location("fields",Path(__file__).with_name("decode-ca780-rlink-native-cfg.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
commit="ca780121cea38bb9b0538d020d4bcce76ca30cbc"

def suffix(raw,nonce):
    good=[]
    for pos in range(len(raw)-1500,len(raw)-13):
        d=m.Decoder(raw);d.pos=pos
        try:
            outdir=d.string()
            assert outdir.startswith("/") and outdir.endswith("/out")
            crate=d.string();stem=d.string()
            assert crate==stem=="e2e-8945421a8b988468"
            assert d.tag(2)==0 and d.tag(2)==1 and d.string()==f"{outdir}/{stem}.rlink-objects"
            assert d.tag(2)==1 and d.string()==nonce and d.tag(2)==0 and d.tag(2)==0
            assert d.seq(lambda:(d.tag(32),d.tag(2)))==[(2,0),(3,0)]
            assert d.take(13)==b"rust-end-file" and d.pos==len(raw)
        except (AssertionError,UnicodeDecodeError,ValueError):
            continue
        good.append(pos)
    assert len(good)==1,good
    return good[0]

def origins(rust,crate):
    def git(*args):
        return subprocess.check_output(["git","-C",str(rust),*args])
    registry,=[r for r in tomllib.loads(git("show",commit+":library/Cargo.lock").decode())["package"] if r["name"]=="libc"]
    assert registry["version"]=="0.2.189" and sha(crate.read_bytes())==registry["checksum"]
    with tarfile.open(crate,mode="r:gz") as t:
        libc=t.extractfile("libc-0.2.189/src/unix/mod.rs").read()
    unwind=git("show",commit+":library/unwind/src/lib.rs")
    assert re.fullmatch(rb"[a-f0-9]{40}\n",git("rev-parse",commit+":library/unwind/src/lib.rs"))
    # Use the GNU std link attributes in their original source order.
    def clauses(source,first,last):
        lines=source.splitlines(keepends=True)
        start=sum(map(len,lines[:first-1]));end=sum(map(len,lines[:last]))
        records=[]
        for hit in re.finditer(rb"#\[link\((.*?)\)\]",source[start:end],re.S):
            text=hit.group(1)
            name=re.search(rb'name\s*=\s*"([^"]+)"',text)
            cfg=re.search(rb'cfg\((not\()?(target_feature = "crt-static")',text)
            assert name and cfg
            body=start+hit.start(1)+cfg.start(2)
            records.append((name[1].decode(),body,body+len(cfg[2]),bool(cfg[1])))
        return records
    src={"libc":libc,"unwind":unwind}
    pos={"libc":clauses(libc,452,511),"unwind":clauses(unwind,148,148)}
    assert list(map(len,pos.values()))==[15,1]
    return src,pos

def attest(raw,receipt,src,pos):
    d=m.Decoder(raw).run()
    sources={int(k):v[0] for k,v in d["libraries"].items()}
    assert sources=={5:"libc",7:"unwind",146:"psm"}
    assert d["indexed_crates"]==233 and len(d["spans"])==23
    nonce,={entry[1] for entry in receipt["authenticated_name_fields"]}
    end=suffix(raw,nonce)
    start=d["crate_info_start"]
    normalized=bytearray();at=start;inverse=[];bases={}
    for span in d["spans"]:
        context=span["context"];crate=sources[context[0]];lib,lo,hi,neg=pos[crate][context[1]]
        assert lib==context[2] and context[-1] in (["target_feature","crt-static"],[4,["target_feature","crt-static"]])
        if context[-2]==2:
            assert neg;lo-=1;hi+=1
        else:
            assert context[-2]==4
        token=src[crate][lo:hi]
        assert token in (b'target_feature = "crt-static"',b'(target_feature = "crt-static")')
        base=span["lo"]-lo
        assert span["hi"]-hi==base and bases.setdefault(crate,base)==base
        a,b=span["offset"],span["end"]
        assert at<=a<b<=d["after_libraries"] and raw[a:b]==leb(span["lo"])+leb(span["hi"])
        normalized.extend(raw[at:a])
        l=len(normalized);normalized.extend(leb(lo)+leb(hi))
        inverse.append((l,len(normalized),raw[a:b]));at=b
    assert bases["unwind"]-bases["libc"]==90107
    normalized.extend(raw[at:end])
    reverse=bytearray(normalized)
    for first,last,value in reversed(inverse):
        reverse[first:last]=value
    assert bytes(reverse)==raw[start:end]
    return d,bytes(normalized),bases,end

def main(rawdir,rust,crate):
    src,pos=origins(rust,crate)
    lanes={}; exemplar=None
    for f in sorted(rawdir.glob("*.rlink")):
        raw=f.read_bytes()
        receipt=json.loads(f.with_suffix(".json").read_bytes())
        assert sha(raw)==receipt["raw_sha"]
        d,normalized,bases,end=attest(raw,receipt,src,pos)
        if exemplar is None:exemplar=normalized
        assert normalized==exemplar
        lanes[f.stem]={"raw":sha(raw),"region_start":d["crate_info_start"],"region_end":end,"relative_sha256":sha(normalized),"relative_size":len(normalized),"source_bases":bases}
    assert len(lanes)==8
    for a,b in [("warm-parent","warm-child"),("leaf-parent-original","leaf-child-original"),("leaf-parent-edited","leaf-child-edited"),("cold-parent","cold-child")]:
        assert lanes[a]["source_bases"]==lanes[b]["source_bases"]
    for crate_name in src:
        v=lambda name:lanes[name]["source_bases"][crate_name]
        assert v("leaf-parent-original")-v("leaf-parent-edited")==9 and v("warm-parent")-v("leaf-parent-original")==11090900
    f=rawdir/"leaf-parent-original.rlink";raw=f.read_bytes();rec=json.loads(f.with_suffix(".json").read_bytes())
    d,_canonical,_,end=attest(raw,rec,src,pos)
    def bad(label,body):
        try:
            result=attest(body,rec,src,pos)
            if result[1]==exemplar:raise RuntimeError("accepted altered native recipe: "+label)
        except (AssertionError,UnicodeDecodeError,ValueError):
            pass
        return label
    def flipped(i):
        b=bytearray(raw);b[i]^=1;return bytes(b)
    i=raw.index(b"crt-static",d["libraries_start"],d["after_libraries"])
    symbol=raw.index(b"rust_metadata_e2e_",d["after_libraries"],end)
    worst=d["spans"][0]
    negatives=[bad("first actual cfg endpoint",flipped(worst["offset"])),
               bad("real cfg semantic token",flipped(i)),bad("opaque metadata symbol byte",flipped(symbol+19)),
               bad("encoded OutputFilenames invocation token",flipped(len(raw)-28)),bad("serialized end marker",raw[:-1])]
    print(json.dumps(dict(compiler=commit,cfg_spans_per_recipe=23,native_library_entries=17,negative_controls=negatives,
                          source_sha256={k:sha(v)for k,v in src.items()},lanes=lanes),indent=2,sort_keys=True))

if __name__=="__main__":
    main(*map(Path,sys.argv[1:]))
