"""Run six small installed-package commands in one owned tmpfs, with the host mounted read-only."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile

def sha(path):
    with path.open("rb") as s:
        return hashlib.file_digest(s,"sha256").hexdigest()

def record(path):
    return {"bytes_hex":path.read_bytes().hex(),"sha256":sha(path),"inode":path.stat().st_ino,
            "permissions":stat.S_IMODE(path.stat().st_mode)}

sdk = Path.home()/".cache/ohm-ron-producer-freshness-20261028/official-sdk"
tool = Path.home()/".cargo/bin/cargo"
assert sha(sdk/"bin/cargo") == "02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
assert sha(sdk/"bin/rustc") == "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
root=Path(tempfile.mkdtemp(prefix="ohm-marker-sandbox-",dir="/dev/shm"))
assert root.is_dir() and not root.is_symlink() and root.stat().st_uid==os.getuid()
for sub in ("project/src","target","build","victims","registry","home","tmp","logs","rustup/toolchains"):
    (root/sub).mkdir(parents=True,exist_ok=True)
(root/"rustup/toolchains/ohm").symlink_to(sdk)
(root/"project/Cargo.toml").write_text('[package]\nname="marker_fixture"\nversion="0.1.0"\nedition="2024"\n')
(root/"project/src/lib.rs").write_text('pub fn value() -> u32 { 17 }\n')
prefix=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--bind",str(root),str(root),"--chdir",str(root/"project"),"--","taskset","-c","28,29","strace","-f","-qq","-s","1024","-e","trace=execve,symlink,readlink,readlinkat,rename,renameat,renameat2"]
env={"PATH":str(tool.parent)+":/usr/local/bin:/usr/bin:/bin","RUSTUP_HOME":str(root/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","CARGO_HOME":str(root/"registry"),"CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"build"),"HOME":str(root/"home"),"TMPDIR":str(root/"tmp"),"LANG":"C.UTF-8","CARGO_NET_OFFLINE":"true","CARGO_BUILD_JOBS":"2"}
ledger={"root":str(root),"cargo":sha(sdk/"bin/cargo"),"rustc":sha(sdk/"bin/rustc"),"runs":[]}
def build(name,flags=()):
    trace=root/"logs"/(name+".trace")
    p=subprocess.run([*prefix,"-o",str(trace),str(tool),"+ohm",*flags,"build","--lib","--message-format=json"],capture_output=True,env=env)
    (root/"logs"/(name+".stdout")).write_bytes(p.stdout);(root/"logs"/(name+".stderr")).write_bytes(p.stderr)
    data=[json.loads(x) for x in p.stdout.splitlines()]
    selected=[x for x in trace.read_text().splitlines() if ("victims/" in x or ".ohm-worktree-seed-" in x) and ("rename" in x or "readlink" in x)]
    ledger["runs"].append({"name":name,"flags":list(flags),"rc":p.returncode,"stderr":p.stderr.decode(),"stdout_sha256":hashlib.sha256(p.stdout).hexdigest(),
                           "trace_sha256":sha(trace),"marker_syscalls":selected,"artifacts":[{"name":x["target"]["name"],"fresh":x["fresh"]} for x in data if x["reason"]=="compiler-artifact"]})
    assert p.returncode == 0,(name,p.stderr)
def markers():
    return sorted(p for t in ("target","build") for p in (root/t).rglob(".ohm-worktree-seed-v7"))
victim=root/"victims"/"user-sentinel.txt"
content=b"fixture-owner sentinel: keep these bytes\n"
victim.write_bytes(content)
ledger["initial"]=record(victim)
build("first-seeds-off",["-Zohm-worktree-seeds=no"])
assert not markers() and victim.read_bytes()==content
build("prepare")
found=markers()
assert len(found)==1,found
marker,=found; ledger["marker"]=str(marker.relative_to(root));ledger["marker_prepared"]=record(marker)
assert marker.read_bytes()==b"7\n" and marker.is_file() and not marker.is_symlink()
build("regular-fresh");assert victim.read_bytes()==content
marker.unlink();marker.symlink_to(victim)
assert marker.readlink()==victim and victim.read_bytes()==content
ledger["marker_inode"]=marker.lstat().st_ino
build("symlink-seeds-off",["-Zohm-worktree-seeds=no"])
ledger["after_disabled"]=record(victim)
assert victim.read_bytes()==content
build("symlink-default-fresh")
ledger["after_default"]=record(victim)
victim.write_bytes(b"fresh control sentinel from fixture\n")
ledger["before_same_default"]=record(victim)
build("same-default-truly-fresh")
assert ledger["runs"][-1]["artifacts"] == [{"name":"marker_fixture","fresh":True}]
ledger["after_same_default"]=record(victim)
ledger["link_at_end"]={"symlink":marker.is_symlink(),"link":str(marker.readlink()),"inode":marker.lstat().st_ino}
assert marker.is_symlink() and victim.read_bytes()==b"7\n"
print(json.dumps(ledger,indent=2,sort_keys=True))
