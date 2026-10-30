#!/usr/bin/env python3
"""Re-read one completed focused Cargo run, including each stock process trace and complete ELF body."""
import argparse
import ast
import collections
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

LIST = "76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52"
CASES=("inlay_hints::default_inlay_hints","notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell")
ORDER=("01-original-empty","02-unchanged","03-unchanged","04-edited","05-edited-repeat","06-invalid","07-recovery","08-restored","09-valid","10-forced-valid","11-malformed","12-remove","13-forced-malformed","14-final-remove","15-edited-independent-empty")
CARGOCMD=("test","--locked","--offline","--no-run","-j4","-p","ty_server","--test","e2e","--message-format=json")

def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def digest_bytes(b):
    return hashlib.sha256(b).hexdigest()

def readj(p):
    return json.loads(p.read_bytes())

def token(s,pos,end):
    start=pos;quoted=False;escape=False;depth=0
    while pos<len(s):
        c=s[pos];pos+=1
        if quoted:
            if escape:escape=False
            elif c=="\\":escape=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c=="[":depth+=1
        elif c=="]":depth-=1
        if not quoted and depth==0 and c==end:
            return ast.literal_eval(s[start:pos]),pos
    raise ValueError("unterminated exec field")

def collect_execs(trace):
    success=collections.Counter();hashes=[];resumed=0
    for f in sorted(trace.glob("exec.*")):
        assert f.name[5:].isdigit()
        pending=None;raw=f.read_bytes();hashes.append((f.name,digest_bytes(raw)))
        for line in raw.decode().splitlines():
            if line.endswith("<unfinished ...>"):
                assert pending is None;pending=line[:line.rfind("<unfinished ...>")];continue
            if line.startswith("<... "):
                assert pending is not None
                old,sep,rest=line.partition(" resumed>")
                assert sep and old[5:]==pending.split("(",1)[0]
                line=pending+rest;pending=None;resumed+=1
            if not (line.startswith(("execve(","execveat(")) and re.search(r"=\s*0\s*$",line)):continue
            pos=line.index("(")+1
            if line.startswith("execveat("):pos=line.index(", ",pos)+2
            assert line[pos]=='"'
            path,pos=token(line,pos,'"')
            assert line[pos:pos+2]==", ";pos+=2;assert line[pos]=="["
            argv,pos=token(line,pos,"]");assert line[pos:pos+2]==", " and isinstance(argv,list)
            success[path,tuple(argv)]+=1
        assert pending is None
    assert hashes
    return success,digest_bytes(json.dumps(hashes,separators=(",",":")).encode()),len(hashes),resumed

def physical_role(process):
    exe=Path(process["path"]);av=process["argv"]
    if exe.name=="cargo":
        return "cargo" if "/toolchains/ohm/bin/" in str(exe) else "cargo-proxy"
    if exe.name=="rustc" and "/toolchains/ohm/bin/" in str(exe):
        if "--crate-name" not in av or (any(x=="--print" or x.startswith("--print=") for x in av) and not any(x=="--emit" or x.startswith("--emit=") for x in av)):return "rustc-probe"
        return "rustc-link-only" if any(x=="-Zlink-only" or x.startswith("-Zlink-only=") for x in av) else "rustc-full"
    if exe.name=="ld.bfd" and exe.parent.name=="wild-ld":return "wild"
    if exe.name=="collect2":return "collect2"
    if exe.name in {"cc","gcc"} or re.match(r".*-gcc(?:-[0-9]+)?$",exe.name):return "cc"
    return "other"

