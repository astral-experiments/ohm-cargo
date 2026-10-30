"""Run an actual Ruff integration build after a previously built Git branch advances."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

OPS=Path(__file__).resolve().parent
spec=json.loads((OPS/"source.json").read_bytes())
def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def save(path,value):
    with path.open("x") as f:
        json.dump(value,f,indent=2,sort_keys=True)
        f.write("\n")
def execute(args,log,env,cwd,name,success=True):
    p=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,timeout=240)
    (log/(name+".stdout")).write_bytes(p.stdout)
    (log/(name+".stderr")).write_bytes(p.stderr)
    save(log/(name+".json"),{"argv":list(map(str,args)),"exit":p.returncode,"stdout":digest(log/(name+".stdout")),"stderr":digest(log/(name+".stderr"))})
    if (p.returncode==0)!=success:
        raise RuntimeError((name,p.returncode,p.stderr[-1400:],p.stdout[-750:]))
    return p
def sessions(target):
    result={}
    for f in target.rglob("dep-graph.bin"):
        s=f.parent
        if s.name.startswith("s-") and not s.name.endswith("-working") and s.parent.name.startswith(("ruff_python_ast-","ruff_python_parser-","fixtures-")):
            result.setdefault(s.parent.name,[]).append(s.name)
    return {k:sorted(v) for k,v in result.items()}
def verify_consumer(rows,p,env,source,target,shared,out):
    units=[r for r in rows if r["reason"]=="compiler-artifact"]
    direct=["rustc","+ohm","--edition=2024","--crate-name","ohm_branch_probe",OPS/"consumer.rs"]
    for dep in ("ruff_python_ast","ruff_python_parser"):
        u,=[x for x in units if x["target"]["name"]==dep and "lib" in x["target"]["kind"]]
        lib,=[j for j in u["filenames"] if j.endswith(".rlib")]
        direct+=["--extern",dep+"="+lib]
    deps={Path(j).parent for x in units for j in x["filenames"]}
    for base in (target,shared):
        for pattern in ("*.rlib","*.so"):
            deps.update(j.parent for j in base.rglob(pattern))
    for path in sorted(deps):
        direct+=["-L","dependency="+str(path)]
    for path in sorted({x["out_dir"] for x in rows if x.get("reason")=="build-script-executed" and x.get("out_dir")}):
        direct+=["-L","native="+path]
    reader=out/"reader"
    execute([*direct,"-o",reader],p,env,source,"compile-reader")
    return reader,execute([reader],p,env,source,"run-reader").stdout.decode().strip()
def kernel(p):
    traces=sorted(p.glob("kernel.log.*"))
    assert traces
    lines=[line for raw in traces for line in raw.read_text(errors="replace").splitlines()]
    exc=[l for l in lines if "execve(" in l and re.search(r"= 0$",l)]
    comp=[l for l in exc if '/bin/rustc"' in l and '"--crate-name"' in l]
    wild=[l for l in exc if '/wild-ld/ld.bfd"' in l]
    assert len(wild)>=1 and any('"ruff_python_parser"' in l for l in comp),(wild,[l[:300] for l in comp])
    keep=[l for l in lines if "dep-graph.bin" in l and any(s in l for s in ("link(","linkat(","FICLONE","copy_file_range"))]
    (p/"copy-lines").write_text("\n".join(keep)+"\n")
    compressed={}
    for raw in traces:
        gz=raw.with_name(raw.name+".gz")
        with raw.open("rb") as inp,gz.open("xb") as sink,gzip.GzipFile(fileobj=sink,mode="wb",mtime=0) as outgzip:
            shutil.copyfileobj(inp,outgzip)
        raw.unlink()
        compressed[gz.name]=digest(gz)
    return {"kernel_compilers":[re.search(r'"--crate-name", "([^"]+)"',l).group(1) for l in comp],
            "kernel_wild":len(wild),"kernel_gzip":compressed}

def main():
    args=argparse.ArgumentParser(description=__doc__)
    for n in ("parent-sdk","candidate-sdk","pack","out"):
        args.add_argument("--"+n,required=True,type=Path)
    a=args.parse_args()
    out=a.out.resolve()
    out.mkdir(mode=0o700)
    kits={"P":a.parent_sdk.resolve(strict=True),"Q":a.candidate_sdk.resolve(strict=True)}
    sdk=out/"sdk"
    shutil.copytree(kits["P"],sdk,symlinks=True)
    rustup=out/"rustup/toolchains"
    rustup.mkdir(parents=True)
    (rustup/"ohm").symlink_to(sdk)
    target,shared,source=[out/n for n in ("target","build","ruff")]
    source.mkdir()
    env=os.environ|dict(RUSTUP_HOME=str(rustup.parent),RUSTUP_TOOLCHAIN="ohm",RUSTUP_AUTO_INSTALL="0",
                        CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_NET_OFFLINE="true",
                        CARGO_TERM_COLOR="never",INSTA_UPDATE="no",**spec["identity"])
    for k in ("RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","RUSTC","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","CARGO_INCREMENTAL","CARGO_UNSTABLE_OHM_DEFAULTS"):
        env.pop(k,None)
    def git(*argv,stdin=None):
        return subprocess.check_output(["git","--no-optional-locks","-C",source,*argv],env=env,stdin=stdin).decode().strip()
    git("init","--quiet")
    with a.pack.open("rb") as f:
        git("index-pack","--stdin",stdin=f)
    (source/".git/shallow").write_text(spec["A"]+"\n")
    parent="refs/heads/historical-parent"
    git("update-ref",parent,spec["A"])
    git("update-ref","refs/heads/historical-feature",spec["B"])
    git("switch","--quiet","historical-parent")
    patch=out/"parser-validation.patch"
    patch.write_bytes(gzip.decompress((OPS/"parser-validation.patch.gz").read_bytes()))
    assert digest(patch)==spec["patch_sha256"] and digest(source/spec["path"])==spec["original_sha256"]
    git("apply","--reverse","--index",str(patch))
    assert digest(source/spec["path"])==spec["changed_sha256"]
    ct=git("write-tree")
    assert ct==spec["C_tree"]
    c=git("commit-tree",ct,"-p",spec["A"],"-m",spec["messages"][0])
    d=git("commit-tree",spec["A_tree"],"-p",c,"-m",spec["messages"][1])
    assert [c,d]==[spec["C"],spec["D"]]
    git("restore","--source=HEAD","--staged","--worktree","--",spec["path"])
    assert not git("status","--porcelain")
    git("update-ref","refs/heads/empty-reference",c)
    runs=out/"runs"
    runs.mkdir()
    history={}
    def clear():
        for p in (target,shared):
            if p.exists():
                assert p.parent==out and not p.is_symlink()
                shutil.rmtree(p)
    def phase(role,label,key,branch,traced=False):
        p=runs/(role+"-"+label)
        p.mkdir()
        git("switch","--quiet",branch)
        assert (git("rev-parse","HEAD"),git("rev-parse","HEAD^{tree}"))==(spec[key],spec[key+"_tree"])
        assert git("symbolic-ref","--short","HEAD")==branch and not git("status","--porcelain","--untracked-files=no")
        before=sessions(target)
        argv=["cargo","+ohm","test","-p","ruff_python_parser","--test","fixtures","--no-run","--locked","--offline","-j4","--message-format=json"]
        if traced:
            argv=["strace","-ff","-qq","-yy","-s","8192","-e","trace=execve,execveat,link,linkat,openat,ioctl,copy_file_range","-o",p/"kernel.log",*argv]
        rows=list(map(json.loads,execute(argv,p,env,source,"cargo").stdout.splitlines()))
        assert rows[-1]=={"reason":"build-finished","success":True}
        units=[r for r in rows if r["reason"]=="compiler-artifact"]
        fixture,=[x for x in units if x["target"]["name"]=="fixtures" and x.get("executable")]
        exe=Path(fixture["executable"])
        folder=source/"crates/ruff_python_parser"
        listing=execute([exe,"--list"],p,env,folder,"inventory").stdout.decode()
        names=[s[:-6] for s in listing.splitlines() if s.endswith(": test")]
        chosen,=[n for n in names if "signed_pattern_non_literal_operand.py" in n]
        selected=execute([exe,"--exact",chosen,"--test-threads=1"],p,env,folder,"upstream-test",success=key!="C")
        report=selected.stdout+selected.stderr
        assert chosen.encode() in report and (b"1 failed" if key=="C" else b"1 passed") in report
        reader,verdict=verify_consumer(rows,p,env,source,target,shared,out)
        assert verdict==f"Expr={56 if key=='B' else 64} signed-expression={'accepted' if key=='C' else 'rejected'}",verdict
        got={"test_elf":digest(exe),"reader_elf":digest(reader),"inventory":hashlib.sha256(listing.encode()).hexdigest(),
             "tests":len(names),"upstream_test":chosen,"test_exit":selected.returncode,"verdict":verdict,
             "git":spec[key],"tree":spec[key+"_tree"],"branch":branch,"sessions_before":before,"sessions_after":sessions(target),
             "dirty":sorted(x["target"]["name"] for x in units if not x["fresh"]),"typed":len(units)}
        ref="A" if key=="D" else key
        hashes=tuple(got[n] for n in ("test_elf","reader_elf","inventory"))
        assert history.setdefault((role,ref),hashes)==hashes,(role,key,"warm/cold",hashes)
        assert history.setdefault(("both",ref),hashes)==hashes,(role,key,"cross-compiler",hashes)
        if label.startswith("empty-") and role=="P":
            shutil.copy2(exe,out/("clean-"+key+"-test.elf"))
            shutil.copy2(reader,out/("clean-"+key+"-reader.elf"))
        if traced:
            got.update(kernel(p))
        save(p/"result.json",got)
        print(role,label,key,verdict,selected.returncode,got.get("kernel_wild"),flush=True)
    drivers={}
    for role,kit in kits.items():
        driver,=(kit/"lib").glob("librustc_driver*.so")
        dr=digest(driver)
        assert dr=={"P":"66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e","Q":"b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c"}[role]
        assert digest(kit/"bin/cargo")=="1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add"
        stable,=(sdk/"lib").glob("librustc_driver*.so")
        temporary=out/"driver.next"
        shutil.copy2(driver,temporary)
        os.replace(temporary,stable)
        assert digest(stable)==dr
        drivers[role]=dr
        git("switch","--quiet","empty-reference")
        if role=="Q":
            git("update-ref",parent,spec["A"],d)
        clear()
        phase(role,"empty-C","C","empty-reference")
        clear()
        phase(role,"empty-A","A","historical-parent")
        phase(role,"first-B","B","historical-feature")
        git("update-ref",parent,c,spec["A"])
        phase(role,"return-moved-C","C","historical-parent",True)
        phase(role,"return-B","B","historical-feature")
        git("update-ref",parent,d,c)
        phase(role,"return-restored-D","D","historical-parent",True)
    save(out/"summary.json",{"sources":spec,"drivers":drivers,"phases":{p.name:json.loads((p/"result.json").read_bytes()) for p in runs.iterdir()}})
    print("Both branch advances matched their empty sources and native verdicts.",flush=True)

if __name__=="__main__":
    main()
