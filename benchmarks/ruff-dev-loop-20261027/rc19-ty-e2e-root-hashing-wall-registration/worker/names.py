"""Separate live full-compiler root objects from every literal dependency input."""
import ast
import os
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

ROLE = prior.module("existing_args",M/"ops/native-order-args-v4.py")
ROOT_OBJECT = re.compile(r"("+re.escape(NAME)+r"\.[a-z0-9]+)\.([a-z0-9]{7})(\.rcgu\.o)")

def kernel_rows(d):
    config=get(M/"qualification/native-tools.json")["images"]
    identities={(Path(x["path"]).stat().st_dev,Path(x["path"]).stat().st_ino):k for k,x in config.items()}
    rows=[]
    for f in sorted(d.glob("exec.*")):
        for line in f.read_text(errors="replace").splitlines():
            hit=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',line)
            if not hit:
                continue
            exe=Path(ast.literal_eval(hit[1]));s=exe.stat();role=identities.get((s.st_dev,s.st_ino));a=ast.literal_eval(hit[2])
            if not role:
                continue
            output=a[a.index("-o")+1] if "-o" in a else None
            target=None
            if role=="rustc" and "--crate-name" in a:
                target=a[a.index("--crate-name")+1]
                role="rustc-link-only" if "-Zlink-only" in a or "link-only" in a else "rustc-full"
            rows.append({"role":role,"target":target,"argv":a,"out":output,"pid":int(f.suffix[1:]),"ino":s.st_ino,"dev":s.st_dev,
                         "argv_sha256":hashlib.sha256(b"\0".join(map(os.fsencode,a))+b"\0").hexdigest()})
    return rows

def root_name(path):
    p=Path(path)
    if p.parent!=E2E.with_suffix(".rlink-objects"):
        return None
    m=ROOT_OBJECT.fullmatch(p.name)
    assert m,p
    return str(p.with_name(m[1]+".<current-root-name>"+m[3])),m[2]

def ordered(rows,side,with_input_bytes):
    real=[r for r in rows if r.get("target")=="e2e" and r["role"]=="rustc-full"]
    assert len(real)==1
    actual=real[0]["argv"]
    assert not any(a in ("-Zlink-only","link-only") for a in actual)
    full=hashlib.sha256(b"\0".join(map(os.fsencode,actual))+b"\0").hexdigest()
    ext=[]
    for i,x in enumerate(actual):
        if x!="--extern":
            continue
        name,sep,path=actual[i+1].partition("=")
        assert sep and Path(path).is_absolute()
        ext.append([name,path,datafile(path)])
    roles={"gcc","collect2","stock-wild"}
    chosen=[dict(r) for r in rows if r["role"] in roles and r["out"]==str(E2E)]
    assert sorted(r["role"] for r in chosen)==sorted(roles)
    original={r["role"]:r["argv_sha256"] for r in chosen}
    canon=[]
    regular=[]
    native_sha={name:v for name,v in side["objects"].items()}
    for r in chosen:
        seen=set();nonces=set();renamed=[]
        for x in r["argv"]:
            a=root_name(x)
            if a is None:
                renamed.append(x)
            else:
                seen.add(Path(x).name);nonces.add(a[1]);renamed.append(a[0])
        assert seen==native_sha.keys() and len(nonces)==1
        if r["role"]=="stock-wild" and with_input_bytes:
            for item in r["direct_file_operands"]:
                at=item["index"];path=item["path"];assert r["argv"][at]==path
                f=root_name(path)
                if f is not None:
                    small=native_sha[Path(path).name]
                    assert (item["size"],item["sha256"])==(small["bytes"],small["sha256"])
                    regular.append({"index":at,"role":"own","path":f[0],"size":item["size"],"sha256":item["sha256"]})
                else:
                    assert Path(path).is_absolute()
                    regular.append({"index":at,"role":"absolute","path":path,"size":item["size"],"sha256":item["sha256"]})
            assert len([q for q in regular if q["role"]=="own"])==len(seen)
        if r["role"]=="stock-wild" and not with_input_bytes:
            r["temporary"]={"raw_dylibs":[],"resolution_len":0}
        r["argv"]=renamed
        canon.append(r)
    args=ROLE.fingerprints(canon,LIVE/"target",Path("/tmp"))
    if not with_input_bytes:
        for a in args:a.pop("temporary_contents",None)
    return {"full_argv":full,"externs":ext,"argv_roles":args,"ordered_current_files":regular},original

def own_recipe(side):
    path=E2E.with_suffix(".rlink")
    buf=bytearray(path.read_bytes())
    assert hashlib.sha256(buf).hexdigest()==side["recipe"]["sha256"] and buf.startswith(b"rustlink")
    fields=[]
    for name, row in side["objects"].items():
        n=name.encode();indices=[m.start() for m in re.finditer(re.escape(n),buf)]
        assert len(indices)==1,(name,indices)
        m=ROOT_OBJECT.fullmatch(name);i=indices[0]+m.start(2);before=bytes(buf[i:i+7])
        assert before==m[2].encode()
        fields.append([i,m[2],name,row["bytes"],row["sha256"]])
        buf[i:i+7]=b"NoncE00"
    assert len(fields)==len({f[0] for f in fields})==139 and len({x[1] for x in fields})==1
    return {"source_sha256":side["recipe"]["sha256"],"bytes":len(buf),"authentic_object_name_fields":sorted(fields),
            "exact_except_verified_names":hashlib.sha256(buf).hexdigest(),"objects":sorted([n[:m.start(2)]+".ROOT."+n[m.end(2):],v["bytes"],v["sha256"]] for n,v in side["objects"].items() if (m:=ROOT_OBJECT.fullmatch(n)))}
