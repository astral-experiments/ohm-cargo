"""Count libm in ordinary, locked Ruff wasm-test builds while checking a real CRLF edit."""
import argparse
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

base="93526150df078af7dd8fc4226cdcc469539d2001"
archive_sha="b6d2cec3eae94f9f509c767b45932f1ada8350c4bdb85af2fcab4a3c14807981"
consumer=b'\nuse ruff_source_file::{LineIndex,OneIndexed,SourceCode};\nfn main() {\n    let line = OneIndexed::from_zero_indexed(0);\n    for text in ["a\\nb", "a\\r\\nb", "a\\rb", "\\r\\n"] {\n        let index = LineIndex::from_source_text(text);\n        print!("{} ", SourceCode::new(text, &index).line_end_exclusive(line).to_usize());\n    }\n    println!();\n}\n'
def digest(path):
    with Path(path).open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def save(path, obj):
    with path.open("x") as f: json.dump(obj,f,sort_keys=True,indent=2);f.write("\n")
def zipbytes(path,data):
    with path.open("xb") as f: f.write(gzip.compress(data,compresslevel=2,mtime=0))
def healthy(work):
    mem=int(next(r.split()[1] for r in Path("/proc/meminfo").read_text().splitlines() if r.startswith("MemAvailable:")))*1024
    vals=[mem,shutil.disk_usage(work).free]
    assert mem>int(os.environ["OHM_LOCAL_MEM_FLOOR"]) and vals[1]>int(os.environ["OHM_LOCAL_DISK_FLOOR"]),vals
    return vals

def joined(text):
    pending=None
    for line in text.splitlines():
        if line.endswith("<unfinished ...>"):
            assert pending is None; pending=line[:line.rfind("<unfinished ...>")]; continue
        if line.startswith("<... "):
            before,sep,tail=line.partition(" resumed>")
            assert pending is not None and sep and before[5:]==pending.split("(",1)[0];line=pending+tail;pending=None
        yield line
    assert pending is None

def physical(tr, rustc, wild):
    jobs=[];links=[];raw={}
    for f in sorted(tr.glob("exec.*")):
        data=f.read_text()
        raw[f.name]=data
        for line in joined(data):
            if not line.startswith("execve(") or not line.endswith(" = 0"):continue
            m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), .*\)\s+= 0',line)
            assert m,(f,line[:120])
            exe=Path(ast.literal_eval(m[1]));args=ast.literal_eval(m[2])
            if not exe.is_absolute() or not exe.is_file(): continue
            if exe.samefile(rustc):
                name=args[args.index("--crate-name")+1] if "--crate-name" in args else None
                linking=any(v=="-Zlink-only" or (v=="-Z" and args[i+1:i+2]==["link-only"]) for i,v in enumerate(args))
                jobs.append({"pid":f.name,"name":name,"kind":"link_only" if linking else ("full" if name and "--out-dir" in args else "query"),"argv":args})
            if exe.samefile(wild): links.append({"pid":f.name,"argv":args})
    return jobs,links,raw

def externs(args):
    return [Path(v.removeprefix("ruff_source_file=")) for i,v in enumerate(args) if i and args[i-1]=="--extern" and v.startswith("ruff_source_file=")]

def select_reader_unit(units,root,jobs):
    normal=lambda row:{k:v for k,v in row["profile"].items() if k!="test"}
    variants=[];eligible=[]
    for unit in units:
        if unit["package_id"]!=root["package_id"] or unit.get("executable") or unit["target"]["name"]!="ruff_source_file" or unit["target"]["kind"]!=["lib"]:
            continue
        lib,=[Path(f) for f in unit["filenames"] if f.endswith(".rlib")]
        meta,=[Path(f) for f in unit["filenames"] if f.endswith(".rmeta")]
        assert not unit["profile"]["test"] and lib.is_file() and meta.is_file()
        variants.append(dict(package_id=unit["package_id"],features=sorted(unit["features"]),profile=unit["profile"],rlib=str(lib),rmeta=str(meta),rlib_sha256=digest(lib),rmeta_sha256=digest(meta)))
        if set(unit["features"])==set(root["features"]) and normal(unit)==normal(root):
            eligible.append((lib,meta))
    lib,meta=eligible[0] if len(eligible)==1 else (None,None)
    assert lib is not None and len(variants)==2 and len({v["rlib"] for v in variants})==2,(variants,eligible)
    assert set(root["features"])=={"get-size","serde"} and root["profile"]["test"]
    observed=[]
    for j in jobs:
        if j["name"] not in ("ruff_wasm","api"):continue
        paths=externs(j["argv"])
        if not paths:
            assert j["kind"]!="full",(j["name"],j["kind"])
            continue
        assert all(e.is_file() and any(e.samefile(v) for v in (lib,meta)) for e in paths),paths
        if j["kind"]=="full":assert any(e.samefile(lib) for e in paths),paths
        observed.append({"crate":j["name"],"kind":j["kind"],"pid":j["pid"],"externs":[str(e) for e in paths]})
    return lib,{"variants":variants,"selected":str(lib),"target_root_features":sorted(root["features"]),"target_root_profile":root["profile"],"target_root_package":root["package_id"],"wasm_api_externs":observed}

