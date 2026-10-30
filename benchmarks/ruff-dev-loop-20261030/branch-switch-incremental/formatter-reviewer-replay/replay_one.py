"""Run one fresh formatter history on a user-supplied public-source Ohm SDK and Ruff checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import resource

A="b5dba861cc38e3f7fb4524c9ceba3e01a474ea13"
B="7b13f01ba1569887a25670820764b24c206da8e5"
TREES={A:"2b61306d708a211b3725c8d920e7590be6da41ad",B:"97ca36909f1ae8fa028b2c1f48f452fbdcdbbd4c"}
TESTS=("tests::basic","tests::string_processing","comments::tests::parenthesized_expression")
def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sdk",required=True,type=Path,help="Complete source-built SDK for this arm, including the common Cargo and stock Wild")
    ap.add_argument("--ruff-checkout",required=True,type=Path,help="Read-only local Git checkout containing historical Ruff #28335")
    ap.add_argument("--cargo-home",required=True,type=Path,help="Preloaded Cargo home with canonical offline registry inputs")
    ap.add_argument("--work",required=True,type=Path,help="New absent private root. Use the same absolute path in all installations.")
    ap.add_argument("--out",required=True,type=Path,help="New result directory outside --work")
    ap.add_argument("--mode",choices=("history","controls"),default="history")
    ap.add_argument("--min-free-gib",type=float,default=8.0,help="Disk headroom to preserve while using this work directory")
    ap.add_argument("--trace-returns",action="store_true",help="Trace exec and object creation only on control-mode returns")
    args=ap.parse_args()
    if platform.system()!="Linux" or platform.machine()!="x86_64":ap.error("This ABI control requires x86-64 Linux.")
    if args.work.absolute().exists() and args.work.absolute().is_symlink():ap.error("Refuse a symlink work path.")
    if args.trace_returns and args.mode!="controls":ap.error("Time ordinary histories without a tracing prefix.")
    donor=args.sdk.resolve(strict=True);ruff=args.ruff_checkout.resolve(strict=True);registry=(args.cargo_home/"registry").resolve(strict=True)
    work=args.work.absolute();out=args.out.absolute()
    if work.exists() or out.exists() or work.is_relative_to(out) or out.is_relative_to(work):
        ap.error("--work and --out must be two new independent paths.")
    for p in (work.parent,out.parent):p.resolve(strict=True)
    floor=int(args.min_free_gib*2**30)
    if floor<0 or shutil.disk_usage(work.parent).free<floor+4*2**30:ap.error("Additional space for the SDK, registry and target is required.")
    work.mkdir(mode=0o700);out.mkdir(mode=0o700)
    for n in ("source","target","shared","home","tmp","bin","cargo-home","rustup","rustup/toolchains"):(work/n).mkdir()
    def guard():
        if shutil.disk_usage(work).free<floor:raise RuntimeError("The declared work filesystem floor was reached.")
    # The canonical installation is owned by this invocation. Each input SDK and original registry remain separate.
    for src,dst in [(donor,work/"sdk"),(registry,work/"cargo-home/registry")]:
        guard();subprocess.run(["cp","-aL","--reflink=auto","--",src,dst],check=True);guard()
    rustup_proxy=shutil.which("rustup")
    if not rustup_proxy:ap.error("Install rustup so the private cargo +ohm and rustc +ohm proxies can run.")
    tool=Path(rustup_proxy).resolve(strict=True)
    for n in ("cargo","rustc","rustup"):(work/"bin"/n).symlink_to(tool)
    kit=work/"sdk";(work/"rustup/toolchains/ohm").symlink_to(kit)
    env={"PATH":f"{work/'bin'}:/usr/local/bin:/usr/bin:/bin","HOME":str(work/"home"),"CARGO_HOME":str(work/"cargo-home"),
         "RUSTUP_HOME":str(work/"rustup"),"CARGO_TARGET_DIR":str(work/"target"),"CARGO_BUILD_BUILD_DIR":str(work/"shared"),
         "RUSTUP_AUTO_INSTALL":"0","CARGO_NET_OFFLINE":"true","TMPDIR":str(work/"tmp"),"LANG":"C","LC_ALL":"C"}
    src=work/"source"
    def git(*cmd):
        return subprocess.check_output(["git","--no-optional-locks","-C",src,*cmd],env=env)
    git("init","-q");git("fetch","--no-tags","--update-shallow","--depth=2",str(ruff),B)
    assert git("rev-parse",B+"^").decode().strip()==A
    for rev,branch in [(A,"historical-parent"),(B,"historical-feature")]:
        assert git("rev-parse",rev+"^{tree}").decode().strip()==TREES[rev];git("branch",branch,rev)
    def command(argv,d,label,rc=0,environment=env):
        guard();before=resource.getrusage(resource.RUSAGE_CHILDREN)
        with (d/(label+".stdout")).open("xb") as so,(d/(label+".stderr")).open("xb") as se:
            start=time.monotonic_ns()
            proc=subprocess.run(argv,cwd=src,env=environment,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
            elapsed=time.monotonic_ns()-start
        after=resource.getrusage(resource.RUSAGE_CHILDREN);guard()
        record={"argv":list(map(str,argv)),"exit":proc.returncode,"wall_ns":elapsed,"user_s":after.ru_utime-before.ru_utime,"system_s":after.ru_stime-before.ru_stime}
        save(d/(label+".json"),record)
        if proc.returncode!=rc:raise RuntimeError(f"{label} exited {proc.returncode}. See its retained output in {d}.")
        return record
    driver,=(kit/"lib").glob("librustc_driver*.so")
    wild=kit/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    for n in ("cargo","rustc"):
        selected=subprocess.check_output(["rustup","which","--toolchain","ohm",n],env=env,text=True).strip()
        assert Path(selected).samefile(kit/"bin"/n);command([n,"+ohm","-Vv"],out,n)
    save(out/"identity.json",{"cargo":digest(kit/"bin/cargo"),"rustc":digest(kit/"bin/rustc"),"driver":digest(driver),"stock_wild":digest(wild),"source":TREES,"cpus":sorted(os.sched_getaffinity(0))})
    known={}
    ordinary=["cargo","+ohm","test","-p","ruff_python_formatter","--lib","--no-run","--locked","--offline","-j4","--message-format=json"]
    states=([("empty-A",A),("first-B",B),("return-A",A),("return-B",B),("unchanged-B",B)] if args.mode=="history" else
            [("empty-B",B),("first-A",A),("return-B",B),("return-A",A),("invalid-A",A),("recovered-A",A),("unchanged-A",A)])
    last=None;output={}
    for label,rev in states:
        d=out/label;d.mkdir();git_ns=0
        if rev!=last:
            t=time.monotonic_ns();git("switch","-q","historical-parent" if rev==A else "historical-feature");git_ns=time.monotonic_ns()-t;last=rev
        assert git("rev-parse","HEAD").decode().strip()==rev and digest(src/"Cargo.lock")=="839edc8250480bb523619b8d24bd57176a6e1f57c152cca85c5adc61ea5f94eb"
        changed=src/"crates/ruff_python_formatter/src/lib.rs"
        if label=="invalid-A":
            with changed.open("ab") as f:f.write(b"\nconst OHM_FORMATTER_BRANCH_TYPE_GUARD: () = 1u32;\n")
        if label=="recovered-A":git("restore","--",str(changed.relative_to(src)))
        cmd=ordinary
        if args.trace_returns and label.startswith("return-"):
            t=d/"native";t.mkdir();cmd=["strace","-ff","-qq","-ttt","-s","131072","-e","trace=execve,execveat,exit_group,openat,creat","-o",str(t/"exec"),*cmd]
        record=command(cmd,d,"cargo",101 if label=="invalid-A" else 0);record["git_ns"]=git_ns
        msgs=[json.loads(l) for l in (d/"cargo.stdout").read_bytes().splitlines()]
        assert msgs[-1]=={"reason":"build-finished","success":label!="invalid-A"}
        if label=="invalid-A":
            assert any(x["message"].get("code") and x["message"]["code"]["code"]=="E0308" and
                       any("OHM_FORMATTER_BRANCH_TYPE_GUARD" in t["text"] for span in x["message"]["spans"] for t in span["text"])
                       for x in msgs if x["reason"]=="compiler-message")
            output[label]=record;continue
        artifacts=[x for x in msgs if x["reason"]=="compiler-artifact"]
        assert len(artifacts)==216
        dirty=sorted(x["target"]["name"] for x in artifacts if not x["fresh"])
        if label.startswith("return-"):assert dirty==["ruff_db","ruff_python_ast","ruff_python_formatter","ruff_python_parser"],dirty
        if label.startswith("unchanged-"):assert not dirty
        unit,=[a for a in artifacts if a["target"]["name"]=="ruff_python_formatter" and a["profile"]["test"] and a.get("executable")]
        exe=Path(unit["executable"]);runenv=env|{"INSTA_UPDATE":"no","RUSTUP_TOOLCHAIN":"ohm"}
        command([exe,"--list","--format","terse"],d,"list",environment=runenv)
        tests=[q[:-6] for q in (d/"list.stdout").read_text().splitlines() if q.endswith(": test")]
        assert len(set(tests))==53 and set(TESTS)<=set(tests)
        for i,name in enumerate(TESTS):
            command([exe,"--exact",name,"--test-threads=1"],d,f"test-{i}",environment=runenv)
            assert "1 passed;" in (d/f"test-{i}.stdout").read_text()
        if label.startswith("empty"):
            command([exe,"--test-threads=1"],d,"all-tests",environment=runenv)
            assert "51 passed; 0 failed; 2 ignored;" in (d/"all-tests.stdout").read_text()
        extern=[]
        for n in ("ruff_python_ast","ruff_python_parser"):
            a,=[q for q in artifacts if q["target"]["name"]==n and "lib" in q["target"]["kind"]]
            f,=[f for f in a["filenames"] if f.endswith(".rlib")];extern+=["--extern",n+"="+f]
        for directory in sorted({str(Path(f).parent) for x in artifacts for f in x["filenames"]}):extern+=["-L","dependency="+directory]
        for size in (64,56):
            probe=work/"size.rs";probe.write_text(f'use ruff_python_ast::Expr;\nconst _: [(); {size}] = [(); std::mem::size_of::<Expr>()];\npub fn probe() {{ let _ = ruff_python_parser::parse_module("x = 2"); }}\n')
            good=size==(64 if rev==A else 56)
            command(["rustc","+ohm",probe,"--crate-name","branch_expr","--edition=2024","--crate-type=lib","--emit=metadata","--error-format=json",*extern,"-o",work/"size.rmeta"],d,f"size-{size}",0 if good else 1)
            if not good:assert any(j.get("code") and j["code"]["code"]=="E0308" for j in (json.loads(x) for x in (d/f"size-{size}.stderr").read_bytes().splitlines()))
        evidence=(digest(exe),digest(d/"list.stdout"))
        assert known.setdefault(rev,evidence)==evidence
        if not (out/(rev+".elf")).exists():
            shutil.copyfile(exe,out/(rev+".elf"));assert digest(out/(rev+".elf"))==evidence[0]
        record.update(ELF=evidence[0],inventory=evidence[1],dirty=dirty,tests=len(tests));output[label]=record
    save(out/"results.json",output)
    print(json.dumps({"finished":list(output),"ELFs":known,"out":str(out)},sort_keys=True))
if __name__=="__main__":main()
