"""Check the existing metadata-only Ruff cutoff once per release-like compiler outside timing."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

here = Path(__file__).resolve().parent
def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, here/filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
s = module("series", "revision-series.py")
w = module("worker", "revision-worker.py")
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("name")
cli.add_argument("candidate", type=Path)
cli.add_argument("digest")
cli.add_argument("--inside")
args = cli.parse_args()
assert re.fullmatch(r"revision-[a-z0-9-]+", args.name)
out = s.P / (args.name + "-clean-check-control")
if args.inside:
    arm, step = args.inside.split("/")
    assert w.sha(w.P/"frozen-toolchain/lib/librustc_driver-774a793a844d5500.so") == (w.PARENT if arm == "parent" else args.digest)
    assert w.sha(w.P/"frozen-toolchain/bin/cargo") == w.CARGO_SHA
    env = dict(os.environ, RUSTUP_HOME=str(w.P/"rustup"), RUSTUP_AUTO_INSTALL="0", CARGO_HOME=str(w.P/"registry-home"),
               CARGO_TARGET_DIR=str(w.TARGET), CARGO_BUILD_BUILD_DIR=str(w.P/"shared"), CARGO_BUILD_JOBS="8",
               CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all", CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all", CARGO_TERM_COLOR="never")
    assert not any(k.startswith("WILD_") for k in env)
    current = out/arm/step
    current.mkdir(parents=True)
    cmd = ["cargo","+ohm","check","--locked","--offline","--message-format=json"]
    if step == "edit":
        cmd = ["strace","-ff","-qq","-s","2000","-e","trace=execve","-o",str(current/"exec"),*cmd]
    with (current/"stderr").open("wb") as err, (current/"stdout").open("wb") as stdout:
        result = subprocess.run(cmd, env=env, cwd=w.RUFF, stderr=err, stdout=stdout)
    assert result.returncode == 0
    rows = [json.loads(x) for x in (current/"stdout").read_bytes().splitlines() if x.startswith(b"{")]
    arts = [r for r in rows if r["reason"] == "compiler-artifact"]
    assert arts and rows[-1]["success"]
    dirty = sorted((r["target"]["name"],r["target"]["kind"]) for r in arts if not r["fresh"])
    roster = sorted((r["package_id"],r["target"]["name"],r["target"]["kind"],r["profile"]["test"]) for r in arts)
    data = dict(dirty=dirty, units=len(arts), roster_sha256=__import__("hashlib").sha256(json.dumps(roster).encode()).hexdigest())
    if step.endswith("fresh"):
        assert not dirty
    if step == "edit":
        data.update(w.trace_counts(current))
    s.write(current/"receipt.json", data)
    sys.exit(0)

assert s.sha(args.candidate) == args.digest
stores = Path.home()/".cache"/"ohm-233-clean-check-20261027"
stores.mkdir(exist_ok=True)
prior = s.P/"reference-parser-v3"
state = s.P/(args.name+"-private-state")
assert json.loads((s.P/("results-"+args.name+"-test")/"complete.json").read_bytes())["source_clean"]
patch = s.P/"parser-assets/patches/parser-tstring.patch"
assert s.sha(patch) == s.PATCH_SHA
with (s.P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    assert s.git("rev-parse","HEAD") == s.PIN and not s.git("status","--porcelain")
    index = Path(s.git("rev-parse","--path-format=absolute","--git-path","index"))
    index_sha = s.sha(index)
    files = {n: ((s.RUFF/n).read_bytes(),(s.RUFF/n).stat()) for n in
             (l.split("\t",2)[2] for l in s.git("apply","--numstat",patch).splitlines())}
    out.mkdir()
    report = {}
    for arm in ("parent","candidate"):
        drv,target,shared = ((s.FROZEN/".bench-components"/("driver-"+s.PARENT_SHA), prior/"parent-cold-target", prior/"parent-cold-shared")
                             if arm=="parent" else (args.candidate,state/"target-candidate",state/"shared-candidate"))
        target, shared = stores / (arm+"-target"), stores / (arm+"-shared")
        target.mkdir()
        shared.mkdir()
        wrap = ["bwrap","--ro-bind","/","/","--proc","/proc","--dev-bind","/dev","/dev","--bind","/tmp","/tmp",
                "--bind",str(out),str(out),"--bind",str(s.P/"registry-home"),str(s.P/"registry-home"),
                "--bind",str(s.P/"rustup"),str(s.P/"rustup"),"--bind",str(target),str(s.P/"native-target"),
                "--bind",str(shared),str(s.P/"shared"),"--ro-bind",str(s.P/"subjects/parent"),str(s.FROZEN/"bin/cargo"),
                "--ro-bind",str(drv),str(s.FROZEN/"lib/librustc_driver-774a793a844d5500.so"),"--","taskset","-c","0-23",
                sys.executable,str(Path(__file__).resolve()),args.name,str(args.candidate),args.digest,"--inside"]
        def check(step):
            subprocess.run([*wrap,arm+"/"+step],check=True)
        print(arm, "clean check",flush=True)
        check("settle")
        check("before-fresh")
        with s.edit(patch,files,index,index_sha):
            check("edit")
            check("edit-fresh")
        check("restore")
        check("restore-fresh")
        print(arm, "finished",flush=True)
        report[arm] = json.loads((out/arm/"edit"/"receipt.json").read_bytes())
    assert report["parent"]["roster_sha256"] == report["candidate"]["roster_sha256"]
    assert not s.git("status","--porcelain") and s.sha(index) == index_sha
    s.write(out/"summary.json",report)
