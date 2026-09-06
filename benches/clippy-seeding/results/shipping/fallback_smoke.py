#!/usr/bin/env python3
"""Exercise production default and override policy on non-cloning HFS+ storage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path("/private/tmp/codex-cargo-targets/cargo/isolated/clippy-shipping-fallback")
EVIDENCE = Path(__file__).parent / "fallback"
CARGO = Path("/private/tmp/codex-cargo-targets/cargo/clippy-seeding/ohm/release/cargo")

def main():
    ROOT.mkdir(parents=True, exist_ok=False)
    EVIDENCE.mkdir(exist_ok=False)
    mount = ROOT / "volume"
    mount.mkdir()
    image = ROOT / "storage.sparsebundle"
    subprocess.run(["hdiutil", "create", "-size", "1g", "-type", "SPARSEBUNDLE", "-fs", "HFS+", "-volname", "OhmClippyFallback", str(image)], check=True, capture_output=True)
    subprocess.run(["hdiutil", "attach", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(image)], check=True, capture_output=True)
    sysroot = Path(subprocess.check_output(["rustc", "+ohm", "--print", "sysroot"], text=True).strip())
    env = dict(os.environ, CARGO_HOME="/private/tmp/codex-cargo-home", RUSTUP_TOOLCHAIN="ohm", RUSTC=str(sysroot / "bin/rustc"), CARGO=str(CARGO), CARGO_TARGET_DIR=str(mount / "target"), CARGO_BUILD_BUILD_DIR=str(mount / "shared"), PATH=os.pathsep.join([str(CARGO.parent), str(sysroot / "bin"), os.environ["PATH"]]))
    for key in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "CARGO_UNSTABLE_OHM_DEFAULTS", "CARGO_UNSTABLE_OHM_WORKTREE_SEEDS", "__CARGO_OHM_DEFAULTS", "__CARGO_OHM_WORKTREE_SEEDS", "__CARGO_OHM_CLIPPY_SEED_ISOLATION", "CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION"]:
        env.pop(key, None)
    receipt = {"cargo_version": subprocess.check_output([CARGO, "-Vv"], text=True), "cargo_sha256": hashlib.file_digest(CARGO.open("rb"), "sha256").hexdigest(), "filesystem": "HFS+", "scope": "correctness and non-clone default policy; no performance claim", "commands": []}
    def run(name, argv, cwd, current=env):
        r = subprocess.run(argv, cwd=cwd, env=current, capture_output=True, text=True)
        (EVIDENCE / (name + ".log")).write_text(r.stdout + r.stderr)
        receipt["commands"].append({"name": name, "argv": list(map(str, argv)), "returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr})
        (EVIDENCE / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        assert r.returncode == 0, r.stderr
        return r
    try:
        donor = mount / "donor"
        (donor / "src").mkdir(parents=True)
        (donor / "Cargo.toml").write_text('[package]\nname="clippy_fallback"\nversion="0.1.0"\nedition="2024"\n')
        (donor / "src/lib.rs").write_text('pub fn value() -> u32 { 42 }\n')
        (donor / ".gitignore").write_text('/Cargo.lock\n')
        run("init", ["git", "init"], donor)
        run("add", ["git", "add", "."], donor)
        run("commit", ["git", "-c", "user.name=Benchmark", "-c", "user.email=benchmark@example.invalid", "-c", "commit.gpgsign=false", "commit", "-m", "fixture"], donor)
        run("build", [CARGO, "build", "--offline"], donor)
        before = run("fork-before-clippy", [CARGO, "worktree", "add", "--detach", mount / "probe", "--target-dir", mount / "probe-target"], donor)
        assert ", 0 reflinked files)" in before.stderr
        run("default-clippy", [CARGO, "clippy", "--offline", "--", "-D", "warnings"], donor)
        shared = mount / "shared"
        assert not list(shared.rglob(".ohm-clippy-v1"))
        denied = list(shared.rglob(".ohm-worktree-seed-deny-v7"))
        assert denied
        after = run("fork-after-clippy", [CARGO, "worktree", "add", "--detach", mount / "child", "--target-dir", mount / "child-target"], donor)
        assert "no compatible build snapshot seeded" in after.stderr
        forced = dict(env, CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION="true")
        run("forced-clippy", [CARGO, "clippy", "--offline", "--", "-D", "warnings"], donor, forced)
        assert list(shared.rglob(".ohm-clippy-v1"))
        assert all(path.is_file() for path in denied)
        assert not list(shared.rglob(".ohm-clone-probe-*"))
        receipt.update(complete=True, no_reflinks=True, default_isolated=False, default_denied=True, forced_isolated=True, previous_denial_preserved=True, probe_residue=False)
        (EVIDENCE / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    finally:
        r = subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True, text=True)
        (EVIDENCE / "detach.log").write_text(r.stdout + r.stderr)
        assert r.returncode == 0, r.stderr
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
