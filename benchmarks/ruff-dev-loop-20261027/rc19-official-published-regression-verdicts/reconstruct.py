"""Reopen the downloaded Linux distribution, installed binaries and completed verdicts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

TAG = "ohm-1.99.0-19"
TRIPLE = "x86_64-unknown-linux-gnu"
ARCHIVE = TAG + "-" + TRIPLE + ".tar.gz"
ARCHIVE_SHA = "ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812"
COMPONENT_ROOT = "rust-1.99.0-dev-" + TRIPLE
IMAGES = {"cargo":"bin/cargo","rustc":"bin/rustc","rustdoc":"bin/rustdoc",
          "driver":"lib/librustc_driver-b03bf00bec23bb9a.so",
          "wild":"lib/rustlib/"+TRIPLE+"/bin/wild-ld/ld.bfd"}
ORDER = ("provider-first","provider-late")
PHASES = ("original","original-repeat","edited","edited-repeat","edited-clean","restore","restore-repeat")
ROOT_TOKEN = b"@RELEASE_REPLAY@"
FIXED_MANIFEST = "54f63217c50e2c77349e932aff33e7c0f620dedf31d2b386e6eaf12aa13d41ef"

def data(d):
    return (json.dumps(d,sort_keys=True,indent=1)+"\n").encode()
def h(b):
    return hashlib.sha256(b).hexdigest()
def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def obj(p):
    return {"sha256":digest(p),"bytes":p.stat().st_size}
def read(p):
    return json.loads(p.read_bytes())
def inventory(directory):
    return {str(q.relative_to(directory)):obj(q) for q in sorted(directory.rglob("*")) if q.is_file()}
def manifest(p):
    m={}
    for line in p.read_text().splitlines():
        value,name=line.split(maxsplit=1)
        assert name not in m and Path(name).as_posix()==name and not Path(name).is_absolute() and ".." not in Path(name).parts
        assert re.fullmatch("[a-f0-9]{64}",value)
        m[name]=value
    return m
def normalize(raw,root):
    original=str(root).encode()
    assert ROOT_TOKEN not in raw
    normalized=raw.replace(original,ROOT_TOKEN)
    assert normalized.replace(ROOT_TOKEN,original)==raw
    return normalized

def release(root):
    dest=root/"sdk"
    meta=read(root/"release.json"); assets={a["name"]:{"sha256":a["digest"].removeprefix("sha256:"),"bytes":a["size"]} for a in meta["releaseAssets"]["nodes"]}
    assert meta["isDraft"] is False and meta["tagName"]==TAG and len(assets)==len(meta["releaseAssets"]["nodes"])
    verified=read(root/"installed.json")
    checks=manifest(root/"SHA256SUMS")
    archive=root/ARCHIVE
    assert all(assets[n]["sha256"]==v for n,v in checks.items())
    assert assets[ARCHIVE]==obj(archive) and assets[ARCHIVE]["sha256"]==ARCHIVE_SHA==verified["archive"]
    assert manifest(root/(ARCHIVE+".sha256"))=={ARCHIVE:ARCHIVE_SHA}
    for n in ("SHA256SUMS",ARCHIVE+".sha256",TAG+".json"):
        assert obj(root/n)==assets[n]
    assert verified["release"]==TAG
    names={COMPONENT_ROOT+"/"+("cargo" if role=="cargo" else "rustc")+"/"+path:role for role,path in IMAGES.items()}
    extracted={}
    with tarfile.open(archive,"r|gz") as tar:
        for member in tar:
            name=member.name.removeprefix("./")
            role=names.get(name)
            if role is None:continue
            assert role not in extracted and member.isfile()
            fd=tar.extractfile(member)
            assert fd and fd.read(4)==b"\x7fELF"
            dig=hashlib.sha256(b"\x7fELF")
            while blob:=fd.read(1<<20):dig.update(blob)
            actual=dig.hexdigest()
            image=dest/IMAGES[role]
            assert actual==verified["images"][role]==digest(image)==digest(root/"unpacked"/name)
            assert member.size==image.stat().st_size
            extracted[role]={"sha256":actual,"bytes":member.size,"archive_member":name}
    assert set(extracted)==set(IMAGES)
    result={"tag":TAG,"platform":TRIPLE,"published_at":meta["publishedAt"],"images":extracted,
            "versions":verified["versions"],"assets":assets,"archive_sidecar":checks[ARCHIVE],
            "manifest":read(root/(TAG+".json")),"raw":{k:obj(root/k) for k in ("installed.json","release.json","install.log","SHA256SUMS",TAG+".json",ARCHIVE+".sha256")}}
    return result

def state(base):
    result={}
    for store_name,(target,shared) in {"restored":("target","shared"),"edited-clean":("cold-target","cold-shared")}.items():
        store={}
        for c in ("provider","reader"):
            short,=[f for loc in (target,shared) for f in (base/loc).rglob("fingerprint/lib-"+c)]
            assert re.fullmatch(b"[0-9a-f]{16}",short.read_bytes())
            public=short.with_name(short.name+".public-api-hash");body=read(public)
            assert body["version"]==1 and re.fullmatch("[a-f0-9]{32}",body["value"])
            rm,=(short.parent.parent/"out").glob("lib"+c+"-*.rmeta")
            store[c]={"short":{**obj(short),"value":short.read_text()},"public_api":{**obj(public),"value":body["value"]},"rmeta":obj(rm)}
        result[store_name]=store
    return result

def checking(root,ref,stream):
    out={}
    input_orig=inventory(ref/"fixture")
    for order in ORDER:
        base=root/order
        assert (base/"rustup/toolchains/ohm").samefile(root/"sdk")
        assert inventory(base/"src")==input_orig
        worker=(root/(order+".stdout")).read_bytes()
        assert (root/(order+".stderr")).read_bytes()==b""
        phases={}
        for phase in PHASES:
            group={}
            for ext in ("stdout","stderr"):
                f=base/(phase+"."+ext);p=f.read_bytes();portable=normalize(p,root)
                stream[order+"/"+phase+"."+ext]=portable.decode()
                group[ext]={**obj(f),"portable_sha256":h(portable),"local_root_replacements":portable.count(ROOT_TOKEN)}
            rows=list(map(json.loads,(base/(phase+".stdout")).read_bytes().splitlines()))
            arts={r["target"]["name"]:r["fresh"] for r in rows if r["reason"]=="compiler-artifact"}
            errors=[]
            for r in rows:
                if r["reason"]=="compiler-message" and r["message"]["level"]=="error":
                    msg=r["message"];errors.append({"target":r["target"]["name"],"code":msg["code"]["code"],
                        "summary":msg["message"],"rendered_sha256":h(msg["rendered"].encode()),
                        "primary":[[s["file_name"],s["line_start"],s["column_start"]] for s in msg["spans"] if s["is_primary"]],
                        "notes":[c["message"] for c in msg["children"] if c["level"]=="note"]})
            rc=0 if rows[-1]=={"reason":"build-finished","success":True} else 101
            assert rows[-1]=={"reason":"build-finished","success":rc==0}
            line=f"{phase} {rc} {[(e['target'],e['code']) for e in errors]} fresh {sorted(k for k,v in arts.items() if v)}"
            assert worker.decode().splitlines().count(line)==1
            phases[phase]={"exit":rc,"artifacts":arts,"errors":errors,"streams":group}
        ctl=base/"control.tsv";events=[]
        for line in ctl.read_text().splitlines():
            kind,pid,tid,who,restore,old,new,name=line.split("\t")
            assert int(pid)>0 and int(tid)>0
            crate={"1":"provider","2":"reader"}[who]
            path=Path(name)
            assert path.is_relative_to(base) and path.suffix==".rmeta" and path.name.startswith("lib"+crate+"-")
            events.append({"event":kind,"crate":crate,"restore":int(restore),"observed_ns":int(old),"requested_ns":int(new)})
        out[order]={"phases":phases,"events":events,"interposer":obj(base/"commit-order.so"),"sources":input_orig,
                    "state":state(base),"control":obj(ctl),"worker_stdout":worker.decode(),"worker_stdout_sha256":h(worker),
                    "worker_stderr":obj(root/(order+".stderr"))}
    return out

def reverted(root,ref):
    case=root/"first-revert";subject=read(case/"result.json")
    assert (root/"rustup/toolchains/ohm").samefile(root/"sdk")
    inp=inventory(ref/"fixture");wp=inventory(ref/"wrapper")
    for n,w in inp.items():assert obj(case/"app"/n)==w
    for n,w in wp.items():assert obj(case/"wrapper"/n)==w
    records={}
    for phase,r in subject["phases"].items():
        p=case/phase
        for n,v in r["files"].items():assert digest(p/n)==v
        stderr=(p/"stderr").read_bytes()
        assert re.findall(rb"error\[(E[0-9]+)\]",stderr)==[e.encode() for e in r["errors"]]
        native=[]
        for line in (p/"exec.log").read_bytes().splitlines():
            m=re.search(rb'execve\("([^"]+)"',line)
            if not m or not line.rstrip().endswith(b"= 0"):continue
            program=Path(m[1].decode())
            if program.name!="rustc":continue
            name=re.search(rb'"--crate-name", "(app|dep)"',line)
            if not name:continue
            assert program.samefile(root/"sdk/bin/rustc")
            kind=re.search(rb'"--crate-type", "([^"]+)"',line)
            assert kind
            native.append({"crate":name[1].decode(),"crate_type":kind[1].decode(),"literal_sha256":h(line+b"\n")})
        assert [[n["crate"],n["crate_type"]] for n in native]==r["rustcs"]
        records[phase]={"native":native,**r}
    elfs={"program":case/"app/target/debug/app","wrapper":case/"wrapper/target/debug/conditional-metadata-pipeline-wrapper"}
    for elf in elfs.values():
        with elf.open("rb") as f:assert f.read(4)==b"\x7fELF"
    assert all((case/p/"stdout").read_bytes()==b"1\n" for p in ("prime-program","final-program"))
    assert (case/"app/parent-started-early").read_bytes()==b"ready" and (case/"app/dependency-failed").read_bytes()==b"failed" and not (case/"app/parent-timed-out").exists()
    return {"result":subject,"result_digest":obj(case/"result.json"),"phases":records,"source":inp,"wrapper_source":wp,
            "elfs":{k:obj(p) for k,p in elfs.items()},"retained_markers":{"early":"ready","failed":"failed"},"first_stdout":(case/"prime-program/stdout").read_text(),
            "final_stdout":(case/"final-program/stdout").read_text(),"worker_stdout":(root/"first-revert.stdout").read_text(),
            "worker_stderr":obj(root/"first-revert.stderr")}

def run(args):
    root=args.official.resolve();trait=args.trait;revert=args.revert;fixed=args.fixed
    for p in (trait,revert,fixed):
        orig=manifest(p/"SHA256SUMS")
        assert all(obj(p/n)["sha256"]==v for n,v in orig.items())
    assert digest(fixed/"SHA256SUMS")==FIXED_MANIFEST
    captures={}
    out={"release":release(root),"check":checking(root,trait,captures),"revert":reverted(root,revert)}
    files={"release/SHA256SUMS.asset":(root/"SHA256SUMS").read_bytes(),"release/"+TAG+".json":(root/(TAG+".json")).read_bytes(),
        "release/"+ARCHIVE+".sha256":(root/(ARCHIVE+".sha256")).read_bytes(),
        "cargo-streams.json.gz":gzip.compress(data(captures),mtime=0),
        "fixed-qa/SHA256SUMS.reference":(fixed/"SHA256SUMS").read_bytes(),"fixed-qa/outcomes.json.gz":gzip.compress((fixed/"outcomes.json").read_bytes(),mtime=0),
        "fixed-qa/raw-ledger.json":(fixed/"raw-ledger.json").read_bytes()}
    out["source_packets"]={"trait":digest(trait/"SHA256SUMS"),"revert":digest(revert/"SHA256SUMS"),"fixed":FIXED_MANIFEST}
    for prefix,case,folders,additional in (("trait",trait,("fixture",),("commit-order.c",)),("revert",revert,("fixture","wrapper"),())):
        files[prefix+"/reproduce.py"]=(case/"reproduce.py").read_bytes()
        files[prefix+"/SHA256SUMS.reference"]=(case/"SHA256SUMS").read_bytes()
        for name in additional:files[prefix+"/"+name]=(case/name).read_bytes()
        for dirname in folders:
            for f in sorted((case/dirname).rglob("*")):
                if f.is_file():files[prefix+"/"+str(f.relative_to(case))]=f.read_bytes()
    refio={}
    for phase in out["revert"]["phases"]:
        items={}
        for name in ("stdout","stderr"):
            f=root/"first-revert"/phase/name
            original=f.read_bytes();portable=normalize(original,root)
            items[name]={"text":portable.decode(),"raw_sha256":h(original),"portable_sha256":h(portable),
                         "bytes":len(original),"local_root_replacements":portable.count(ROOT_TOKEN)}
        refio[phase]=items
    files["revert-streams.json.gz"]=gzip.compress(data(refio),mtime=0)
    files["official.json"]=data(out)
    for name,blob in files.items():
        path=args.destination/name
        if args.compare:assert path.read_bytes()==blob,name
        elif path.exists():assert path.read_bytes()==blob,name
        else:
            path.parent.mkdir(exist_ok=True,parents=True)
            path.write_bytes(blob)
    print("Reopened GitHub asset, five archived/installed ELFs, 14 real checks, synchronized revert, fixture sources and fixed production QA.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("official","trait","revert","fixed","destination"):ap.add_argument(name,type=Path)
    ap.add_argument("--compare",action="store_true")
    run(ap.parse_args())
