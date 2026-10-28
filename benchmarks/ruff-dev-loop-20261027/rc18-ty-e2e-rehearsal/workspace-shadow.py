"""Exercise an earlier native provider, linker failure, and recovery in a real full Ruff Cargo command."""
from pathlib import Path
import ast
import collections
import fcntl
import hashlib
import json
import mmap
import os
import re
import shutil
import subprocess
import sys

root=Path.home()/".cache/ohm-18-ty-e2e-link-20261028"
arm,reference,label=sys.argv[1:]
assert arm in ("rehearsal","release","candidate")
prefix=label+"-"
d=root/"reports"/label;d.mkdir()
src=root/"source";target=root/"target";shared=root/"shared"
assert not subprocess.check_output(["git","--no-optional-locks","-C",src,"status","--porcelain","-z"])
raw=root/"reports"/reference
ref=json.loads((raw/"result.json").read_bytes())
assert ref["arm"]==arm and ref["native_counts"]["wild"]==50
sdk=(root/"rustup/toolchains/ohm").resolve()
assert sdk==(Path.home()/".cache/ohm-rc18-r2-whole-ruff-20261028/sdk" if arm=="rehearsal" else root/"install"/arm)
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
assert digest(sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")==ref["stock_linker"]
targets={};psms=set()
for r in ref["results"]:
    leaf=json.loads((raw/"actual"/(str(r["pid"])+".json")).read_bytes())
    out=Path(leaf["out"]);assert out.is_relative_to(target) and out.is_file()
    targets[out]=r
    psm,={Path(s[2:]) for s in leaf["argv"] if s.startswith("-L") and "psm" in Path(s[2:]).parts}
    psms.add(psm)
psm,=psms
assert (psm.is_relative_to(target) or psm.is_relative_to(shared)) and psm.is_dir() and not (psm/"libgcc_s.so").exists()
e2e,=[p for p,r in targets.items() if r["file"]==ref["ty_e2e"]]
assert shutil.disk_usage(root).free>50*2**30
art=root/"native-shadow";art.mkdir(exist_ok=True)
prep=art/label;prep.mkdir()
provider=Path(subprocess.check_output(["gcc","-print-file-name=libgcc_s.so"],text=True).strip()).resolve(strict=True)
assert provider.is_file() and provider.name in ("libgcc_s.so","libgcc_s.so.1") and not provider.is_relative_to(root)
asm=prep/"probe.S";obj=prep/"probe.o"
symbol="ohm_ruff_workspace_native_preinit_83"
asm.write_text(".text\n.type "+symbol+",@function\n"+symbol+":\n  mov $231,%eax\n  mov $83,%edi\n  syscall\n  ud2\n.section .preinit_array,\"aw\",@preinit_array\n.quad "+symbol+"\n.section .note.GNU-stack,\"\",@progbits\n")
subprocess.run(["as","--64",asm,"-o",obj],check=True)
valid=prep/"valid";invalid=prep/"invalid"
for folder in (valid,invalid):
    subprocess.run(["cp","-a","--reflink=auto","--",psm,folder],check=True)
(valid/"libgcc_s.so").write_text(f"INPUT ( {obj} {provider} )\n")
bad_token="OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT"
(invalid/"libgcc_s.so").write_text(bad_token+" (\n")
env=dict(HOME=str(root/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',USER=os.environ['USER'],
         RUSTUP_HOME=str(root/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(root/'cargo'),CARGO_BUILD_BUILD_DIR=str(shared),
         CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_TERM_COLOR='never',TMPDIR=str(root/'tmp'),
         LC_ALL='C.UTF-8',LANG='C.UTF-8',GIT_OPTIONAL_LOCKS='0',INSTA_UPDATE='no')
def ns(mask):
    n=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp"]
    for path in [d,target,shared,root/"cargo",root/"tmp",root/"home"]:
        n+=["--bind",str(path),str(path)]
    if mask is not None:n+=["--ro-bind",str(mask),str(psm)]
    return n+["--chdir",str(src),"--"]
def has_hook(path):
    with path.open("rb") as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
        return data.find(symbol.encode()+b"\x00")>=0
def write(p,data):
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def lane(hold,load):
    subprocess.run([sys.executable,"-IB",root/"ops/lane.py",prefix+hold,prefix+load,arm],check=True)
args=["cargo","+ohm","test","--workspace","--no-run","--locked","--offline","-j8","--message-format=json"]
exe_expr=re.compile(rb'^execve\(("(?:\\.|[^"\\])*"),\s*(\[.*\]), (?:0x[\da-f]+|NULL).*?\)\s+= 0$')
def run(phase,mask):
    cl=d/phase;cl.mkdir(); trace=cl/"trace";trace.mkdir()
    with (cl/"cargo.stdout").open("xb") as out,(cl/"cargo.stderr").open("xb") as err:
        proc=subprocess.run(ns(mask)+["strace","-ff","-qq","-s","1048576","-e","trace=execve","-o",str(trace/"e")]+args,
                        env=env,stdout=out,stderr=err,timeout=1300)
    output=(cl/"cargo.stdout").read_bytes();error=(cl/"cargo.stderr").read_bytes()
    messages=[json.loads(l) for l in output.splitlines()]
    assert messages[-1]=={"reason":"build-finished","success":phase!="invalid"}
    natives=set();native_execs=0;full=[];linkonly=0
    for t in trace.glob("e.*"):
        for ln in t.read_bytes().splitlines():
            if not ln.startswith(b"execve(") or not ln.endswith(b"= 0"):continue
            match=exe_expr.match(ln);assert match,ln[:100]
            path=Path(ast.literal_eval(match[1].decode()))
            if path.name=="ld.bfd" and path.parent.name=="wild-ld":
                av=ast.literal_eval(match[2].decode());natives.add(Path(av[av.index("-o")+1]));native_execs+=1
            elif path.name=="rustc":
                av=ast.literal_eval(match[2].decode())
                if "--crate-name" in av:
                    if "-Zlink-only" in av or "link-only" in av:linkonly+=1
                    else:full.append(av[av.index("--crate-name")+1])
    results={"phase":phase,"cargo_exit":proc.returncode,"native_link_execs":native_execs,
             "original_50_linked":len(set(targets)&natives),"full":sorted(full),"link_only":linkonly,
             "units":sum(r["reason"]=="compiler-artifact" for r in messages),
             "stderr_sha256":hashlib.sha256(error).hexdigest(),"cargo_stdout_sha256":hashlib.sha256(output).hexdigest()}
    if phase=="invalid":
        assert proc.returncode and native_execs and bad_token.encode() in output+error and b"libgcc_s.so" in output+error
        results["malformed_diagnostic"]=True
    else:
        assert proc.returncode==0 and results["units"]==619
        destination=[]
        for p in sorted(targets):
            hook=has_hook(p)
            row={"output":str(p.relative_to(root)),"sha256":digest(p),"hook_symbol":hook}
            if hook or p==e2e:
                a=subprocess.run(ns(mask)+[str(p),"--list","--format","terse"],capture_output=True,env=env,timeout=35)
                row.update(list_exit=a.returncode,list_count=len(a.stdout.splitlines()),list_sha256=hashlib.sha256(a.stdout).hexdigest())
                if hook:assert a.returncode==83 and not a.stdout and not a.stderr,(p,a.returncode)
                if p==e2e and phase=="restored":assert a.returncode==0 and len(a.stdout.splitlines())==200
            destination.append(row)
        results["outputs"]=destination
        results["exit_83"]=sum(r.get("list_exit")==83 for r in destination)
        if phase=="valid":
            assert results["exit_83"]>=1 and next(r for r in destination if r["output"]==str(e2e.relative_to(root)))["list_exit"]==83
        else:
            assert not any(r["hook_symbol"] for r in destination)
    write(cl/"result.json",results)
    print(phase,{k:v for k,v in results.items() if k not in ("outputs","full")},flush=True)
    return results
# Verify private clone before changing it. Its target and shared paths become the original logical paths.
lock=(root/"measure.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
saved=root/"saved"/(prefix+"working");saved.mkdir()
for path in [target,shared]:
    subprocess.run(["cp","-a","--reflink=auto","--",path,saved/path.name],check=True)
before=[{"output":str(p.relative_to(root)),"sha256":digest(p),"hook_symbol":has_hook(p)} for p in sorted(targets)]
assert not any(r["hook_symbol"] for r in before)
write(d/"before.json",before)
fcntl.flock(lock,fcntl.LOCK_UN)
lane("good","working")
try:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    results=[run(phase,mask) for phase,mask in [("valid",valid),("invalid",invalid),("restored",None)]]
finally:
    fcntl.flock(lock,fcntl.LOCK_UN)
    lane("post","good")
assert all(digest(root/r["output"])==r["sha256"] for r in before)
write(d/"result.json",{"arm":arm,"shadow_anchor":str(psm.relative_to(root)),"system_provider":str(provider),
     "hook_sha256":digest(obj),"wild":ref["stock_linker"],"targets":50,"original_target_unchanged":True,
     "before":before,"phases":results})
