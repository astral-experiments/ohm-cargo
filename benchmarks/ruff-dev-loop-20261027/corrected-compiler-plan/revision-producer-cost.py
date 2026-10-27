"""Count only the freshly compiled Ruff parser's rustc instructions with matched native toolchains."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
from tempfile import TemporaryDirectory

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("candidate", type=Path)
cli.add_argument("digest")
cli.add_argument("output", type=Path)
args = cli.parse_args()
root = Path("/home/dev-user/.cache")
data = root / "ohm-ruff-packed-edges-20261026/nonleaf"
study = data / "trait-pgo-state"
sysroot = study / "sysroot"
lib = "librustc_driver-774a793a844d5500.so"
counter = root / "ohm-dynamorio-20261026"
source = Path("/home/dev-user/code/oss/ruff-ohm-private-trait-20261026")
out = args.output.resolve()
out.mkdir()
active = out / "active"
active.mkdir()
toolchains = {"parent": study/"armB"/lib, "candidate": args.candidate.resolve()}
def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
assert sha(toolchains["parent"]) == "051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518"
assert sha(toolchains["candidate"]) == args.digest
assert subprocess.check_output(["git","-C",source,"rev-parse","HEAD"],text=True).strip() == "93526150df078af7dd8fc4226cdcc469539d2001"
assert not subprocess.check_output(["git","--no-optional-locks","-C",source,"status","--porcelain"])
cases = {"check": (data/"trait-confirm-current/discovery-C01B",study/"confirmation-current/seedB",study/"confirmation-current/store"),
         "build": (data/"trait-codegen-screen/receipts/objects-v2-0A",data/"trait-codegen-screen/seed",data/"trait-codegen-screen/store")}
env = dict(os.environ, RUSTUP_TOOLCHAIN="ohm", RUSTUP_HOME=str(study/"rustup"), GIT_OPTIONAL_LOCKS="0",
           CARGO_MANIFEST_DIR=str(source/"crates/ruff_python_parser"), CARGO_PKG_NAME="ruff_python_parser", CARGO_PKG_VERSION="0.0.17")
rows = []
for mode, (receipts, seed, canonical) in cases.items():
    (entry,) = [f for f in receipts.glob("compile.*.argv") if b"\0ruff_python_parser\0" in f.read_bytes()]
    argv = [x.decode() for x in entry.read_bytes().split(b"\0") if x]
    assert Path(argv[0]).resolve() == (sysroot/"bin/rustc").resolve() and "-Zpublic-api-hash" in argv
    argv[argv.index("--out-dir")+1] = str(active)
    argv = ["incremental="+str(active/"incremental") if a.startswith("incremental=") else a for a in argv]
    hashes = {}
    for pair, order in enumerate(("AB","BA","BA","AB"),1):
        for letter in order:
            arm = {"A":"parent","B":"candidate"}[letter]
            dst = out / f"{mode}-{pair:02d}-{arm}"
            dst.mkdir()
            with TemporaryDirectory(dir=out) as tmp:
                files = Path(tmp)
                ns = ["taskset","-c","6,7","bwrap","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp",
                      "--ro-bind",str(seed),str(canonical),"--bind",str(files),str(active),"--bind",str(dst),str(dst),
                      "--ro-bind",str(toolchains[arm]),str(sysroot/"lib"/lib),"--chdir",str(source),"--"]
                cmd = [*ns,str(counter/"sdk/bin64/drrun"),"-no_follow_children","-c",str(counter/"client/libpidcounter.so"),
                       str(dst/"rustc.ir"),"--",*argv]
                with (dst/"stdout").open("wb") as stdout, (dst/"stderr").open("wb") as stderr:
                    result = subprocess.run(cmd, env=env, stdout=stdout, stderr=stderr)
                assert result.returncode == 0, (dst, (dst/"stderr").read_text()[-1200:])
                lines = [s.split() for s in (dst/"rustc.ir").read_text().splitlines()]
                pid = lines[0][1]
                assert lines[0] == ["B",pid,"0","0"] and lines[-1] == ["P",pid,"0","0"] and all(r[1] == pid for r in lines)
                assert Counter(r[2] for r in lines if r[0]=="T") == Counter(r[2] for r in lines if r[0]=="F")
                assert all(r[0] in ("B","P","T","F") or r[0]=="S" and int(r[3]) in (10,17) for r in lines)
                ir = sum(int(r[3]) for r in lines if r[0]=="F")
                (meta,) = list(files.glob("*.rmeta"))
                public = subprocess.check_output([*ns,"/home/dev-user/.cargo/bin/rustc","+ohm","-Zls=public_hash",str(active/meta.name)],
                                                 env=env,text=True).strip().split()[-1]
                assert hashes.setdefault(arm,public) == public
                row = dict(mode=mode,pair=pair,arm=arm,instructions=ir,public=public,driver_sha256=sha(toolchains[arm]),
                           metadata_sha256=sha(meta),original_argv_sha256=sha(entry))
                rows.append(row)
                (dst/"receipt.json").write_text(json.dumps(row, indent=2)+"\n")
                (out/"observations.json").write_text(json.dumps(rows, indent=2)+"\n")
                print(mode,pair,arm,ir,flush=True)
summary = {}
for mode in cases:
    pairs = [{r["arm"]:r["instructions"] for r in rows if r["mode"] == mode and r["pair"] == p} for p in range(1,5)]
    summary[mode] = {"paired_median_overhead_pct":statistics.median(100*(p["candidate"]/p["parent"]-1) for p in pairs),
                     "pairs":pairs}
(out/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
