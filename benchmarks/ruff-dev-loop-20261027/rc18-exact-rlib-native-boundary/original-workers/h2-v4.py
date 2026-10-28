import hashlib, json, os, subprocess, sys
from pathlib import Path
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
root=Path('/mnt/devbox-scratch/dev-user/ohm-native-cargo-raw-boundary-r2-20261028')
assert root.is_dir()
base=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
cold=base/'frozen-toolchain'
cargo=Path('/mnt/devbox-scratch/dev-user/ohm-rc18-pgo-qualification-20261028/cargo')
driver=base/'mixed-module-children-17-v1-20261028/tool-rc18-export-r2/candidate-driver.so'
sdk=root/'sdk';sdk.mkdir(exist_ok=True)
ru=root/'rustup';(ru/'toolchains').mkdir(parents=True,exist_ok=True)
alias=ru/'toolchains/ohm'
if not alias.exists():alias.symlink_to(sdk)
soname,=list((cold/'lib').glob('librustc_driver-*.so'))
wanted={'cargo':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8','rustc':'4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f','driver':'22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f'}
actual={k:sha(p) for k,p in {'cargo':cargo,'rustc':cold/'bin/rustc','driver':driver}.items()};assert wanted==actual
env={**os.environ,'RUSTUP_HOME':str(ru),'RUSTUP_AUTO_INSTALL':'0','PATH':str(Path.home()/'.cargo/bin')+':'+os.environ['PATH']}
name=sys.argv[1];assert name.isalnum()
cmd=['taskset','-c','24-25','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--bind',str(root),str(root),'--tmpfs','/tmp','--ro-bind',str(cold),str(sdk),'--ro-bind',str(driver),str(sdk/'lib'/soname.name),'--ro-bind',str(cargo),str(sdk/'bin/cargo'),'--',sys.executable,'-IB',str(root/'witness4.py'),str(root/name)]
p=subprocess.run(cmd,env=env,cwd=root);json.dump({'argv':cmd,'actual':actual,'status':p.returncode},(root/(name+'.terminal.json')).open('w'),indent=2);sys.exit(p.returncode)