def project(armroot):
    w=armroot/"visit";enr=readj(armroot/"enrollment.json");op=readj(armroot/"operator.json");b=readj(w/"bound.json");T=readj(w/"terminal.json")
    assert op["exit"]==0 and op["abort"] is None and op["terminal"]==sha(w/"terminal.json") and op["source_receipt"]==sha(armroot/"enrollment.json")
    assert op["min_mem"]>16*2**30+600*2**20 and op["min_free"]>2**30+128*2**20
    assert T["passed"] and T["both_native_controls"] and T["independent_edited_full_cmp"] and set(T["states"])==set(ORDER)
    assert b["source_head"]=="93526150df078af7dd8fc4226cdcc469539d2001" and b["source_edit"]=="1b9310471b7d1178633e58ee63808522609db887"
    assert b["ordinary"]==["cargo","+ohm",*CARGOCMD] and b["cpus"]==[4,5,6,7] and b["real_euid"]==1000
    assert not {"RUSTC","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","WILD_LOG"}&set(b["env"])
    assert b["subject"]==enr and enr["physical_verified_file_count"]==2453 and set(b["sdk"].values())==set(readj(w/"tools.json").values())
    assert enr["cargo_sha256"]=="96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5" and enr["wild_sha256"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    out={};artsha=set();all_bodies={};toolnames={};pubkey=lambda j: '/'.join([j['role'],Path(j['path']).name])
    dest=Path(b["env"]["CARGO_TARGET_DIR"]);recorded_outputs={}
    for label in ORDER:
        d=w/label;r=T["states"][label];assert readj(d/"result.json")==r
        entry=readj(d/"entered.json")
        assert r["native_sha"]==sha(d/"native-jobs.json.gz") and r["cargo_stdout"]==sha(d/"stdout") and r["cargo_stderr"]==sha(d/"stderr")
        jobs=json.load(gzip.open(d/"native-jobs.json.gz"));phys,commit,ntr,resumed=collect_execs(d/"trace")
        assert collections.Counter((x["path"],tuple(x["argv"])) for x in jobs)==phys
        assert all(physical_role(j)==j["role"] for j in jobs)
        counts=collections.Counter(j["role"] for j in jobs);assert dict(counts)==r["counters"] and counts["cargo"]==counts["cargo-proxy"]==1
        cargo=next(x for x in jobs if x["role"]=="cargo");assert cargo["argv"][1:]==list(CARGOCMD)
        assert [counts[k] for k in ("rustc-full","rustc-link-only","wild")]==[r["full"],r["cached"],r["wild"]]
        seen=[{"kind":j["role"],"crate":j["argv"][j["argv"].index("--crate-name")+1]} for j in jobs if j["role"] in ("rustc-full","rustc-link-only")]
        assert seen==r["all_real_compilers"]
        rows=[json.loads(line) for line in (d/"stdout").read_bytes().splitlines()];assert rows[-1]=={"reason":"build-finished","success":r["cargo"]==0}
        arts=[v for v in rows if v["reason"]=="compiler-artifact"];assert len(arts)==r["typed"] and sum(v["fresh"] for v in arts)==r["fresh"]
        source=[j["crate"] for j in seen];diag=[];target_elf=None
        if r["cargo"]==0:
            assert r["typed"]==300
            typed=sorted([json.dumps((a["package_id"],a["target"],a["profile"],a["features"]),sort_keys=True,separators=(",",":")) for a in arts]);artsha.add(digest_bytes(("\n".join(typed)+"\n").encode()))
            target,=[a for a in arts if a["target"]["kind"]==["test"] and a["target"]["name"]=="e2e" and a["manifest_path"].endswith("/crates/ty_server/Cargo.toml")]
            target_elf=Path(target["executable"]);rel=target_elf.relative_to(dest);recorded_outputs[label]=rel
            if r["e2e_argv"]:assert Path(r["e2e_argv"][r["e2e_argv"].index("-o")+1])==target_elf
            assert sha(d/"listing")==r["inventory"] and not (d/"listing.stderr").stat().st_size
            if r["runtime"]==0:
                assert r["inventory"]==LIST and sum(x.endswith(b": test") for x in (d/"listing").read_bytes().splitlines())==200
                assert set(r["three_assertions"])==set(CASES)
                for i,k in enumerate(CASES):
                    p=d/("case-"+str(i)+".stdout");assert sha(p)==r["three_assertions"][k] and ("test "+k+" ... ok").encode() in p.read_bytes().splitlines() and b"199 filtered out" in p.read_bytes()
                assert r["coherent"]["exit"]==0 and sha(d/"coherent.rmeta")==r["coherent"]["rmeta"] and all(len(s)==64 for _,s in r["coherent"]["externs"])
                assert len(r["source_in_native_image"])==1
            else:
                assert r["runtime"]==83 and label in ("09-valid","10-forced-valid") and not (d/"listing").stat().st_size
        else:
            assert r["cargo"]==101 and label in ("06-invalid","11-malformed","13-forced-malformed")
            if label=="06-invalid":
                assert r["e2e_wild"]==0
                for m in rows:
                    z=m.get("message",{});code=z.get("code") or {}
                    if code.get("code")=="E0308":
                        diag.extend((y["line_start"],Path(y["file_name"]).as_posix()) for y in z["spans"] if y["is_primary"])
                assert any(line==22 and name.endswith("crates/ty_server/tests/e2e/inlay_hints.rs") for line,name in diag)
            else:
                assert r["e2e_wild"]==1 and "OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in (d/"stdout").read_text()+(d/"stderr").read_text()
        if r["e2e_wild"]:
            av=r["e2e_argv"];assert sum(j["role"]=="wild" and j["argv"]==av for j in jobs)==1
            choices=[i for i,v in enumerate(av) if v.startswith("-L") and "psm" in Path(v[2:]).parts and Path(v[2:]).name=="out"]
            assert len(choices)==1 and choices[0]<av.index("-lgcc_s")
        if label.startswith(("01-","15-")):assert r["typed"]==300 and r["fresh"]==0
        if label in ("02-unchanged","03-unchanged","04-edited","05-edited-repeat","06-invalid","07-recovery","08-restored","09-valid","10-forced-valid","11-malformed","12-remove","13-forced-malformed","14-final-remove"):
            compiled=sorted(collections.Counter(source).items())
        else:compiled=None
        out[label]={"cargo":r["cargo"],"typed":len(arts),"fresh":r["fresh"],"full":r["full"],"link_only":r["cached"],"probe":r["target_info_and_other_rustc_probes"],"cc":counts["cc"],"collect2":counts["collect2"],"wild":r["wild"],"e2e_wild":r["e2e_wild"],"runtime":r["runtime"],"elf":r["elf"],"listing":r["inventory"],"selected_source":r["source_in_native_image"],"checked_cases":sorted(r["three_assertions"]),"coherent_reader_rmeta":r["coherent"]["rmeta"] if r["coherent"] else None,"physical_compiler_names":compiled,"e0308_22":bool(diag),"raw":{"entered":sha(d/"entered.json"),"stdout":r["cargo_stdout"],"stderr":r["cargo_stderr"],"native":r["native_sha"],"per_thread_files":ntr,"per_thread_manifest":commit,"resumed":resumed,"terminal":sha(d/"result.json")}}
    assert len(artsha)==1
    gold=out["01-original-empty"]["elf"];edited=out["04-edited"]["elf"];provider=out["09-valid"]["elf"]
    assert len({gold,edited,provider})==3 and all(out[k]["elf"]==gold for k in ("02-unchanged","03-unchanged","08-restored","12-remove","14-final-remove"))
    assert all(out[k]["elf"]==edited for k in ("05-edited-repeat","07-recovery","15-edited-independent-empty")) and out["10-forced-valid"]["elf"]==provider
    assert out["09-valid"]["runtime"]==out["10-forced-valid"]["runtime"]==83 and out["11-malformed"]["cargo"]==out["13-forced-malformed"]["cargo"]==101
    keep=[w/"warm-edited.elf",w/"target"/recorded_outputs["15-edited-independent-empty"],w/"saved-warm-target"/recorded_outputs["14-final-remove"],w/"10-forced-valid/preserved-prior",w/"13-forced-malformed/preserved-prior"]
    model=[edited,edited,gold,provider,gold]
    for p,h in zip(keep,model):
        assert p.is_file() and not p.is_symlink() and sha(p)==h
        with p.open("rb") as f:assert f.read(4)==b"\x7fELF"
        all_bodies[h]=p.stat().st_size
    assert set(all_bodies)=={gold,edited,provider} and not os.path.samefile(keep[0],keep[1])
    with keep[0].open("rb") as a,keep[1].open("rb") as c:
        while True:
            xa=a.read(2**20);xb=c.read(2**20);assert xa==xb
            if not xa:break
    return {"arm":enr["arm"],"rust_source":enr["rust_source"],"driver":enr["driver_sha256"],"cargo":enr["cargo_sha256"],"cargo_source":enr["cargo_source"],"wild":enr["wild_sha256"],"registry_sha":enr["registry_authenticated"],"full_sdk_receipt":enr["sdk_file_table"],"cpu":b["cpus"],"source":b["source_head"],"historical_edit":b["source_edit"],"source_hashes":b["inputs"],"source_pack":"7d56e04902802ddfcabd614ce444ae3c0a851ab4aa126f05e6d0c0a8a1ab57e5","typed_digest":next(iter(artsha)),"tools":{Path(n).name:h for n,h in b["sdk"].items()},"all_elf_bodies":all_bodies,"ordinary_empty_cmp":True,"command_binding":digest_bytes(json.dumps([b["ordinary"],b["env"]],sort_keys=True).encode()),"terminal":sha(w/"terminal.json"),"operator":sha(armroot/"operator.json"),"min_mem":op["min_mem"],"min_private_free":op["min_free"],"visits":out}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("armroot",type=Path);args=ap.parse_args();print(json.dumps(project(args.armroot),indent=2,sort_keys=True))
