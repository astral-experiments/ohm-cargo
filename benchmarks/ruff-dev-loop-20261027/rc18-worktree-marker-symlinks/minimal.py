"""Reproduce the prepared-marker write on a fully fresh normal build using an isolated release SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--sdk",type=Path,required=True)
p.add_argument("--revision",choices=[17,18],type=int,required=True)
p.add_argument("--cargo",type=Path)
p.add_argument("--cargo-sha")
p.add_argument("--expect",choices=["vulnerable","protected"],required=True)
p.add_argument("--cpus",default="28,29")
a=p.parse_args()
packages={
 17:("4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3","7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c","618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7"),
 18:("02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573","c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60","a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de")}
def sha(f):
    with f.open("rb") as b:return hashlib.file_digest(b,"sha256").hexdigest()
sdk=a.sdk.resolve()
c=(a.cargo or sdk/"bin/cargo").resolve()
official,rustc,driver=packages[a.revision]
driverfile,=(sdk/"lib").glob("librustc_driver-*.so")
assert sha(sdk/"bin/cargo")==official and sha(sdk/"bin/rustc")==rustc and sha(driverfile)==driver
assert sha(c)==(a.cargo_sha or official)
r=Path(tempfile.mkdtemp(prefix="ohm-marker-min-",dir="/dev/shm"));project=r/"project"
for d in ("project/src","target","shared","registry","home","tmp","victims","rustup/toolchains"): (r/d).mkdir(parents=True)
(r/"rustup/toolchains/ohm").symlink_to(sdk)
(project/"Cargo.toml").write_text('[package]\nname="owned_case"\nversion="0.1.0"\nedition="2024"\n')
(project/"src/lib.rs").write_text("pub fn value() -> u32 { 17 }\n")
cargo_proxy=Path.home()/".cargo/bin/cargo"
env={"HOME":str(r/"home"),"CARGO_HOME":str(r/"registry"),"RUSTUP_HOME":str(r/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","TMPDIR":str(r/"tmp"),"CARGO_TARGET_DIR":str(r/"target"),"CARGO_BUILD_BUILD_DIR":str(r/"shared"),"PATH":str(cargo_proxy.parent)+":/usr/local/bin:/usr/bin:/bin","LANG":"C.UTF-8","CARGO_NET_OFFLINE":"true"}
base=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--bind",str(r),str(r),"--ro-bind",str(sdk),str(sdk)]
if a.cargo:base+=["--ro-bind",str(c),str(sdk/"bin/cargo")]
base+=["--chdir",str(project),"--","taskset","-c",a.cpus,"strace","-f","-qq","-s","1024","-e","trace=execve,readlink,renameat","-o"]
def build(name,flags=()):
    tr=r/(name+".trace");exe=[str(cargo_proxy),"+ohm",*flags,"build","--lib","--message-format=json"]
    proc=subprocess.run(base+[str(tr),*exe],env=env,capture_output=True)
    assert proc.returncode==0,(r,proc.stderr)
    rows=[x for x in map(json.loads,proc.stdout.splitlines()) if x["reason"]=="compiler-artifact"]
    text=tr.read_text();return {"name":name,"rc":proc.returncode,"args":exe[1:],"fresh":rows[0]["fresh"],"trace_sha256":sha(tr),"stdout_sha256":hashlib.sha256(proc.stdout).hexdigest(),"stderr_sha256":hashlib.sha256(proc.stderr).hexdigest(),"execs":[Path(z).name for z in re.findall(r'execve\("([^"]+)"',text)],"relevant_syscalls":[ln for ln in text.splitlines() if "victims/" in ln and ("readlink(" in ln or "renameat(" in ln)]}
v=r/"victims/owned.txt";initial=b"keep this owned sentinel\n";v.write_bytes(initial)
runs=[build("seeds-disabled",["-Zohm-worktree-seeds=no"])]
markername=".ohm-worktree-seed-v7"
assert not list((r/"target").rglob(markername)) and v.read_bytes()==initial
runs+=[build("ordinary"),build("settled")]
m,=(r/"target").rglob(markername)
assert not m.is_symlink() and m.read_bytes()==b"7\n" and runs[-1]["fresh"]
m.unlink();m.symlink_to(v);before=v.stat().st_ino
runs.append(build("symlink"))
assert runs[-1]["fresh"] and runs[-1]["execs"]==["cargo","cargo"]
after=v.read_bytes();ino=v.stat().st_ino
if a.expect=="vulnerable":assert m.is_symlink() and m.readlink()==v and before!=ino and after==b"7\n"
else:assert not m.is_symlink() and m.read_bytes()==b"7\n" and before==ino and after==initial
print(json.dumps({"release":a.revision,"sdk":str(sdk),"cargo":sha(c),"rustc":rustc,"driver":driver,"root":str(r),"marker":str(m.relative_to(r)),"expected":a.expect,"final_is_link":m.is_symlink(),"victim_before":initial.hex(),"victim_after":after.hex(),"inode_before":before,"inode_after":ino,"runs":runs},sort_keys=True,indent=2))
