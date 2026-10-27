from pathlib import Path
import sys,os,hashlib,json,subprocess,shutil
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';S=X/'mixed-registry-seed-programs-20261027';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');F=P/'frozen-toolchain';out=P/'mixed-registry-only-pilot'/('parse-source-runmake-'+sys.argv[1]);driver=Path(sys.argv[2]);ids=hashlib.sha256(driver.read_bytes()).hexdigest();assert ids==sys.argv[3];out.mkdir(mode=0o700)
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
shim=out/'rustc';shim.write_text('#!/bin/sh\nexec rustc +ohm "$@"\n');shim.chmod(0o700)
cfg=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTC=str(shim),RUSTC_BOOTSTRAP='1',HOST_RUSTC_DYLIB_PATH=str(F/'lib'),TARGET_EXE_DYLIB_PATH=str(F/'lib/rustlib/x86_64-unknown-linux-gnu/lib'),LD_LIBRARY_PATH=str(F/'lib'),LD_LIB_PATH_ENVVAR='LD_LIBRARY_PATH',TARGET='x86_64-unknown-linux-gnu',HOST='x86_64-unknown-linux-gnu',TMPDIR=str(out))
rows={}
for name in sys.argv[4:]:
    d=out/name;src=S/('rmake-'+name);shutil.copytree(src/'fixture',d)
    spec=json.loads((src/'runner.json').read_bytes());assert sha(src/'rmake')==spec['rmake_sha256'] and all(sha(d/f)==h for f,h in spec['sources'].items())
    ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(out),str(out),'--ro-bind',str(driver),str(F/'lib/librustc_driver-774a793a844d5500.so'),'--chdir',str(d),'--']
    q=subprocess.run([*ns,'strace','-ff','-qq','-s','15000','-e','trace=execve','-o',str(d/'exec'),str(src/'rmake')],env=cfg,capture_output=True,timeout=180)
    (d/'runner.stdout').write_bytes(q.stdout);(d/'runner.stderr').write_bytes(q.stderr)
    rows[name]={'returncode':q.returncode,'driver_sha256':ids,'frontend_sha256':sha(F/'bin/rustc'),'runner':spec,'stderr_tail':q.stderr.decode()[-2000:]}
    (out/'results.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n');print(name,q.returncode,flush=True)
