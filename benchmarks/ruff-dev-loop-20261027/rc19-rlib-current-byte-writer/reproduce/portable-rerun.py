"""Run the archive component again on Linux x86-64 using the six preserved Ruff inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--work-root',type=Path,required=True,help='new directory on ext4 with at least 4 GiB free')
p.add_argument('--sdk',type=Path,required=True,help='unpacked official Ohm 1.99.0-18 x86-64 Linux SDK')
p.add_argument('--rustup-home',type=Path,required=True,help='private Rustup home whose ohm alias points to the given SDK')
p.add_argument('--cargo-home',type=Path,required=True,help='Cargo home with the five Cargo.lock dependencies available offline')
p.add_argument('--cargo-proxy',type=Path,required=True,help='path to the rustup cargo proxy, as ordinarily used for cargo +ohm')
p.add_argument('--archives',type=Path,required=True,help='directory with the six historical archive files named by SHA-256')
a=p.parse_args()
assert os.geteuid()!=0 and a.work_root.is_absolute() and not a.work_root.exists()
assert (a.rustup_home.resolve()/'toolchains/ohm').resolve()==a.sdk.resolve()
src=Path(__file__).resolve().parent
repo=src.parent
work=a.work_root;work.mkdir(mode=0o700);study=work/'study';study.mkdir(mode=0o700)
ref=work/'ohm-script-hash-wall-rc19-v1/current';ref.mkdir(parents=True);(ref/'sdk').symlink_to(a.sdk.resolve())
for name in ('Cargo.toml','Cargo.lock','src','prepare.py','native-study.py','mount-study.sh','launch.py','order.json'):
    target=study/name
    if name=='order.json':shutil.copyfile(repo/name,target)
    elif (src/name).is_dir():shutil.copytree(src/name,target)
    else:shutil.copyfile(src/name,target)
inputs=study/'inputs';inputs.mkdir()
prior=json.loads((repo/'terminal/members/provenance.json').read_text())
for spec in prior.values():
    for side in ('before','after'):
        name=spec[side];source=a.archives.resolve()/name
        with source.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==name
        # Give this workspace its own copies for the namespace visibility checks.
        shutil.copyfile(source,inputs/name)
subprocess.run([sys.executable,'-IB',study/'prepare.py',inputs,study/'members'],check=True)
target=study/'target'
env=dict(os.environ,RUSTUP_HOME=str(a.rustup_home.resolve()),CARGO_HOME=str(a.cargo_home.resolve()),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(work/'shared-build'),CARGO_NET_OFFLINE='true')
subprocess.run([a.cargo_proxy,'+ohm','build','--release','--locked','--offline'],cwd=study,env=env,check=True)
for fs in ('ext4','btrfs'):
    subprocess.run([sys.executable,'-IB',study/'launch.py',fs,'rerun'],cwd=study,check=True)
print('Qualified current archives and paired ordinary writer measurements:',study/'trial-btrfs-rerun/pairs.json')

