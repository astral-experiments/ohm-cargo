from pathlib import Path
import json,os,shutil,subprocess,sys
d=Path(__file__).resolve().parent;n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');repo=Path('/home/dev-user/code/oss/ohm-rust-private-native-20261027');fixtures=repo/'tests/run-make/rdr-public-hash-private-native-impls';s=d/'rmake';s.mkdir(exist_ok=True);pkg=s/'package';pkg.mkdir(exist_ok=True)
(pkg/'Cargo.toml').write_text('[package]\nname="rdr-private-native-recipe"\nversion="0.0.0"\nedition="2024"\n[dependencies]\nrun_make_support={path="'+str(repo/'src/tools/run-make-support')+'"}\n[[bin]]\nname="rmake"\npath="'+str(fixtures/'rmake.rs')+'"\n')
home=s/'cargo-home';home.mkdir(exist_ok=True)
if not (home/'registry').exists():(home/'registry').symlink_to('/mnt/devbox-scratch/dev-user/ohm-nonleaf-perflint-20261026/stage-bootstrap/cargo-home/registry')
env=dict(os.environ,CARGO_HOME=str(home),CARGO_TARGET_DIR=str(s/'target'),CARGO_BUILD_BUILD_DIR=str(s/'shared'),CARGO_BUILD_JOBS='2',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all')
cmd=['taskset','-c','24-25','/home/dev-user/.cargo/bin/cargo','+ohm','build','--manifest-path',pkg/'Cargo.toml','--offline','--message-format=json'];p=subprocess.run(cmd,env=env,capture_output=True);(s/'cargo-stdout').write_bytes(p.stdout);(s/'cargo-stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr[-1500:]
runner=next(j['executable'] for l in p.stdout.splitlines() if (j:=json.loads(l))['reason']=='compiler-artifact' and j['target']['name']=='rmake');rt=n/'trait-pgo-state/sysroot'
for arm in ('candidate','control'):
    drv=d/'stage2-candidate' if arm=='candidate' else n/'trait-pgo-state/armB';out=s/(sys.argv[1]+'-'+arm);out.mkdir()
    for file in ('dep.rs','hidden.rs','main.rs'):shutil.copyfile(fixtures/file,out/file)
    shim=s/'rustc-with-sysroot';shim.write_text('#!/bin/sh\nexec '+str(rt/'bin/rustc')+' --sysroot '+str(rt)+' "$@"\n');shim.chmod(0o755)
    e=dict(env,RUSTC=str(shim),RUSTC_BOOTSTRAP='1',HOST_RUSTC_DYLIB_PATH=str(drv),TARGET_EXE_DYLIB_PATH=str(rt/'lib/rustlib/x86_64-unknown-linux-gnu/lib'),LD_LIBRARY_PATH=str(drv)+':'+str(rt/'lib'),LD_LIB_PATH_ENVVAR='LD_LIBRARY_PATH',TARGET='x86_64-unknown-linux-gnu',HOST='x86_64-unknown-linux-gnu',TMPDIR=str(out))
    proc=subprocess.run(['taskset','-c','24-25',runner],cwd=out,env=e,capture_output=True);(out/'stdout').write_bytes(proc.stdout);(out/'stderr').write_bytes(proc.stderr)
    print(arm,proc.returncode,proc.stderr[-850:].decode(),flush=True)
    if arm=='candidate':assert proc.returncode==0
    else:assert proc.returncode!=0 and b'assertion `left == right` failed' in proc.stderr and b'Public hash:' in proc.stderr
