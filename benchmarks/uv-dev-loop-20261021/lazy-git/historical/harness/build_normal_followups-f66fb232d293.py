#!/usr/bin/env python3
"""Build PR175+loader-v2 and PR175+lazy-Git after an explicit local lease.

Without --lease-granted this only prints the build plan. Frozen outputs are
never replaced. The shared source checkout is restored after each variant.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/ohm-cargo"
TARGET = ROOT / "work/cargo-build"
BINARIES = ROOT / "work/binaries"
LOGS = ROOT / "work/logs"
BASE = "5e5d271d763d7beb38b48755e22bd59e93f02b97"
ORIGINAL = ROOT / "work/patches/build-output-remap.patch"
UPSTREAM = ROOT / "work/production-build/pr175.patch"
LOADER = ROOT / "work/patches/loader-path-v2-final.patch"
LAZY_GIT = ROOT / "work/benchmark/patches/lazy-git-final-3707975b6b13.patch"
BUILD_COMMAND = ["cargo", "+1.99.0", "build", "--release", "--locked", "-p", "cargo", "-j16"]
PLAN = (
    ("cargo-pr175-loader-v2-normal", (UPSTREAM, LOADER)),
    ("cargo-pr175-lazy-git-normal", (UPSTREAM, LAZY_GIT)),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, env=None):
    return subprocess.check_output(["git", *args], cwd=SOURCE, env=env)


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def source_snapshot():
    # A temporary index captures new src/util/git.rs as well as tracked edits,
    # without changing the shared checkout's real index.
    with tempfile.TemporaryDirectory(prefix="followup-index-", dir=ROOT / "work/benchmark") as directory:
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        git("read-tree", "HEAD", env=environment)
        git("add", "--all", "--", ".", env=environment)
        return {
            "tree": git("write-tree", env=environment).decode().strip(),
            "patch": git("diff", "--cached", "--binary", "HEAD", env=environment),
        }


def assert_original():
    if git("rev-parse", "HEAD").decode().strip() != BASE:
        raise RuntimeError("Unexpected source base")
    if git("status", "--porcelain").decode().splitlines() != [" M src/compiler/custom_build.rs"]:
        raise RuntimeError("Unexpected source edits; the previous owner has not restored its checkout")
    if git("diff", "--binary") != ORIGINAL.read_bytes():
        raise RuntimeError("Source differs from the saved original build-output patch")


@contextmanager
def patched_source(patches):
    assert_original()
    git("apply", "--reverse", "--check", str(ORIGINAL))
    git("apply", "--reverse", str(ORIGINAL))
    applied = []
    expected = source_snapshot()["tree"]
    try:
        for patch in patches:
            git("apply", "--check", str(patch))
            git("apply", str(patch))
            applied.append(patch)
            expected = source_snapshot()["tree"]
        yield
    finally:
        if source_snapshot()["tree"] != expected:
            raise RuntimeError("Source changed unexpectedly; leaving it intact for inspection")
        for patch in reversed(applied):
            git("apply", "--reverse", "--check", str(patch))
            git("apply", "--reverse", str(patch))
        git("apply", "--check", str(ORIGINAL))
        git("apply", str(ORIGINAL))
        assert_original()
        print(f"{now()} original source restored", flush=True)


def matched_environment():
    environment = os.environ.copy()
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        if environment.get(name):
            raise RuntimeError(f"Unexpected {name}; refusing to change the matched build flags")
    environment.update(
        CARGO_HOME="/tmp/codex-cargo-home",
        CARGO_TARGET_DIR=str(TARGET),
        CARGO_PROFILE_RELEASE_DEBUG="1",
    )
    return environment


def build(name, patches):
    destination = BINARIES / name
    metadata_path = BINARIES / f"{name}.build.json"
    source_patch_path = BINARIES / f"{name}.source.patch"
    stripped = BINARIES / "stripped" / name
    for path in (destination, metadata_path, source_patch_path, stripped, stripped.with_name(name + ".json")):
        if path.exists():
            raise RuntimeError(f"Refusing to replace frozen output {path}")
    environment = matched_environment()
    before = source_snapshot()
    source_patch_path.write_bytes(before["patch"])
    metadata = {
        "name": name, "started_at": now(), "base_commit": BASE,
        "source_path": str(SOURCE), "target_path": str(TARGET),
        "source_tree": before["tree"], "source_diff_sha256": sha(before["patch"]),
        "source_patch": str(source_patch_path),
        "patch_sha256": {str(patch): sha(patch.read_bytes()) for patch in patches},
        "command": BUILD_COMMAND,
        "explicit_build_environment": {key: environment[key] for key in (
            "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_PROFILE_RELEASE_DEBUG")},
        "runner_sha256": sha(Path(__file__).read_bytes()), "pgo": False,
    }
    output = TARGET / "release/cargo"
    output.unlink(missing_ok=True)
    log = LOGS / f"build-{name}.log"
    print(f"{now()} building {name}", flush=True)
    with log.open("xb") as stream:
        result = subprocess.run(BUILD_COMMAND, cwd=SOURCE, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    metadata.update(finished_at=now(), returncode=result.returncode, log_sha256=sha(log.read_bytes()))
    write_json(metadata_path, metadata)
    if result.returncode:
        raise RuntimeError(f"Build failed; inspect {log}")
    after = source_snapshot()
    if after != before:
        raise RuntimeError("Source changed while compiling")
    with output.open("rb") as stream, destination.open("xb") as frozen:
        shutil.copyfileobj(stream, frozen)
    shutil.copystat(output, destination)
    metadata.update(sha256=sha(destination.read_bytes()), bytes=destination.stat().st_size)
    if sha(output.read_bytes()) != metadata["sha256"]:
        raise RuntimeError("Linker output changed while freezing the binary")
    write_json(metadata_path, metadata)
    manifest_path = BINARIES / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if name in manifest:
        raise RuntimeError("Frozen binary name already exists in manifest")
    manifest[name] = metadata
    write_json(manifest_path, manifest)
    # This existing helper verifies every allocated ELF section and preserves
    # the linker output while removing only debug sections from the copy.
    subprocess.run(["python3", str(ROOT / "work/benchmark/strip_binaries.py"), name], check=True)
    print(f"{now()} frozen and strip-verified {destination}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-granted", action="store_true")
    parser.add_argument("--only", choices=("loader", "git"))
    args = parser.parse_args()
    plans = PLAN if args.only is None else (PLAN[0 if args.only == "loader" else 1],)
    if not args.lease_granted:
        print(json.dumps({"status": "prepared; explicit parent lease required", "command": BUILD_COMMAND,
                          "source": str(SOURCE), "target": str(TARGET),
                          "variants": [{"name": name, "patches": [str(patch) for patch in patches]}
                                       for name, patches in plans]}, indent=2))
        return
    for name, patches in plans:
        with patched_source(patches):
            build(name, patches)


if __name__ == "__main__":
    main()
