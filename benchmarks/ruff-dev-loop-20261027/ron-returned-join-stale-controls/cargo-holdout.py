import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitflags", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    a = ap.parse_args()
    r = a.work.resolve()
    r.mkdir(parents=True,exist_ok=False)
    for name in ("probe","bitflags","app"):
        (r/name/"src").mkdir(parents=True)
    (r/"Cargo.toml").write_text('[workspace]\nmembers=["probe","bitflags","app"]\nresolver="2"\n[profile.dev]\ndebug="line-tables-only"\nlto="off"\n')
    for name in ("probe","bitflags","app"):
        manifest=f'[package]\nname="{name}"\nversion="0.0.1"\nedition="2021"\n'
        if name=="probe":
            manifest+='[lib]\nproc-macro=true\n'
        if name=="app":
            manifest+='[dependencies]\nbitflags={path="../bitflags"}\nprobe={path="../probe"}\n'
        (r/name/"Cargo.toml").write_text(manifest)
    shutil.copytree(a.bitflags/"src",r/"bitflags/src",dirs_exist_ok=True)
    shutil.copyfile(HERE/"fixtures/probe.rs",r/"probe/src/lib.rs")
    reader=r/"app/src/main.rs"
    shutil.copyfile(HERE/"fixtures/actual.rs",reader)
    for name in ("spec.md","CHANGELOG.md","README.md"):
        shutil.copyfile(a.bitflags/name,r/"bitflags"/name)
    raw=r/"bitflags/src/public.rs"
    assert sha(raw)=="1237676ca4687d8eb8364eb52b23c5f284f73f4d4113ee833fa3470c8b512be9"
    initial=raw.read_bytes()
    anchor=b"        $vis struct $PublicBitFlags(<"
    assert initial.count(anchor)==1
    cases={
        "base":initial,
        "settled":initial,
        "same_offset_different_layout":initial.replace(anchor,b"\n"+anchor[1:]),
        "settled_changed":initial.replace(anchor,b"\n"+anchor[1:]),
        "restore":initial,
        "settled_restored":initial,
    }
    wrapper=r/"rustc-entry"
    wrapper.write_text('#!/bin/sh\nexec rustc +ohm --sysroot "$OHM_HOLDOUT_SYSROOT" "$@"\n')
    wrapper.chmod(0o755)
    env={**os.environ,"CARGO_HOME":str(r/"cargo-home"),"CARGO_TARGET_DIR":str(r/"target"),"CARGO_BUILD_BUILD_DIR":str(r/"shared"),"RUSTC":str(wrapper),"CARGO_NET_OFFLINE":"true","CARGO_TERM_COLOR":"never"}
    checks=[]
    for name,src in cases.items():
        if raw.read_bytes()!=src:
            raw.write_bytes(src)
        p=subprocess.run(["cargo","+ohm","build","--offline","-p","app","--message-format=json"],cwd=r,env=env,text=True,capture_output=True)
        diag=r/("stderr-"+name+".txt")
        diag.write_text(p.stderr)
        assert p.returncode==0,(name,p.stderr)
        products=[j for l in p.stdout.splitlines() if l.strip() and (j:=json.loads(l)).get("reason")=="compiler-artifact"]
        prod=next(j for j in products if j["target"]["name"]=="bitflags")
        executable=Path(next(j["executable"] for j in products if j["target"]["name"]=="app"))
        rlib=next(Path(x) for x in prod["filenames"] if x.endswith(".rlib"))
        root=subprocess.run(["rustc","+ohm","--sysroot",env["OHM_HOLDOUT_SYSROOT"],"-Zls=root",rlib],cwd=r,env=env,text=True,capture_output=True)
        assert root.returncode==0,root.stderr
        header=[x for x in root.stdout.splitlines() if "public_hash" in x or "private hash" in x]
        assert len(header)==2,root.stdout
        deps=[d for path in (r/"target",r/"shared") for d in path.rglob("app.d") if d.parent.name=="out"]
        assert deps
        hashes={str(d.relative_to(r)):sha(d) for d in deps}
        marks=sorted(set("ohm-"+f.decode() for d in deps for f in (b"foreign-span-bytes",b"untrackable-foreign-span") if b"ohm-"+f in d.read_bytes()))
        lines=subprocess.check_output([executable],cwd=r,text=True).splitlines()
        assert len(lines)==3
        checks.append(dict(phase=name,source=sha(raw),observed=lines,root_header=header,dirty=sorted(j["target"]["name"] for j in products if not j["fresh"]),depfile=hashes,markers=marks,exe=sha(executable)))
        (r/"results.json").write_text(json.dumps(checks,indent=2)+"\n")
    assert checks[0]["observed"]==checks[-1]["observed"]
    assert checks[0]["observed"]!=checks[2]["observed"]
    print(json.dumps(checks,indent=2))
if __name__=="__main__":
    main()
