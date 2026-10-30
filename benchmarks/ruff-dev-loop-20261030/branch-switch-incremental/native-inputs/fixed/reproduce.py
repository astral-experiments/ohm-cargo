#!/usr/bin/env python3
"""Reproduce a branch-return assembler regression with the installed Ohm Cargo and rustc."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("work", type=Path, help="new private directory to retain the sources and results")
parser.add_argument("--mode", choices=("default", "opt-out"), default="opt-out")
parser.add_argument("--expect", choices=("stale", "correct"), required=True)
args = parser.parse_args()
work = args.work.absolute()
work.mkdir(mode=0o700)
donor = work / "donor"
source = work / "consumer"
out = work / "evidence"
out.mkdir()
env = dict(os.environ)
env.update(CARGO_HOME=str(work/"cargo-home"), CARGO_TARGET_DIR=str(work/"target"),
           CARGO_BUILD_BUILD_DIR=str(work/"shared"), CARGO_NET_OFFLINE="true",
           RUSTUP_AUTO_INSTALL="0", RUSTUP_TOOLCHAIN="ohm", GIT_TERMINAL_PROMPT="0")
for key in ("RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","RUSTC","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER",
            "CARGO_INCREMENTAL","CARGO_PROFILE_DEV_INCREMENTAL","CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST","CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST"):
    env.pop(key,None)
def execute(command,directory,environment=None):
    return subprocess.run(list(map(str,command)), cwd=directory, env=environment or env,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
def checked(command,directory,environment=None):
    result=execute(command,directory,environment)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout
def git(*words):
    return checked(["git",*words],donor)
def sha(data):
    return hashlib.sha256(data).hexdigest()

(donor/"src").mkdir(parents=True)
(donor/"Cargo.toml").write_text('[package]\nname="branch_fixture"\nversion="0.1.0"\nedition="2024"\n')
(donor/"Cargo.lock").write_text('version=4\n\n[[package]]\nname="branch_fixture"\nversion="0.1.0"\n')
(donor/".gitignore").write_text("/external/\n")
assembly=r'''use core::arch::global_asm;
global_asm!(concat!(
    ".pushsection .rodata.branch_fixture,\"a\",@progbits\n",
    ".globl branch_fixture_input\n.type branch_fixture_input,@object\n",
    "branch_fixture_input:\n.include \"", env!("CARGO_MANIFEST_DIR"), "/external/symbol.inc\"\n",
    ".size branch_fixture_input,.-branch_fixture_input\n.popsection\n"
));
unsafe extern "C" { static branch_fixture_input: u8; }
fn main() { let value = unsafe { core::ptr::read_volatile(&raw const branch_fixture_input) }; println!("BRANCH_NATIVE_VALUE={value}"); }
'''
(donor/"src/main.rs").write_text(assembly)
git("init","-b","base");git("rev-parse","--absolute-git-dir","--git-common-dir")
git("config","user.name","Reproducer");git("config","user.email","reproducer@example.invalid")
git("add","--all");git("commit","-m","A reads the assembler input")
git("switch","-c","other")
(donor/"src/main.rs").write_text('fn main(){println!("BRANCH_NATIVE_VALUE=43");}\n')
git("commit","-am","B uses an independent implementation");git("switch","base")
checked(["cargo","+ohm","worktree","add","--target-dir",work/"target","-b","first",source,"base"],
        donor,env|{"CARGO_TARGET_DIR":str(work/"donor-target")})
inputs=source/"external"
inputs.mkdir()
blob=inputs/"payload.bin"
inc=inputs/"symbol.inc"
directive=f'.incbin "{blob}"\n'
inc.write_text(directive)
observations={}
def build(label,empty=False):
    d=out/label;d.mkdir()
    flags=["-Zohm-defaults=no"] if args.mode=="opt-out" else []
    e=env
    if empty:
        e=env|{"CARGO_TARGET_DIR":str(d/"target"),"CARGO_BUILD_BUILD_DIR":str(d/"shared")}
    result=execute(["cargo","+ohm",*flags,"build","--locked","--offline","--message-format=json"],source,e)
    (d/"cargo.stdout").write_bytes(result.stdout);(d/"cargo.stderr").write_bytes(result.stderr)
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert rows[-1]=={"reason":"build-finished","success":result.returncode==0}
    value=None
    product=None
    if result.returncode==0:
        artifact,=[row for row in rows if row["reason"]=="compiler-artifact" and row.get("executable")]
        binary=Path(artifact["executable"])
        text=checked([binary],source,e);(d/"native.stdout").write_bytes(text)
        value=int(text.decode().strip().removeprefix("BRANCH_NATIVE_VALUE="))
        product=sha(binary.read_bytes())
    observations[label]={"exit":result.returncode,"value":value,"ELF":product}
    print(label,result.returncode,value,product or "",flush=True)
    return (result.returncode,value)
def switch(name):
    checked(["git","switch",name],source)
def check_phase(label,expected):
    assert build(label)==expected

blob.write_bytes(bytes([17]))
check_phase("01-A17",(0,17))
switch("other");check_phase("02-B43",(0,43))
blob.write_bytes(bytes([29]));switch("first")
check_phase("03-return-A29",(0,17 if args.expect=="stale" else 29))
assert build("04-empty-A29",empty=True)==(0,29)
switch("other");check_phase("05-B-again",(0,43))
blob.unlink();switch("first")
failure=(0,17) if args.expect=="stale" else (101,None)
check_phase("06-return-A-missing",failure)
assert build("07-empty-missing",empty=True)==(101,None)
blob.write_bytes(bytes([29]));switch("other");check_phase("08-B-after-repair",(0,43))
inc.write_text(".ohm_bad_branch_directive 5\n");switch("first")
check_phase("09-return-A-malformed",failure)
assert build("10-empty-malformed",empty=True)==(101,None)
(out/"summary.json").write_text(json.dumps(observations,sort_keys=True,indent=2)+"\n")
