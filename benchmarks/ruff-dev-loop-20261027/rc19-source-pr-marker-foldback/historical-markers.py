"""Exercise private Ohm marker writes with separate owned sentinels. Use --expect protected for a candidate Cargo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

PUBLIC_CARGO = "02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
PUBLIC_RUSTC = "7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c"
names = {"seed":".ohm-worktree-seed-v7","deny":".ohm-worktree-seed-deny-v7","macro":".ohm-worktree-seed-local-proc-macro-v7","script":".ohm-worktree-result-v1"}
policy = {"seed":b"7\n","deny":b"untrusted compile-time inputs\n","macro":b"local procedural-macro outputs require trust at import time\n","depinfo":b"untracked Cargo output path in compiled code\n"}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sdk",type=Path,default=Path.home()/".cache/ohm-ron-producer-freshness-20261028/official-sdk")
parser.add_argument("--cargo",type=Path,help="Private Cargo file to read-only bind over this SDK Cargo in the child namespace")
parser.add_argument("--cargo-sha",default=PUBLIC_CARGO)
parser.add_argument("--expect",choices=("vulnerable","protected"),required=True)
parser.add_argument("--cpus",default="28,29")
parser.add_argument("--pr",choices=("101","103"),required=True)
args=parser.parse_args()
version="5" if args.pr=="101" else "6"
names={k:v.replace("-v7","-v"+version) for k,v in names.items()}
policy["seed"]=(version+"\n").encode()
def digest(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def describe(path):
    st=path.stat()
    return {"hex":path.read_bytes().hex(),"sha256":digest(path),"inode":st.st_ino,"mode":stat.S_IMODE(st.st_mode)}
sdk=args.sdk.resolve()
cargo=(args.cargo or sdk/"bin/cargo").resolve()
assert digest(cargo)==args.cargo_sha and digest(sdk/"bin/rustc")==PUBLIC_RUSTC
root=Path(tempfile.mkdtemp(prefix="ohm-markers-all-",dir="/dev/shm"))
assert stat.S_IMODE(root.stat().st_mode)==0o700
project=root/"project"
for name in ("project/src","project/local_macro/src","target","build","victims","registry","home","tmp","logs","rustup/toolchains"):
    (root/name).mkdir(parents=True,exist_ok=True)
(root/"rustup/toolchains/ohm").symlink_to(sdk)
(project/"Cargo.toml").write_text('[package]\nname="marker_fixture"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nlocal_macro={path="local_macro"}\n')
(project/"local_macro/Cargo.toml").write_text('[package]\nname="local_macro"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n')
(project/"local_macro/src/lib.rs").write_text('extern crate proc_macro;\n#[proc_macro] pub fn keep(t:proc_macro::TokenStream)->proc_macro::TokenStream {t}\n')
source='local_macro::keep! { pub fn value()->usize { nnn } }\n'
(project/"src/lib.rs").write_text(source.replace("nnn","17"))
(project/"trigger").write_text("initial\n")
(project/"build.rs").write_text('''use std::{fs, path::Path};
fn main() {
    println!("cargo::rerun-if-changed=trigger");
    if let Ok(hook) = fs::read_to_string("owned_hook") {
        let mut rows = hook.lines();
        let marker = Path::new(rows.next().unwrap());
        let victim = Path::new(rows.next().unwrap());
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        assert!(marker.starts_with(root.join("target")) || marker.starts_with(root.join("build")));
        assert!(victim.starts_with(root.join("victims")));
        assert!(marker.symlink_metadata().unwrap().is_file());
        fs::remove_file(marker).unwrap();
        std::os::unix::fs::symlink(victim, marker).unwrap();
    }
}
''')
env={"PATH":str(Path.home()/".cargo/bin")+":/usr/local/bin:/usr/bin:/bin","RUSTUP_HOME":str(root/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","CARGO_HOME":str(root/"registry"),"CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"build"),"HOME":str(root/"home"),"TMPDIR":str(root/"tmp"),"LANG":"C.UTF-8","CARGO_NET_OFFLINE":"true","CARGO_BUILD_JOBS":"2"}
wrapper=root/"workspace-rustc"
wrapper.write_text('#!/bin/sh\nexec "$@"\n')
wrapper.chmod(0o700)
env["RUSTC_WORKSPACE_WRAPPER"]=str(wrapper)
prefix=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--bind",str(root),str(root)]
if args.cargo: prefix+=["--ro-bind",str(cargo),str(sdk/"bin/cargo")]
prefix+=["--chdir",str(project),"--","taskset","-c",args.cpus,"strace","-f","-qq","-s","2048","-e","trace=execve,symlink,symlinkat,readlink,readlinkat,rename,renameat,renameat2"]
out={"root":str(root),"cargo_sha256":digest(cargo),"rustc_sha256":digest(sdk/"bin/rustc"),"expect":args.expect,"builds":[],"cases":{}}
def save():
    (root/"ledger.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
def build(name,options=()):
    trace=root/"logs"/(name+".trace")
    command=[str(Path.home()/".cargo/bin/cargo"),"+ohm","-Zohm-shared-registry-cache",*options,"build","--lib","--message-format=json"]
    run=subprocess.run([*prefix,"-o",str(trace),*command],env=env,capture_output=True)
    (root/"logs"/(name+".stderr")).write_bytes(run.stderr)
    if run.returncode:raise RuntimeError((root,name,run.stderr.decode()))
    entries=[json.loads(line)for line in run.stdout.splitlines()]
    processes=[];calls=[]
    for ln in trace.read_text().splitlines():
        if ".trace" in ln:continue
        if re.search(r'execve\("[^"]*(?:/rustc|/build-script-build|/build_script_build-[a-f0-9]+)"',ln) and ln.endswith(" = 0"):
            if "--crate-name" in ln or "/build-script-build" in ln or "/build_script_build-" in ln:processes.append(hashlib.sha256(ln.encode()).hexdigest())
        if ("victims/" in ln or ".ohm-worktree-" in ln) and re.search(r" (?:rename|readlink|symlink)\w*\(",ln):
            calls.append(ln)
    out["builds"].append({"name":name,"options":list(options),"rc":run.returncode,"trace_sha256":digest(trace),"stdout_sha256":hashlib.sha256(run.stdout).hexdigest(),"stderr_sha256":hashlib.sha256(run.stderr).hexdigest(),"relevant_syscalls":calls,"compiler_or_script_execs":processes,"artifacts":[[x["target"]["name"],x["fresh"]]for x in entries if x["reason"]=="compiler-artifact"]});save()
def find(kind):
    paths=sorted((root/"build").rglob(names[kind])) or sorted((root/"target").rglob(names[kind]))
    if len(paths)!=1:raise RuntimeError((root,kind,[str(p)for p in paths]))
    return paths[0]
def trigger(value):
    (project/"trigger").write_text(value+"\n")
def exercise(kind,marker,rerun,setup=False):
    assert marker.is_file() and not marker.is_symlink() and (marker.is_relative_to(root/"target") or marker.is_relative_to(root/"build"))
    old=marker.read_bytes()
    victim=root/"victims"/(kind+".txt")
    initial=("dummy owner data for "+kind+"\n").encode()
    victim.write_bytes(initial)
    before=describe(victim)
    if setup:
        (project/"owned_hook").write_text(str(marker)+"\n"+str(victim)+"\n")
    else:
        marker.unlink()
        marker.symlink_to(victim)
    rerun()
    after=describe(victim);ismarkerlink=marker.is_symlink()
    out["cases"][kind]={"marker":str(marker.relative_to(root)),"prior_marker_hex":old.hex(),"victim_before":before,"victim_after":after,"final_marker_hex":marker.read_bytes().hex(),"final_marker_is_link":ismarkerlink}
    save()
    if args.expect=="vulnerable":
        assert ismarkerlink and marker.readlink()==victim and before["inode"]!=after["inode"] and victim.read_bytes()!=initial,(root,kind,after,ismarkerlink)
    else:
        assert after==before and not ismarkerlink,(root,kind,after,ismarkerlink)
    current=marker.read_bytes()
    if kind=="script":assert re.fullmatch(rb"[0-9a-f]{64}\n",current)
    else:assert current==policy[kind],(root,kind,current)
    if ismarkerlink:
        marker.unlink();marker.write_bytes(current)
    if setup:(project/"owned_hook").unlink()
build("opt-out-no-previous",["-Zohm-worktree-seeds=no"])
assert not list((root/"target").rglob(names["seed"]))
build("cold")
build("warm")
for kind in (("seed","deny") if args.pr=="101" else ("seed","deny","macro")):
    m=find(kind)
    exercise(kind,m,lambda k=kind:build("ordinary-fresh-"+k))
    assert all(row[1]for row in out["builds"][-1]["artifacts"]) and not out["builds"][-1]["compiler_or_script_execs"]
m=find("script"); trigger("second")
exercise("script",m,lambda:build("actual-script-rerun"))
m=find("deny")
trigger("third")
(project/"src/lib.rs").write_text(source.replace("nnn",'env!("LD_LIBRARY_PATH").len() + 29'))
exercise("depinfo",m,lambda:build("post-script-depinfo"),setup=True)
print(json.dumps(out,indent=2,sort_keys=True))
