"""Run the actual compiled repository case against the separately authenticated Rust subject."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys

p=Path("/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027")
q=p/"first-proof-stage1"
label=sys.argv[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mode=sys.argv[2]
driver=Path(sys.argv[3]); digest=sys.argv[4]
assert mode in ("stage1","release") and sha(driver)==digest
sysroot=q/"sysroot" if mode=="stage1" else p/"frozen-toolchain"
inputs=Path(__file__).resolve().parent/"run-make"
run=Path(__file__).resolve().parent/("permanent-"+label)
run.mkdir(); fixture=run/"fixture"; shutil.copytree(inputs/"fixture",fixture)
binding=json.loads((inputs/"runner.json").read_bytes()); assert binding["driver"]==sha(inputs/"rmake") and all(sha(fixture/n)==h for n,h in binding["inputs"].items())
shim=run/"rustc";shim.write_text('#!/bin/sh\nexec rustc +ohm "$@"\n');shim.chmod(0o700)
cfg=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",RUSTUP_HOME=str(p/"rustup"),RUSTUP_AUTO_INSTALL="0",RUSTC=str(shim),RUSTC_BOOTSTRAP="1",HOST_RUSTC_DYLIB_PATH=str(p/"frozen-toolchain/lib"),TARGET_EXE_DYLIB_PATH=str(p/"frozen-toolchain/lib/rustlib/x86_64-unknown-linux-gnu/lib"),LD_LIBRARY_PATH=str(p/"frozen-toolchain/lib"),LD_LIB_PATH_ENVVAR="LD_LIBRARY_PATH",HOST="x86_64-unknown-linux-gnu",TARGET="x86_64-unknown-linux-gnu",TMPDIR=str(run),PATH=str(Path.home()/".cargo/bin")+":"+os.environ["PATH"])
so,=sysroot.glob("lib/librustc_driver-*.so")
ns=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp","--bind",str(run),str(run),"--ro-bind",str(sysroot),str(p/"frozen-toolchain"),"--ro-bind",str(driver),str(p/"frozen-toolchain/lib"/so.name),"--chdir",str(fixture),"--"]
r=subprocess.run([*ns,"taskset","-c","24-27","strace","-ff","-qq","-s","65536","-e","trace=execve,execveat","-o",str(run/"exec"),str(inputs/"rmake")],capture_output=True,env=cfg,timeout=250)
(run/"stderr").write_bytes(r.stderr)
(run/"stdout").write_bytes(r.stdout)
(run/"case.json").write_text(json.dumps({"returncode":r.returncode,"driver":digest,"frontend":sha(sysroot/"bin/rustc"),"case":binding},indent=2,sort_keys=True)+"\n")
print(r.returncode,r.stderr.decode(errors="replace")[-1500:]);sys.exit(r.returncode)
