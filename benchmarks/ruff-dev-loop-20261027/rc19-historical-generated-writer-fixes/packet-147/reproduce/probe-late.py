"""Place one same-UID symlink immediately after Cargo invalidates a generated record."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

here=Path(__file__).resolve().parent
watcher=here/"watch-relink-entry.py"
spec=importlib.util.spec_from_file_location("witness",watcher)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
def sha(b):return hashlib.sha256(b).hexdigest()
p=argparse.ArgumentParser();p.add_argument("root",type=Path);p.add_argument("sdk",type=Path)
p.add_argument("--case",choices=("provenance","check-hint"),required=True)
p.add_argument("--expect",choices=("follows","protected"),required=True)
p.add_argument("--disabled",action="store_true")
a=p.parse_args();root=a.root.resolve();root.mkdir(mode=0o700)
sdk=a.sdk.resolve(strict=True)
(root/"rustup/toolchains").mkdir(parents=True)
(root/"rustup/toolchains/ohm").symlink_to(sdk,target_is_directory=True)
src=root/"workspace"
for name in ("src","tests"): (src/name).mkdir(parents=True)
(src/"Cargo.toml").write_text('[package]\nname="cache_probe"\nversion="0.1.0"\nedition="2024"\n')
(src/"src/main.rs").write_text('fn main() { println!("{}", cache_probe::value()); }\n')
env={"PATH":os.environ["PATH"],"LANG":"C","HOME":str(root),"CARGO_HOME":str(root/"cargo-home"),
     "RUSTUP_HOME":str(root/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","RUSTUP_AUTO_INSTALL":"0",
     "CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"build"),
     "CARGO_NET_OFFLINE":"true","CARGO_INCREMENTAL":"0"}
cmd=[shutil.which("cargo"),"+ohm"]+(["build"] if a.case=="provenance" else ["check","--test","witness"])+["--offline","--message-format=json","-j1"]
if a.disabled: cmd.insert(2,"-Zohm-defaults=no")
record=None;rows=[]
for phase,value in (("cold",17),("during",29),("before",31),("repeat",31)):
    if phase!="repeat":
        (src/"src/lib.rs").write_text(f'pub fn value() -> u32 {{ {value} }}\n')
        (src/"tests/witness.rs").write_text(f'#[test] fn value() {{ let x: u32 = cache_probe::value(); assert_eq!(x,{value}); }}\n')
    victim=root/(phase+"-owned-sentinel");initial=(phase+" unrelated\n").encode();victim.write_bytes(initial)
    inode=victim.stat().st_ino
    watch=None
    if phase=="during" and not a.disabled:
        assert record.is_file() and not record.is_symlink();watch=w.watch_directory(record.parent)
    elif phase=="before" and not a.disabled:
        record.unlink();record.symlink_to(victim)
    proc=subprocess.Popen(cmd,cwd=src,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        if watch is not None: w.install_after_delete(watch,record,victim,proc)
        stdout,stderr=proc.communicate(timeout=90)
    finally:
        if proc.poll() is None: proc.kill();proc.wait()
        if watch is not None: os.close(watch)
    (root/(phase+".stdout")).write_bytes(stdout);(root/(phase+".stderr")).write_bytes(stderr)
    assert proc.returncode==0,stderr[-800:]
    messages=list(map(json.loads,stdout.splitlines()))
    assert messages[-1].get("success")==True
    arts=[m for m in messages if m["reason"]=="compiler-artifact"]
    if a.case=="provenance":
        exe,=[m["executable"] for m in arts if m.get("executable")]
        run=subprocess.run([exe],env=env,capture_output=True,check=True)
        assert run.stdout==f"{value}\n".encode()
        verdict=value
    else:
        assert any(m["target"]["name"]=="witness" for m in arts)
        verdict="checked"
    if phase=="cold":
        if a.case=="provenance":
            candidates=list((root/"target").rglob("ohm-message-provenance-lib-cache_probe"))
        else:
            candidates=[p for d in (root/"target").rglob("ohm-early-test-check-v1") for p in d.iterdir() if p.is_file()]
        if a.disabled: assert not candidates
        else:
            assert len(candidates)==1,(a.case,candidates)
            record,=candidates
    changed=(initial!=victim.read_bytes())
    assert changed==(phase=="during" and not a.disabled and a.expect=="follows"),(a.case,phase,a.expect,changed)
    assert changed==(victim.stat().st_ino!=inode)
    assert record is None or record.is_symlink()==changed
    content=record.read_bytes() if record else b""
    if a.case=="provenance": assert "version" in json.loads(content)
    elif not a.disabled: assert content==b"uses-library\n"
    if phase=="repeat": assert all(m["fresh"] for m in arts)
    rows.append(dict(phase=phase,exit=proc.returncode,verdict=verdict,
               typed=[(m["target"]["name"],m["fresh"]) for m in arts],
               prior=sha(initial),after=sha(victim.read_bytes()),inode_preserved=inode==victim.stat().st_ino,
               changed=changed,record_is_symlink=record.is_symlink() if record else False,record_sha=sha(content),stdout=sha(stdout),stderr=sha(stderr)))
out=dict(case=a.case,disabled=a.disabled,cargo=sha((sdk/"bin/cargo").read_bytes()),compiler=sha((sdk/"bin/rustc").read_bytes()),rows=rows)
(root/"result.json").write_text(json.dumps(out,indent=2)+"\n")
print(a.case,[(r["phase"],r["changed"],r["verdict"]) for r in rows])
