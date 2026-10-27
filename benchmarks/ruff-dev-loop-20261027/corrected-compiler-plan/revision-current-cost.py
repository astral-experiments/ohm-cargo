"""Count one Ruff native/check producer against the dependencies built by each exact compiler."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
from tempfile import TemporaryDirectory

P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
SOURCE = Path("/home/dev-user/code/oss/ruff-ohm-whole-native-20261027")
FROZEN = P/"frozen-toolchain"
RUSTC = P/"rustup/toolchains/ohm/bin/rustc"
LIB = "librustc_driver-774a793a844d5500.so"
PARENT = "051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518"
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("name")
cli.add_argument("candidate", type=Path)
cli.add_argument("digest")
args = cli.parse_args()
assert re.fullmatch(r"revision-[a-z0-9-]+", args.name) and re.fullmatch(r"[0-9a-f]{64}", args.digest)
out = P/(args.name+"-producer-instructions")
counter = Path(__file__).resolve().parent/"dynamorio"
old = P/"reference-parser-v3"
new = P/(args.name+"-private-state")
subjects = {"parent":(FROZEN/".bench-components"/("driver-"+PARENT),PARENT,old/"parent-cold-target",old/"parent-cold-shared"),
            "candidate":(args.candidate.resolve(),args.digest,new/"target-candidate",new/"shared-candidate")}

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def argv_for(traces):
    calls = []
    for trace in traces.glob("exec.*"):
        for line in trace.read_text(errors="replace").splitlines():
            m = re.search(r'execve\(("[^"]*/rustc"), (\[.*)', line)
            if not m or not line.endswith("= 0") or '"--crate-name", "ruff_python_parser"' not in line:
                continue
            call, _ = json.JSONDecoder().raw_decode(m[2])
            assert Path(call[0]).resolve() == RUSTC.resolve() and "-Zpublic-api-hash" in call
            assert "link-only" not in call and any(x.startswith("incremental=") for x in call)
            calls.append(call)
    (argv,) = calls
    return argv

def write(path,data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    assert not subprocess.check_output(["git","--no-optional-locks","-C",SOURCE,"status","--porcelain"])
    assert subprocess.check_output(["git","-C",SOURCE,"rev-parse","HEAD"],text=True).strip() == PIN
    out.mkdir()
    active = out/"active"
    active.mkdir()
    env = dict(os.environ,RUSTUP_TOOLCHAIN="ohm",RUSTUP_HOME=str(P/"rustup"),RUSTUP_AUTO_INSTALL="0",
               CARGO_MANIFEST_DIR=str(SOURCE/"crates/ruff_python_parser"),CARGO_MANIFEST_PATH=str(SOURCE/"crates/ruff_python_parser/Cargo.toml"),
               CARGO_PKG_NAME="ruff_python_parser",CARGO_PKG_VERSION="0.0.17",GIT_OPTIONAL_LOCKS="0")
    rows=[]
    for mode in ("check","build"):
        controls = {}
        for arm in subjects:
            traces = (P/(args.name+"-check-control")/arm/"edit" if mode=="check" else
                      P/("results-"+args.name+"-build")/(arm+"-verify-edit"))
            controls[arm] = argv_for(traces)
            write(out/(mode+"-"+arm+"-argv.json"),controls[arm])
        for pair,order in enumerate(("AB","BA","BA","AB"),1):
            for ch in order:
                arm = "parent" if ch=="A" else "candidate"
                driver,digest,target,shared = subjects[arm]
                assert sha(driver) == digest
                argv = list(controls[arm])
                argv[argv.index("--out-dir")+1] = str(active)
                argv = ["incremental="+str(active/"incremental") if s.startswith("incremental=") else s for s in argv]
                rec = out/f"{mode}-{pair:02}-{arm}"
                rec.mkdir()
                with TemporaryDirectory(dir=out) as temp:
                    w = ["taskset","-c","0,1","bwrap","--ro-bind","/","/","--dev-bind","/dev","/dev","--proc","/proc","--tmpfs","/tmp",
                         "--ro-bind",str(target),str(P/"native-target"),"--ro-bind",str(shared),str(P/"shared"),
                         "--ro-bind",str(driver),str(FROZEN/"lib"/LIB),"--bind",temp,str(active),"--bind",str(rec),str(rec),
                         "--chdir",str(SOURCE),"--"]
                    cmd = [*w,str(counter/"sdk/bin64/drrun"),"-no_follow_children","-c",str(counter/"client/libpidcounter.so"),
                           str(rec/"rustc.ir"),"--",*argv]
                    with (rec/"stdout").open("wb") as stdout,(rec/"stderr").open("wb") as stderr:
                        result=subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr)
                    assert result.returncode == 0,(rec,(rec/"stderr").read_text()[-1000:])
                    lines=[line.split() for line in (rec/"rustc.ir").read_text().splitlines()]
                    pid = lines[0][1]
                    assert lines[0]==["B",pid,"0","0"] and lines[-1]==["P",pid,"0","0"] and all(l[1]==pid for l in lines)
                    assert Counter(l[2]for l in lines if l[0]=="T")==Counter(l[2]for l in lines if l[0]=="F")
                    assert all(l[0]in("B","P","T","F")or l[0]=="S"and int(l[3])in(10,17)for l in lines)
                    ir = sum(int(l[3])for l in lines if l[0]=="F")
                    (rmeta,)=list(Path(temp).glob("*.rmeta"))
                    row=dict(pair=pair,mode=mode,arm=arm,instructions=ir,driver_sha256=digest,rmeta_sha256=sha(rmeta))
                    write(rec/"receipt.json",row)
                    rows.append(row)
                    write(out/"observations.json",rows)
                    print(mode,pair,arm,ir,flush=True)
    summary = {}
    for mode in ("check","build"):
        pairs = [{r["arm"]:r["instructions"] for r in rows if r["mode"]==mode and r["pair"]==p} for p in range(1,5)]
        summary[mode]=dict(pairs=pairs,paired_median_overhead_pct=statistics.median(100*(p["candidate"]/p["parent"]-1)for p in pairs))
    write(out/"summary.json",summary)
