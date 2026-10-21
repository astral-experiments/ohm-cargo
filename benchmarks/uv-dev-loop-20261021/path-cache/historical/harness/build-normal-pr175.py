#!/usr/bin/env python3
"""Build a matched PR175/path-cache sensitivity pair in the original source path."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/ohm-cargo"
BINARIES = ROOT / "work/binaries"
LOGS = ROOT / "work/logs"
TARGET = ROOT / "work/cargo-build"
BASE = "5e5d271d763d7beb38b48755e22bd59e93f02b97"
ORIGINAL = ROOT / "work/patches/build-output-remap.patch"
UPSTREAM = ROOT / "work/production-build/pr175.patch"
PATH_CACHE = ROOT / "work/patches/path-cache.patch"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, env=None):
    return subprocess.check_output(["git", *args], cwd=SOURCE, env=env)


def now():
    return datetime.now(timezone.utc).isoformat()


def source_tree():
    with tempfile.TemporaryDirectory(prefix="pr175-index-", dir=ROOT / "work") as d:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(Path(d) / "index")
        git("read-tree", "HEAD", env=env)
        git("add", "-u", env=env)
        return git("write-tree", env=env).decode().strip()


def build(name, patches):
    destination = BINARIES / name
    if destination.exists():
        raise RuntimeError(f"Refusing to replace frozen binary {destination}")
    before = git("diff", "--binary")
    env = os.environ.copy()
    env.update(CARGO_HOME="/tmp/codex-cargo-home", CARGO_TARGET_DIR=str(TARGET),
               CARGO_PROFILE_RELEASE_DEBUG="1")
    command = ["cargo", "+1.99.0", "build", "--release", "--locked", "-p", "cargo", "-j16"]
    metadata = {
        "name": name, "started_at": now(), "base_commit": BASE,
        "source_path": str(SOURCE), "target_path": str(TARGET),
        "source_tree": source_tree(), "source_diff_sha256": sha(before),
        "patch_sha256": {str(p): sha(p.read_bytes()) for p in patches},
        "command": command,
        "explicit_build_environment": {k: env[k] for k in (
            "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_PROFILE_RELEASE_DEBUG")},
        "pgo": False,
    }
    output = TARGET / "release/cargo"
    output.unlink(missing_ok=True)
    log = LOGS / f"build-{name}.log"
    print(f"{now()} building {name}", flush=True)
    with log.open("wb") as stream:
        result = subprocess.run(command, cwd=SOURCE, env=env, stdout=stream, stderr=subprocess.STDOUT)
    metadata.update(finished_at=now(), returncode=result.returncode, log_sha256=sha(log.read_bytes()))
    if result.returncode:
        (BINARIES / f"{name}.build.json").write_text(json.dumps(metadata, indent=2) + "\n")
        raise RuntimeError(f"Build failed; inspect {log}")
    if before != git("diff", "--binary"):
        raise RuntimeError("Source changed while compiling")
    shutil.copy2(output, destination)
    metadata.update(sha256=sha(destination.read_bytes()), bytes=destination.stat().st_size)
    (BINARIES / f"{name}.build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    manifest_path = BINARIES / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[name] = metadata
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    subprocess.run(["python3", str(ROOT / "work/benchmark/strip_binaries.py"), name], check=True)
    print(f"{now()} finished {name}", flush=True)


if git("rev-parse", "HEAD").decode().strip() != BASE:
    raise RuntimeError("Unexpected source base")
if git("status", "--porcelain").decode().splitlines() != [" M src/compiler/custom_build.rs"]:
    raise RuntimeError("Unexpected source edits")
if git("diff", "--binary") != ORIGINAL.read_bytes():
    raise RuntimeError("Initial source differs from the saved build-output patch")
git("apply", "--reverse", str(ORIGINAL))
git("apply", str(UPSTREAM))
build("cargo-pr175-baseline-normal", [UPSTREAM])
git("apply", str(PATH_CACHE))
build("cargo-pr175-path-cache-normal", [UPSTREAM, PATH_CACHE])
git("apply", "--reverse", str(PATH_CACHE))
git("apply", "--reverse", str(UPSTREAM))
git("apply", str(ORIGINAL))
if git("diff", "--binary") != ORIGINAL.read_bytes():
    raise RuntimeError("Failed to restore the original source state")
print(f"{now()} source restored; matched sensitivity pair is ready", flush=True)
