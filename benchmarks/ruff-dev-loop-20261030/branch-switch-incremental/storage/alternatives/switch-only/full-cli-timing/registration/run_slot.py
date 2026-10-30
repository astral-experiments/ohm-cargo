#!/usr/bin/env python3
"""Execute one prepared, ordinary Ruff installation in the enrolled mount namespace."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERE=Path(__file__).resolve().parent
def module(name):
    s=importlib.util.spec_from_file_location(name,HERE/(name+".py"))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m

measure=module("measure")
oracle=module("cli_oracle")
census=module("census")
analyze=module("analyze")
def require(value,reason):
    if not value:raise ValueError(reason)
def load(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def commit(obj):
    return hashlib.sha256((json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
def put(p,obj):
    with p.open("x") as f:json.dump(obj,f,sort_keys=True,indent=2);f.write("\n")
def identical(a,b):
    if a.stat().st_size!=b.stat().st_size:return False
    with a.open("rb") as f,b.open("rb") as g:
        while data:=f.read(2**20):
            if data!=g.read(len(data)):return False
        return not g.read(1)

def terminal(cmd,cwd,env,out,tag):
    with (out/(tag+".stdout")).open("xb") as a,(out/(tag+".stderr")).open("xb") as b:
        proc=subprocess.run(cmd,cwd=cwd,env=env,stdout=a,stderr=b)
    put(out/(tag+".process.json"),{"argv":list(map(str,cmd)),"exit":proc.returncode})
    proc.check_returncode()

def settled(view,d):
    frame=census.census(view/"products",view/"shared")
    fd=os.open(view/".allocation",os.O_RDONLY|os.O_DIRECTORY)
    try: fs=os.fstatvfs(fd)
    finally:os.close(fd)
    allocated=(fs.f_blocks-fs.f_bfree)*fs.f_frsize
    require(allocated==frame["all"]["allocated_bytes"] and not frame["working_directories"],"unstable output device")
    tables={}
    for k in ("products","shared"):
        for base,dirs,files in os.walk(view/k):
            if "incremental" not in Path(base).parts:continue
            for name in files:
                if "dep-graph" not in name and "query-cache" not in name:continue
                path=Path(base)/name;st=path.lstat()
                require(path.is_file() and not path.is_symlink(),"unsupported incremental table type")
                key=(st.st_dev,st.st_ino);value=(name.startswith("ohm-packed-"),st.st_blocks*512,st.st_size)
                require(tables.setdefault(key,value)==value,"inconsistent table alias")
    put(d/"settled.json",frame)
    total=lambda part:frame[part]["allocated_bytes"]
    result=dict(whole=total("all"),target=total("products"),shared=total("shared"),shared_names=total("both_roots_same_inode"),
                incremental=total("all_incremental"),incremental_exclusive=total("incremental_only"),
                incremental_also_outside=total("incremental_also_named_outside"),filesystem_used=allocated,
                working_sessions=len(frame["working_directories"]),ledger_sha256=frame["name_plus_inode_ledger_sha256"])
    for packed,name in [(True,"packed_bytes"),(False,"raw_table_bytes")]:
        result[name]=sum(n for b,n,_ in tables.values() if b==packed)
    put(d/"storage.json",result)
    return result

def typed_roster(messages):
    rows=[{"id":m["package_id"],"target":m["target"]["name"],"kind":m["target"]["kind"],"crate_types":m["target"]["crate_types"],
           "profile":m["profile"],"features":m["features"],"fresh":m["fresh"]} for m in messages]
    sig=lambda row:json.dumps({k:v for k,v in row.items() if k!="fresh"},sort_keys=True,separators=(",",":"))
    graph=hashlib.sha256(("\n".join(sorted(sig(r) for r in rows))+"\n").encode()).hexdigest()
    return rows, graph, sorted(sig(r) for r in rows if not r["fresh"])

def checked_body(generated,ref,body_dir,phase,tag):
    require(generated.is_file() and not generated.is_symlink() and not generated.stat().st_mode&0o6000,"generated untrusted artifact")
    body=body_dir/ref["sha256"]
    require(body.is_file() and os.statvfs(body).f_flag&os.ST_RDONLY,"cold reference must be physically read-only")
    actual=sha(generated)
    matches=(actual==ref["sha256"]==sha(body) and generated.stat().st_size==ref["bytes"] and identical(generated,body))
    if not matches:
        # Preserve a genuine unexpected native product before the temporary mount exits.
        archive=phase/(tag+"-unexpected-"+actual+".zst")
        require(shutil.disk_usage(phase).free>140*2**30+180*2**20,"cannot safely archive unexpected ELF")
        with archive.open("xb") as f:
            subprocess.run(["zstd","-q","-T1","-1","-c",str(generated)],stdout=f,check=True)
            f.flush();os.fsync(f.fileno())
        decoder=subprocess.Popen(["zstd","-qdc",str(archive)],stdout=subprocess.PIPE)
        with decoder.stdout as raw:preserved=hashlib.file_digest(raw,"sha256").hexdigest()
        require(decoder.wait()==0 and preserved==actual,"mismatched ELF capture")
        put(phase/(tag+"-mismatch.json"),{"expected":ref,"actual_sha256":actual,"actual_bytes":generated.stat().st_size,"compressed_sha256":sha(archive)})
        raise ValueError("complete generated file differs from its separately empty native reference")
    return ref

def run(conf,tag):
    plan=load(HERE/"plan.json")
    slot,=[s for s in analyze.schedule(plan) if s["slot"]==tag]
    arm=slot["arm"];study=Path(conf["receipts"]);view=Path(conf["canonical"]);src=view/"source"
    inp=Path(conf["source_inputs"]);sdk=view/"sdk";native=Path(conf["native_custody"]);d=study/"runs"/tag
    refs=load(study/"native-reference.json");front=load(study/"logs"/tag/"front.json");public=refs["public"]
    require(sha(study/"native-reference.json")==front["native_reference_sha256"] and len(load(study/"logs"/tag/"sdk.json")["physical"])==57,
            "missing kernel-bound per-slot source and 57-file SDK admission")
    require(front["qualified"] and front["all_visible_HOME_aliases_read_only"] and front["writable_HOME_budget"]==0,"mount admission")
    require(os.sched_getaffinity(0)==set(conf["cpus"]) and os.getuid()!=0,"privileges and CPU group")
    require(os.statvfs(inp).f_flag & os.ST_RDONLY and os.statvfs(native).f_flag & os.ST_RDONLY,"immutable input custody")
    require(not list((view/"products").iterdir()) and not list((view/"shared").iterdir()),"targets must be empty")
    require(shutil.disk_usage(view).total==6*2**30 and shutil.disk_usage(view/".allocation").total==10*2**30 and
            view.stat().st_dev!=(view/"products").stat().st_dev==(view/"shared").stat().st_dev,"separate source and exclusive output")
    d.mkdir(mode=0o700)
    for n in ("rustup","home","tmp","bin"):
        (view/n).mkdir(mode=0o700)
    (view/"rustup/toolchains").mkdir();(view/"rustup/toolchains/ohm").symlink_to(sdk)
    for n in ("cargo","rustc","rustup"):
        proxy=(Path(conf["proxies"])/n).resolve(strict=True)
        require(os.statvfs(proxy).f_flag & os.ST_RDONLY,"rustup proxy must remain read-only")
        (view/"bin"/n).symlink_to(proxy)
    subprocess.run(["cp","-a","--reflink=never","--",str(Path(conf["donor"])/"cargo-home"),str(view/"cargo-home")],check=True)
    env={"PATH":str(view/"bin")+":/usr/local/bin:/usr/bin:/bin","HOME":str(view/"home"),"CARGO_HOME":str(view/"cargo-home"),
         "RUSTUP_HOME":str(view/"rustup"),"CARGO_TARGET_DIR":str(view/"products"),"CARGO_BUILD_BUILD_DIR":str(view/"shared"),
         "RUSTUP_AUTO_INSTALL":"0","CARGO_NET_OFFLINE":"true","TMPDIR":str(view/"tmp"),"LC_ALL":"C","LANG":"C"}
    if arm=="on":env["CARGO_ENCODED_RUSTFLAGS"]=plan["on_flag"]
    for n in ("rustc","cargo"):
        resolved=Path(subprocess.check_output(["rustup","which","--toolchain","ohm",n],env=env,text=True).strip())
        require(resolved.samefile(sdk/"bin"/n),"wrong Rustup installation")
        (d/(n+"-version.txt")).write_bytes(subprocess.check_output([n,"+ohm","-Vv"],env=env))
    source_rec=load(inp/"sources.json")
    require((source_rec["role_A"],source_rec["role_B"])==(plan["ruff"]["A"],plan["ruff"]["B"]) and sha(inp/"ruff.pack")==source_rec["pack_sha256"],"Ruff source")
    src.mkdir(mode=0o700);g=["git","--no-optional-locks","-C",str(src)]
    def git(*args,**kw):
        return subprocess.run([*g,*args],env=env,check=True,**kw)
    git("init","--quiet")
    with (inp/"ruff.pack").open("rb") as f:git("index-pack","--stdin",stdin=f,stdout=subprocess.DEVNULL)
    (src/".git/shallow").write_text(plan["ruff"]["A"]+"\n")
    branches={"A":"historical-parent","B":"historical-feature"}
    for rev,branch in branches.items():git("update-ref","refs/heads/"+branch,plan["ruff"][rev])
    def switch(rev):
        t=time.monotonic_ns();git("switch","--quiet",branches[rev]);dt=time.monotonic_ns()-t
        require(git("symbolic-ref","--short","HEAD",capture_output=True,text=True).stdout.strip()==branches[rev],"wrong Git branch")
        require(git("rev-parse","HEAD",capture_output=True,text=True).stdout.strip()==plan["ruff"][rev],"wrong source commit")
        require(git("rev-parse","HEAD^{tree}",capture_output=True,text=True).stdout.strip()==source_rec["trees"][plan["ruff"][rev]],"wrong source tree")
        git("diff","--exit-code",capture_output=True)
        require(sha(src/"Cargo.lock")==source_rec["lockfile"],"working Cargo.lock")
        return dt
    switch("A")
    want={v["name"]+"-"+v["version"]+".crate":v["checksum"] for v in tomllib.loads((src/"Cargo.lock").read_text())["package"] if "checksum" in v}
    registry=view/"cargo-home/registry";idx=load(inp/"historical-index.json")
    require(len(want)==plan["registry_archives"] and len(idx["entries"])==plan["sparse_rows"] and all(
        any(sha(f)==h for f in (registry/"cache").glob("*/"+n)) for n,h in want.items()) and all(
        any(sha(f)==v["sha256"] for f in (registry/"index").glob("*/.cache/"+v["name"])) for v in idx["entries"]), "physical locked registry")
    consumer=Path(conf["consumer"]);require(sha(consumer)==sha(HERE/"consumer.rs")=="69b71457fca1ee4b9594c733aea2f597bac93d2dfce2c3432e76fbe50ec5e2a7","real external reader")
    empty=settled(view,d);require(empty["whole"]==0,"fresh installation")
    visits=[]
    for phase in analyze.PHASES:
        rev=phase[-1];commit_id=plan["ruff"][rev];pd=d/phase;pd.mkdir()
        switched=0 if phase.startswith(("empty","unchanged")) else switch(rev)
        proc=measure.ordinary_cargo(src,env,view/"tmp",pd)
        usage=settled(view,pd)
        msgs=[json.loads(line) for line in (pd/"cargo.stdout").read_bytes().splitlines()]
        require(msgs[-1]=={"reason":"build-finished","success":True},"Cargo completion")
        art=[m for m in msgs if m.get("reason")=="compiler-artifact"]
        roster,graph,dirty=typed_roster(art);put(pd/"typed.json",roster)
        raw_native=native/"runs"/(arm+"-storage")/phase/"result.json"
        ref=load(raw_native);gold=public["native_reference"][arm][phase]
        require(sha(raw_native)==gold["raw_native_result"] and ref["revision"]==commit_id and graph==ref["graph_sha256"] and dirty==ref["dirty"],"actual graph/dirty set")
        chosen=[m["out_dir"]+"/build" for m in msgs if m.get("reason")=="build-script-executed" and "tikv-jemalloc-sys" in m.get("package_id","")]
        require(chosen==[ref["native_comp_dir"]],"same Cargo-reported native build directory")
        selected,=[m for m in art if m["target"]["name"]=="ruff" and "bin" in m["target"]["kind"] and m["executable"]]
        binary=view/"products/debug/ruff";require(Path(selected["executable"]).samefile(binary) and (not selected["fresh"])==ref["selected_dirty"],"physical CLI")
        cli=checked_body(binary,ref["CLI_ELF"],native/"elf",pd,"ruff")
        verdict=oracle.cli_checks(pd,binary,env,src,commit_id)
        require(verdict==ref["outcomes"],"all seven native verdicts and outputs")
        roots={}
        for package in ("ruff_python_ast","ruff_python_parser"):
            found={Path(f) for m in art if m["target"]["name"]==package and "lib" in m["target"]["kind"] for f in m["filenames"] if f.endswith(".rlib")}
            require(len(found)==1,"current external reader dependency");roots[package]=found.pop()
        paths={str(f.parent) for loc in ("shared","products") for pat in ("*.rlib","*.so") for f in (view/loc).rglob(pat)}
        native_dirs={m["out_dir"] for m in msgs if m.get("reason")=="build-script-executed" and m.get("out_dir")}
        rx=view/"reader.elf";args=["rustc","+ohm","--edition=2024","--crate-name","ohm_branch_reader",consumer]
        for name,rlib in roots.items():args.extend(["--extern",name+"="+str(rlib)])
        for path in sorted(paths):args.extend(["-L","dependency="+path])
        for path in sorted(native_dirs):args.extend(["-L","native="+path])
        terminal([*args,"-o",rx],src,env,pd,"reader-build");terminal([rx],src,env,pd,"reader-run")
        reader=checked_body(rx,ref["reader"],native/"elf",pd,"reader")
        require((pd/"reader-run.stdout").read_text().strip()==ref["observed"]==("Expr=64 valid=1 rejected" if rev=="A" else "Expr=56 valid=1 rejected"),"AST reader")
        row=dict(phase=phase,source=commit_id,exit=proc["exit"],typed_units=len(art),dirty_units=len(dirty),graph_sha256=graph,
                 cli=cli,reader=reader,verdict_sha256=commit(verdict),dirty_set_sha256=commit(dirty),elapsed_ns=proc["wall_ns"],
                 user_cpu_us=proc["user_cpu_us"],system_cpu_us=proc["system_cpu_us"],git_ns=switched,storage=usage,process_sha256=sha(pd/"cargo.process.json"))
        put(pd/"result.json",row);row=dict(row,result_sha256=sha(pd/"result.json"))
        analyze.check_visit(row,phase,arm,plan,gold)
        visits.append(row)
    out=dict(**slot,physical_sdk_sha256=public["physical_sdk_sha256"],physical_sdk_entries=57,empty_workspace=True,
             actual_front_gate=True,front_sha256=sha(study/"logs"/tag/"front.json"),visits=visits)
    put(d/"completed.json",out)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("configuration",type=Path);ap.add_argument("slot")
    args=ap.parse_args();run(load(args.configuration),args.slot)
if __name__=="__main__":
    main()