def verify_reader_link(jobs,raw,reader,exe,lib,selected_info):
    true,=[j for j in jobs if str(reader) in j["argv"]]
    dep,=externs(true["argv"]);assert dep.is_file() and dep.samefile(lib)
    assert true["argv"][true["argv"].index("-o")+1]==str(exe)
    candidates={v["rlib"] for v in selected_info["variants"]};bound=[];opened=[]
    for pid,body in raw.items():
        for line in joined(body):
            if line.startswith("openat("):
                m=re.match(r'openat\([^,]+, ("(?:[^"\\]|\\.)*"), O_RDONLY[^)]*\)\s+= (\d+)',line)
                if m and ast.literal_eval(m[1])==str(lib):opened.append(pid)
            if not line.startswith("execve(") or not line.endswith(" = 0"):continue
            m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), .*\)\s+= 0',line);assert m
            path=Path(ast.literal_eval(m[1]));args=ast.literal_eval(m[2])
            if path.name not in ("ld","ld.bfd","ld.lld","rust-lld","wild","wild-ld") or "-o" not in args or args[args.index("-o")+1]!=str(exe):continue
            operands=[x for x in args if x in candidates or (not x.startswith("-") and Path(x).name.startswith("libruff_source_file-") and x.endswith(".rlib"))]
            assert all(Path(x).is_file() and Path(x).samefile(lib) for x in operands),operands
            bound.append({"pid":pid,"path":str(path),"linker_sha256":digest(path),"selected_rlib_operands":operands})
    assert bound and any(a["selected_rlib_operands"] for a in bound) and opened and digest(lib)==next(v["rlib_sha256"] for v in selected_info["variants"] if v["rlib"]==str(lib))
    return {"rustc_pid":true["pid"],"rustc_argv":true["argv"],"one_typed_extern":str(dep),"rlib_sha256":digest(lib),"actual_linkers":bound,"opened_selected_pids":sorted(set(opened))}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,required=True,help="Private root containing a writable Ruff overlay at source, an overlay cargo-home, and empty target and shared directories")
    parser.add_argument("--donor",type=Path,required=True,help="Read-only unmodified Ruff checkout")
    parser.add_argument("--save",type=Path,required=True,help="An absent per-arm receipt directory on protected storage")
    parser.add_argument("--driver-sha",required=True,help="Driver digest from the physically authenticated single-change SDK")
    parser.add_argument("--phase",choices=("warm","clean"),required=True)
    parser.add_argument("--arm",choices=("W","F"),required=True)
    a=parser.parse_args()
    cargo_sha=os.environ["OHM_LOCAL_CARGO_SHA"]
    wild_sha=os.environ["OHM_LOCAL_WILD_SHA"]
    work=a.work.resolve(strict=True);source=work/"source";save_root=a.save
    assert os.getuid()!=0 and set(os.sched_getaffinity(0))=={int(i) for i in os.environ["OHM_LOCAL_CPUS"].split(",")} and healthy(work)
    assert all((work/n).is_dir() for n in ("source","cargo-home","target","shared","tmp")) and not any((work/"target").iterdir()) and not any((work/"shared").iterdir())
    assert save_root.parent.is_dir() and not save_root.exists()
    save_root.mkdir(mode=0o700)
    inputs=json.loads(Path(__file__).with_name("source.json").read_bytes())
    actual=source/inputs["relative"];original=actual.read_bytes()
    assert subprocess.check_output(["git","-C",a.donor,"rev-parse","HEAD"],text=True).strip()==base==inputs["head"]
    assert a.donor.resolve(strict=True)!=source.resolve(strict=True) and not actual.samefile(a.donor/inputs["relative"])
    assert original==(a.donor/inputs["relative"]).read_bytes() and digest(source/"Cargo.lock")=="c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
    fixed=inputs["fixed_implementation"].encode()
    assert original.count(fixed)==1
    variants={"original":original,"reverse-production-hunk":original.replace(fixed,inputs["old_implementation"].encode()),"invalid":original.replace(fixed,inputs["invalid_implementation"].encode())}
    assert {k:hashlib.sha256(v).hexdigest() for k,v in variants.items()}==inputs["states"]
    cached,=(work/"cargo-home/registry/cache").glob("*/libm-0.2.16.crate")
    assert digest(cached)==archive_sha
    rustc=Path(subprocess.check_output(["rustup","which","--toolchain","ohm","rustc"],text=True).strip()).resolve()
    sdk=rustc.parent.parent; cargo=sdk/"bin/cargo";wild=sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    driver,=(sdk/"lib").glob("librustc_driver-*.so")
    assert (digest(cargo),digest(wild),digest(driver))==(cargo_sha,wild_sha,a.driver_sha)
    env={k:os.environ[k] for k in ("HOME","PATH","RUSTUP_HOME")}
    env.update(CARGO_HOME=str(work/"cargo-home"),CARGO_TARGET_DIR=str(work/"target"),CARGO_BUILD_BUILD_DIR=str(work/"shared"),CARGO_NET_OFFLINE="true",CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",RUSTUP_AUTO_INSTALL="0",CARGO_TERM_COLOR="never",TMPDIR=str(work/"tmp"),INSTA_UPDATE="no",LC_ALL="C",TZ="UTC")
    version={}
    for tool,opt in (("rustc","-vV"),("cargo","-Vv")):version[tool]=subprocess.check_output([tool,"+ohm",opt],cwd=source,env=env,text=True)
    assert "84af87848a5a952ba61ae6a2cc5b22da24130200" in version["cargo"]
    save(save_root/"input.json",dict(arm=a.arm,phase=a.phase,driver=a.driver_sha,cargo=cargo_sha,wild=wild_sha,base=base,version=version,source=inputs))
    def execute(name,cmd,rc):
        out=work/"tmp"/(name+".out");err=work/"tmp"/(name+".err");minimum=healthy(work)
        with out.open("xb") as fo, err.open("xb") as fe:
            p=subprocess.Popen(cmd,cwd=source,env=env,stdout=fo,stderr=fe,start_new_session=True)
            start=time.monotonic()
            try:
                while p.poll() is None:
                    minimum=list(map(min,minimum,healthy(work)))
                    assert time.monotonic()-start<3600,name
                    time.sleep(0.4)
            finally:
                if p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(10)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        stdout=out.read_bytes();stderr=err.read_bytes()
        zipbytes(save_root/(name+".stdout.gz"),stdout);zipbytes(save_root/(name+".stderr.gz"),stderr)
        save(save_root/(name+".status.json"),{"exit":p.returncode,"minimum":minimum,"command":[str(x) for x in cmd]})
        assert p.returncode==rc,(name,p.returncode,stderr[-900:])
        return stdout
    case=inputs["existing_test"]; reader=work/"tmp/reader.rs";reader.write_bytes(consumer);reader_exe=work/"tmp/reader"
    def visit(tag,state):
        if actual.read_bytes()!=variants[state]:actual.write_bytes(variants[state])
        assert digest(actual)==inputs["states"][state]
        trace=work/"tmp"/(tag+"-trace");trace.mkdir()
        rc=101 if state=="invalid" else 0
        cmd=["strace","-ff","-qq","-s","131072","-e","trace=execve","-o",trace/"exec","cargo","+ohm","test","--no-run","--locked","--offline","-j4","--message-format=json","-p","ruff_wasm","-p","ruff_source_file"]
        output=execute(tag,cmd,rc)
        rows=[json.loads(l) for l in output.splitlines()]
        assert rows[-1]=={"reason":"build-finished","success":rc==0}
        jobs,links,raw=physical(trace,rustc,wild)
        zipbytes(save_root/(tag+".exec.json.gz"),json.dumps(raw).encode())
        state_info={"jobs":jobs,"wild":links,"state":state}
        if rc:
            errors=[r["message"] for r in rows if r["reason"]=="compiler-message" and r["message"]["level"]=="error"]
            assert any(e.get("code") and e["code"]["code"]=="E0425" and "ohm_missing_crlf_offset" in e["message"] for e in errors)
            state_info["error"]="E0425"
        else:
            units=[r for r in rows if r["reason"]=="compiler-artifact"]
            libm,=[u for u in units if u["target"]["name"]=="libm" and u["target"]["kind"]==["lib"]]
            assert libm["features"]==["arch","default"]
            libm_markers={}
            for tree in ("target","shared"):
                for path in (work/tree).rglob("libm-*.d"):
                    data=path.read_bytes()
                    names=[n for n in ("ohm-untracked-relink-inputs","ohm-recheck-dependent-links") if n.encode() in data]
                    if names:libm_markers[str(path.relative_to(work))]={"markers":names,"sha256":hashlib.sha256(data).hexdigest()}
            assert libm_markers,tag
            state_info["libm_markers"]=libm_markers
            root,=[u for u in units if u.get("executable") and u["target"]["name"]=="ruff_source_file"]
            api,=[u for u in units if u.get("executable") and u["target"]["name"]=="api" and "ruff_wasm" in u["package_id"]]
            # The host tool and target harness can build the same local crate with different features.
            lib,selected_info=select_reader_unit(units,root,jobs)
            state_info["selected_reader_input"]=selected_info
            save(save_root/(tag+".source-file-unit.json"),selected_info)
            dirs=sorted({Path(f).parent for u in units for f in u["filenames"]}|{f.parent for tree in ("shared","target") for ext in ("*.so","*.rlib") for f in (work/tree).rglob(ext)})
            reader_trace=work/"tmp"/(tag+"-reader-trace");reader_trace.mkdir()
            execute(tag+"-reader-build",["strace","-ff","-qq","-s","131072","-e","trace=execve,openat","-o",reader_trace/"exec","rustc","+ohm","--edition=2024",reader,"--extern","ruff_source_file="+str(lib),*[a for d in dirs for a in ("-L","dependency="+str(d))],"-o",reader_exe],0)
            rr,_,reader_raw=physical(reader_trace,rustc,wild)
            zipbytes(save_root/(tag+".reader-exec.json.gz"),json.dumps(reader_raw).encode())
            state_info["typed_reader_native"]=verify_reader_link(rr,reader_raw,reader,reader_exe,lib,selected_info)
            save(save_root/(tag+".reader-native.json"),state_info["typed_reader_native"])
            edited=state=="reverse-production-hunk"
            verdict=execute(tag+"-reader",[reader_exe],0).decode().strip()
            assert verdict==("1 2 1 1" if edited else "1 1 1 0")
            inv=execute(tag+"-names",[root["executable"],"--list"],0)
            assert (case+": test").encode() in inv.splitlines()
            body=execute(tag+"-single",[root["executable"],"--exact",case],101 if edited else 0)
            assert (case+(" ... FAILED" if edited else " ... ok")).encode() in body
            api_inv=execute(tag+"-api-names",[api["executable"],"--list"],0)
            state_info.update(libm_fresh=libm["fresh"],units=len(units),products={
                "reader":digest(reader_exe),"verdict":verdict,"root":digest(root["executable"]),"api":digest(api["executable"]),
                "root_names":hashlib.sha256(inv).hexdigest(),"api_names":hashlib.sha256(api_inv).hexdigest(),"expected_test_exit":101 if edited else 0})
        save(save_root/(tag+".json"),state_info)
        return {"full":[j["name"] for j in jobs if j["kind"]=="full"],"link_only":[j["name"] for j in jobs if j["kind"]=="link_only"],"queries":sum(j["kind"]=="query" for j in jobs),"wild":len(links),"product":state_info.get("products"),"state":state}
    sequence=[("independent-edited","reverse-production-hunk")] if a.phase=="clean" else [
        ("original","original"),("repeat-original","original"),("edited","reverse-production-hunk"),
        ("repeat-edited-1","reverse-production-hunk"),("repeat-edited-2","reverse-production-hunk"),("invalid","invalid"),("restored","original")]
    results={}
    try:
        for tag,state in sequence:results[tag]=visit(tag,state)
    finally:
        if actual.read_bytes()!=original:actual.write_bytes(original)
    if a.phase=="warm":
        for k in ("repeat-original","restored"):assert results[k]["product"]==results["original"]["product"]
        for k in ("repeat-edited-1","repeat-edited-2"):assert results[k]["product"]==results["edited"]["product"]
        assert results["original"]["product"]["root"]!=results["edited"]["product"]["root"]
    save(save_root/"terminal.json",{"arm":a.arm,"phase":a.phase,"results":results})
if __name__=="__main__":main()
