"""Observe one owned preinstalled link in each independent offline Cargo target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

def sha(bytes_): return hashlib.sha256(bytes_).hexdigest()
def save(path,content): path.write_text(json.dumps(content,indent=2)+"\n")
p=argparse.ArgumentParser()
p.add_argument("root",type=Path)
p.add_argument("sdk",type=Path)
p.add_argument("--case",choices=("public-api","resolve"),required=True)
p.add_argument("--expect",choices=("follows","protected"),required=True)
a=p.parse_args()
root=a.root.resolve()
root.mkdir(mode=0o700)
sdk=a.sdk.resolve(strict=True)
rustup=root/"rustup"; (rustup/"toolchains").mkdir(parents=True)
(rustup/"toolchains/ohm").symlink_to(sdk,target_is_directory=True)
source=root/"source"; dep=source/"cache_witness_lib"; app=source/"cache_witness_app"
for path in [dep/"src",app/"src",root/"target",root/"build",root/"cargo-home"]: path.mkdir(parents=True)
(source/"Cargo.toml").write_text('[workspace]\nmembers=["cache_witness_lib","cache_witness_app"]\nresolver="3"\n')
(dep/"Cargo.toml").write_text('[package]\nname="cache_witness_lib"\nversion="0.1.0"\nedition="2024"\n')
(app/"Cargo.toml").write_text('[package]\nname="cache_witness_app"\nversion="0.1.0"\nedition="2024"\n[dependencies]\ncache_witness_lib={path="../cache_witness_lib"}\n')
(app/"src/main.rs").write_text('fn main(){ println!("{}",cache_witness_lib::value()); }\n')
(dep/"src/lib.rs").write_text('pub fn value()->u8{17}\n')
env={"PATH":os.environ["PATH"],"HOME":str(root),"CARGO_HOME":str(root/"cargo-home"),
    "RUSTUP_HOME":str(rustup),"RUSTUP_TOOLCHAIN":"ohm","RUSTUP_AUTO_INSTALL":"0","CARGO_NET_OFFLINE":"true",
    "CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"build"),"CARGO_INCREMENTAL":"0","LANG":"C"}
cargo=shutil.which("cargo")
assert cargo
command=[cargo,"+ohm","build","--offline","-j1","--message-format=json","-p","cache_witness_app"]
rows=[]
def run(phase,value):
    proc=subprocess.run(command,cwd=source,env=env,capture_output=True)
    for k,content in (("stdout",proc.stdout),("stderr",proc.stderr)): (root/(phase+"."+k)).write_bytes(content)
    assert proc.returncode==0,proc.stderr[-500:]
    parsed=list(map(json.loads,proc.stdout.splitlines()))
    assert parsed[-1]["reason"]=="build-finished" and parsed[-1]["success"]
    exe,=[m["executable"] for m in parsed if m.get("executable")]
    native=subprocess.run([exe],env=env,capture_output=True,check=True)
    assert native.stdout==f"{value}\n".encode()
    rows.append(dict(phase=phase,exit=0,value=value,executable=sha(Path(exe).read_bytes()),typed=[(x["target"]["name"],x["fresh"]) for x in parsed if x["reason"]=="compiler-artifact"],stdout=sha(proc.stdout),stderr=sha(proc.stderr)))
run("cold",17)
if a.case=="public-api":
    match=[path for folder in ("target","build") for path in (root/folder).rglob("*.public-api-hash") if path.name=="lib-cache_witness_lib.public-api-hash"]
else:
    match=[path for folder in ("target","build") for path in (root/folder).rglob(".cargo-resolve-cache-v1")]
assert len(match)==1,[(str(x.relative_to(root))) for folder in ("target","build") for x in (root/folder).rglob("*.public-api-hash")]
record,=match
assert record.is_file() and not record.is_symlink()
original_record=record.read_bytes()
victim=root/"unrelated-owned-file"
sentinel=b"private unrelated file\n"
victim.write_bytes(sentinel)
stat0=victim.stat()
record.unlink()
record.symlink_to(victim)
(dep/"src/lib.rs").write_text('pub fn value()->u16{29}\n')
run("changed",29)
after=victim.read_bytes();follows=after!=sentinel
assert follows==(a.expect=="follows"),(a.case,a.expect,after)
assert record.is_symlink()==follows
if follows:
    assert record.read_bytes()==after and victim.stat().st_ino!=stat0.st_ino
else:
    assert record.is_file() and victim.stat().st_ino==stat0.st_ino
if a.case=="public-api":
    assert json.loads(record.read_bytes())["value"] != json.loads(original_record)["value"]
else:
    assert len(record.read_text())==16 and int(record.read_text(),16)>=0
run("repeat",29)
result=dict(case=a.case,cargo=sha((sdk/"bin/cargo").read_bytes()),compiler=sha((sdk/"bin/rustc").read_bytes()),cache_name=record.name,
 before_sha=sha(sentinel),after_sha=sha(after),sentinel_replaced=follows,inode_preserved=victim.stat().st_ino==stat0.st_ino,cache_symlink=record.is_symlink(),records=rows)
save(root/"result.json",result);print(json.dumps(result))
