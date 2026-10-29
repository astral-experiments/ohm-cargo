"""Run coherent public Rust consumers and the actual test bodies outside the measured command."""
import mmap
import os
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

def parse_source(mode):
    return (DESIGN/(mode+".rs")).read_bytes().split(b'let foo_content = "\\\n',1)[1].split(b'";',1)[0]

def runtime(d,mode,env,caller_ref,full):
    result={}
    pkg=ROOT/"crates/ty_server"
    case_env={**env,"CARGO_MANIFEST_DIR":str(pkg),"CARGO_MANIFEST_PATH":str(pkg/"Cargo.toml")}
    process=prior.A.process
    names=process(d,"inventory",[E2E,"--list"],pkg,case_env)
    actual=(d/"inventory.stdout").read_bytes()
    assert names["status"]==0 and actual==(M/"gold/e2e-list.txt").read_bytes() and sum(x.endswith(b": test") for x in actual.splitlines())==200
    result["list"]=names
    for i,case in enumerate(SCHEMA["cases"]):
        record=process(d,"test-"+str(i),[E2E,"--exact",case],pkg,case_env)
        lines=(d/("test-"+str(i)+".stdout")).read_bytes().splitlines()
        assert record["status"]==0 and any(line==("test "+case+" ... ok").encode() for line in lines) and any(b"1 passed; 0 failed" in l for l in lines)
        result[case]=record
    fd=os.open(E2E,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME)
    with os.fdopen(fd,"rb") as src, mmap.mmap(src.fileno(),0,access=mmap.ACCESS_READ) as body:
        spots={m:body.find(parse_source(m)) for m in ("original","edited")}
    assert spots[mode]>=0 and spots["original" if mode=="edited" else "edited"]==-1,spots
    result["source_bytes"]=spots
    product=datafile(E2E);preserved=K/"bodies";preserved.mkdir(exist_ok=True)
    ref=M/"native-objects"/product["sha256"]
    if not ref.is_file():
        ref=K.parent/"ohm-rc20-ty-e2e-inlay-manifest-20261029-mount-v2/bodies"/product["sha256"]
    if ref.is_file():
        assert rawsha(ref)==product["sha256"]
        stored=ref
    else:
        stored=preserved/product["sha256"]
        if not stored.exists():
            new=stored.with_name(stored.name+".partial")
            assert not new.exists()
            shutil.copyfile(E2E,new);assert rawsha(new)==product["sha256"];new.chmod(0o444);new.rename(stored)
        assert rawsha(stored)==product["sha256"]
    result["retained_body"]={"sha256":product["sha256"],"file":str(stored)}
    arts=[x for x in caller_ref if x["reason"]=="compiler-artifact"]
    select=lambda name,sfx:next(Path(f) for a in arts if a["target"]["name"]==name and a["target"]["kind"]==["lib"] for f in a["filenames"] if f.endswith(sfx))
    search=sorted({str(Path(f).parent) for a in arts for f in a["filenames"] if Path(f).suffix in (".rlib",".rmeta",".so")})
    rg=["rustc","+ohm","--edition=2024"]
    flags=[s for p in search for s in ("-L","dependency="+p)]
    nw=[q for q in caller_ref if q["reason"]=="build-script-executed"]
    nl=[s for p in sorted({v for q in nw for v in q["linked_paths"]}) for s in ("-L",p)]
    parser=select("ruff_python_parser",".rlib"); meta=select("ruff_python_parser",".rmeta");db=select("ruff_db",".rmeta")
    client=rg+["--crate-name","root_source_coherent","--crate-type","rlib","--emit","metadata",str(M/"credential-reader-v1/natural.rs"),"--extern","ruff_python_parser="+str(meta),"--extern","ruff_db="+str(db),*flags,"-o",str(d/"coherent.rmeta")]
    v=process(d,"coherent-compile",client,ROOT,env)
    put(d/"coherent-argv.json",client)
    assert v["status"]==0 and (d/"coherent.rmeta").stat().st_size>0
    result["coherent"]={"status":v,"metadata":rawsha(d/"coherent.rmeta"),"parser":datafile(meta),"db":datafile(db)}
    if full:
        cmd=rg+[str(M/"gold/caller.rs"),"--extern","ruff_python_parser="+str(parser),*flags,*nl,"-o",str(d/"caller")]
        v=process(d,"caller-compile",cmd,ROOT,env); put(d/"caller-argv.json",cmd);assert v["status"]==0
        b=process(d,"caller-run",[d/"caller"],ROOT,env)
        assert b["status"]==0 and (d/"caller-run.stdout").read_text().strip()==get(REF)["product"]["caller"]
        result["native_parser"]={"compile":v,"run":b,"elf":rawsha(d/"caller")}
        assert result["native_parser"]["elf"]==get(DESIGN/"references.json")["native_parser_elf"]
        # Keep one physical external client per raw digest, with real original argv recorded.
        stash=K/"client-bodies";stash.mkdir(exist_ok=True);stored=stash/result["native_parser"]["elf"]
        if not stored.exists():
            os.link(d/"caller",stored)
        elif not (d/"caller").samefile(stored):
            assert datafile(stored)==datafile(d/"caller")
            os.link(stored,d/"caller-bytes-verified")
            os.replace(d/"caller-bytes-verified",d/"caller")
    return result
