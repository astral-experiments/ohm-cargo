"""Portable worker derived from the recorded H8 driver. Called by replay.py."""
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess as sp
import sys
import time
from pathlib import Path

NATIVE = runpy.run_path(str(Path(__file__).resolve().with_name("native_execs.py")))

MANIFEST = "893b5ff55f23fde170f5079766ebbe20937419a24296394a6dd0f326b8ccba88"
EDITED = "05c9068b358390c0ce8eeacc915763f610e12cb4b6fe3dde6af19323c2c9dff0"
LOCK = "c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
BASE = "967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9"
RUST = "5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
HUNK = b'[profile.dev.package.salsa]\nopt-level = 3\n\n'
def hf(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
def hb(data):
    return hashlib.sha256(data).hexdigest()
def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True)+"\n")
def guard():
    assert os.geteuid() == CFG["uid"] != 0
    assert shutil.disk_usage(H).free > CFG["reserve_bytes"]
    assert shutil.disk_usage(ROOT).free > CFG["reserve_bytes"]

def selection(mode):
    assert mode == "check"
    return ["check","-p","ruff_text_size","--locked","--offline"]
def worker(mode, arm, image, expected_sha, output):
    guard()
    assert mode == "check" and arm in ("C","A","B") and output.is_dir()
    assert set(os.sched_getaffinity(0)) == set(CFG["cpus"])
    assert Path("/proc/self/status").read_text().split("CapEff:\t")[1].splitlines()[0] == "0000000000000000"
    source, sdk = VIEW/"source", VIEW/"sdk"
    exe = sdk/"bin/cargo"
    assert hf(image) == expected_sha
    tmp = exe.with_name("cargo.install-private")
    before=exe.stat()
    shutil.copyfile(image,tmp)
    tmp.chmod(0o500)
    os.utime(tmp,ns=(before.st_atime_ns,before.st_mtime_ns))
    os.replace(tmp,exe)
    assert hf(exe) == expected_sha and not exe.is_symlink()
    assert hf(sdk/"bin/rustc")==RUST and hf(sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")==WILD
    env = dict(HOME=str(H), USER=CFG["username"], LOGNAME=CFG["username"], PATH=CFG["proxies"]+":/usr/bin:/bin",
               RUSTUP_HOME=str(VIEW/"ru"), CARGO_HOME=str(VIEW/"cargo-home"), CARGO_TARGET_DIR=str(VIEW/"products"),
               CARGO_BUILD_BUILD_DIR=str(VIEW/"shared"), TMPDIR=str(VIEW/"tmp"), CARGO_NET_OFFLINE="true",
               RUSTUP_AUTO_INSTALL="0", CARGO_TERM_COLOR="never", CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",
               TZ="UTC", LC_ALL="C.UTF-8")
    if CFG.get("mechanism_only"):
        env["CARGO_LOG"]="cargo::ops::resolve=debug"
    cli = [str(Path(CFG["proxies"])/"cargo"), "+ohm"]
    def call(cmd, *, environment=env, **kw):
        return sp.run(cmd, cwd=source, env=environment, stdout=sp.PIPE, stderr=sp.PIPE, timeout=180, **kw)
    version=call(cli+["-Vv"],check=True).stdout
    assert b"2fe90823d8eadc95de56c2cde8d41e0082aac0eb" in version
    assert call(["git","rev-parse","HEAD"],check=True).stdout.strip()==b"93526150df078af7dd8fc4226cdcc469539d2001"
    mf,lock=source/"Cargo.toml",source/"Cargo.lock"
    orig=mf.read_bytes()
    assert (hb(orig),orig.count(HUNK),hf(lock))==(MANIFEST,1,LOCK)
    edit=orig.replace(HUNK,b"")
    assert hb(edit)==EDITED
    args=selection(mode)
    discovery=dict(env,CARGO_TARGET_DIR=str(VIEW/"discovery-products"),CARGO_BUILD_BUILD_DIR=str(VIEW/"discovery-build"))
    plan=call(cli+["-Zunstable-options",*args,"--unit-graph"],environment=discovery,check=True)
    graph=json.loads(plan.stdout)["units"]
    assert len(graph)==1
    # The stock unit graph can include build-script execution units that do not emit an artifact.
    dump(output/"enrollment.json",dict(cargo=expected_sha,version=version.decode(),rust=RUST,wild=WILD,
         orig=hb(orig),edit=hb(edit),lock=LOCK,units=len(graph),plan=hb(plan.stdout),argv=args,env=env))
    def traced(label, allow_work):
        tr=output/(label+".exec")
        cmd=["strace","-f","-qq","-s","131072","-e","trace=execve,execveat","-o",str(tr),*cli,*args,"--message-format=json"]
        x=call(cmd)
        (output/(label+".jsonl")).write_bytes(x.stdout)
        (output/(label+".stderr")).write_bytes(x.stderr)
        assert x.returncode==0,(label,x.stderr[-1200:])
        rows=[json.loads(l) for l in x.stdout.splitlines()]
        arts=[r for r in rows if r["reason"]=="compiler-artifact"]
        assert rows[-1]=={"reason":"build-finished","success":True} and arts
        assert len(arts)==1
        paths={str(Path(f).relative_to(VIEW)):hf(f) for r in arts for f in r["filenames"] if Path(f).is_file()}
        roster=sorted((r["package_id"],r["target"]["name"],r["target"]["kind"],r["features"]) for r in arts)
        joined=NATIVE["native_execs"](tr.read_bytes())
        ev=[[r["program"],NATIVE["is_compile"](r),NATIVE["is_link"](r)] for r in joined]
        assert [r["program"] for r in joined[:2]] == ["cargo","cargo"]
        workers=[e for e in ev if e[1] or e[2]]
        if not allow_work:
            assert not workers and all(r["fresh"] for r in arts),(label,workers,[r["target"]["name"] for r in arts if not r["fresh"]])
        metadata,=[f for r in arts for f in r["filenames"] if f.endswith(".rmeta")]
        assert Path(metadata).stat().st_size > 1024
        rustc=[str(Path(CFG["proxies"])/"rustc"),"+ohm","--edition=2024","--crate-type","lib",
               "--extern","ruff_text_size="+metadata,"--emit=metadata","--cap-lints","allow"]
        good=VIEW/"checked-consumer.rmeta"
        call(rustc+["--crate-name","ohm_valid_consumer",str(VIEW/"consumer.rs"),"-o",str(good)],check=True)
        assert good.stat().st_size>512
        negative=VIEW/"profile-check-negative.rs"
        negative.write_text("use ruff_text_size::OhmNonexistentProfileInput;\n")
        res=call(rustc+["--crate-name","ohm_invalid_consumer","--error-format=json",str(negative),"-o",str(VIEW/"rejected.rmeta")])
        errors=[json.loads(l)for l in res.stderr.splitlines()]
        explicit=[(e["code"]["code"],e["message"]) for e in errors if e.get("code") and e.get("level")=="error"]
        assert res.returncode==1 and len(explicit)==1 and explicit[0][0]=="E0432" and "OhmNonexistentProfileInput" in explicit[0][1]
        assert not (VIEW/"rejected.rmeta").exists()
        oracle=[hf(good),explicit]
        assert hf(lock)==LOCK
        result=dict(files=paths,roster=roster,oracle=oracle,exec=ev,dirty=[r["target"]["name"] for r in arts if not r["fresh"]])
        if CFG.get("mechanism_only"):
            full=x.stderr.count(b"resolve_with_registry:resolve_with_previous:register_patch_entries:")
            hits=x.stderr.count(b"reusing the cached workspace resolution")
            assert full or hits
            result.update(full=full,hits=hits)
        return result
    print("READY",flush=True)
    prior=None
    for line in sys.stdin:
        tag,kind,what=line.strip().split()
        if what=="finish":
            assert mf.read_bytes()==orig and hf(lock)==LOCK
            print('{"closed":true}',flush=True)
            break
        guard()
        data=orig if kind=="orig" else edit
        if mf.read_bytes()!=data:
            mf.write_bytes(data)
        if what in ("hydrate","trace"):
            result=traced(tag,what=="hydrate")
            identity={k:result[k] for k in ("files","roster","oracle")}
            if prior is not None: assert identity==prior,tag
            prior=identity
        elif what=="wall":
            begin=time.perf_counter_ns()
            x=call(cli+args)
            ns=time.perf_counter_ns()-begin
            assert x.returncode==0 and b"Finished" in x.stderr and b"Compiling " not in x.stderr and b"Checking " not in x.stderr
            assert not x.stdout and hf(lock)==LOCK
            (output/(tag+".stdout")).write_bytes(x.stdout)
            (output/(tag+".stderr")).write_bytes(x.stderr)
            result=dict(ns=ns,exit=x.returncode,stdout=hb(x.stdout),stderr=hb(x.stderr))
        else:
            raise ValueError(what)
        dump(output/(tag+".json"),result)
        print(json.dumps({"row":tag,"ns":result.get("ns")}),flush=True)

if __name__ == "__main__":
    _, config, mode, arm, image, image_sha, output = sys.argv
    CFG=json.loads(Path(config).read_text())
    H=Path(CFG["home"]); ROOT=Path(CFG["scratch"]); VIEW=ROOT/"arena"
    worker(mode, arm, Path(image), image_sha, Path(output))
