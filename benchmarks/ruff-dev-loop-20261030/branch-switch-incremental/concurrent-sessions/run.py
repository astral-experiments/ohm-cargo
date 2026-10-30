#!/usr/bin/env python3
"""Re-run with complete source-attested SDKs on an x86-64 Linux host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

a = argparse.ArgumentParser()
for key in ("parent-sdk", "guarded-sdk", "guarded-product-dir", "rustup-proxy", "empty-output", "home-volume"):
    a.add_argument("--" + key, type=Path, required=True)
p = a.parse_args()
out = p.empty_output.resolve()
out.mkdir(mode=0o700)
here = Path(__file__).resolve().parent
for f in ("setup.py", "qualify.py"):
    shutil.copy2(here / f, out / f)
shutil.copytree(here / "ops", out / "ops")
def digest(file): return hashlib.sha256(file.read_bytes()).hexdigest()
(out / "register.json").write_text(json.dumps({"source":digest(here / "SHA256SUMS"),"purpose":"fresh portable controlled replay"})+"\n")
env = dict(os.environ, QA_PARENT_SDK=str(p.parent_sdk.resolve()), QA_GUARDED_SDK=str(p.guarded_sdk.resolve()),
           QA_GUARDED_PRODUCT_DIR=str(p.guarded_product_dir.resolve()), QA_RUSTUP_PROXY=str(p.rustup_proxy.resolve()),
           QA_HOME_VOLUME=str(p.home_volume.resolve()))
for program in ("setup.py", "qualify.py"):
    subprocess.run(["taskset", "-c", "0-3", sys.executable, "-IB", str(out / program)], env=env, check=True)
