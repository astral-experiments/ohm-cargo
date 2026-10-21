#!/usr/bin/env python3
"""Build matched Cargo variants in the one authorized task directory."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path("/tmp/ohm-hillclimb-20261021-production")
SOURCE = ROOT / "source"
PINNED = "5e5d271d763d7beb38b48755e22bd59e93f02b97"
TREE = "f359174bb51dd7adb6a6e94dac43661d27086193"
TOOLCHAIN = Path("/home/dev-user/.rustup/toolchains/1.99.0-x86_64-unknown-linux-gnu")
VARIANTS = (("pr175-path-cache", ("pr175.patch", "path-cache.patch")),)
PATCH_HASHES = {
    "pr175.patch": "30332415e2fdc6735719868cddeeb717cc856415f8cd1731ab5696c109f697dc",
    "path-cache.patch": "0ad07b5922f9fdd60f772368e8621c679f1fb0163c245fdd484aee58cd599bb0",
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def output(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def occupancy():
    busy = []
    names = {"cargo", "rustc", "cargo-nextest", "cc1", "cc1plus", "gcc", "g++",
             "clang", "clang++", "make", "ninja", "ld", "ld.lld", "collect2"}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            arguments = [os.fsdecode(arg) for arg in arguments if arg]
        except (OSError, PermissionError):
            continue
        if not arguments:
            continue
        executable = Path(arguments[0]).name
        benchmark = any("/controller/launch-linux.py" in arg or
                        "/controller/run-suite.py" in arg for arg in arguments)
        if executable in names or benchmark:
            busy.append({"pid": int(entry.name), "executable": arguments[0],
                         "benchmark_controller": benchmark})
    return {"at": now(), "load_average": list(os.getloadavg()), "other_workloads": busy}


def main():
    if ROOT.resolve() != ROOT or Path(__file__).resolve().parent != ROOT:
        raise RuntimeError("driver must remain in the authorized task directory")
    for name in ("logs", "binaries", "cargo-home", "tmp", "tools"):
        (ROOT / name).mkdir(exist_ok=True)
    if output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]) != PINNED:
        raise RuntimeError("source is not the exact pinned commit")
    if output(["git", "-C", str(SOURCE), "rev-parse", "HEAD^{tree}"]) != TREE:
        raise RuntimeError("pinned tree identity changed")
    for filename, expected in PATCH_HASHES.items():
        if sha(ROOT / filename) != expected:
            raise RuntimeError(f"frozen patch changed: {filename}")

    environment = os.environ.copy()
    cleared = sorted(key for key in environment if key.startswith(("RUST", "CARGO_PROFILE_", "CARGO_UNSTABLE_")))
    cleared += ["CARGO_ENCODED_RUSTFLAGS", "CARGO_ENCODED_RUSTDOCFLAGS", "CARGO_BUILD_TARGET",
                "CARGO_BUILD_RUSTC", "CARGO_BUILD_RUSTC_WRAPPER", "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER",
                "CARGO_BUILD_BUILD_DIR", "CARGO_LOG", "CARGO_LOG_PROFILE", "CFG_OMIT_GIT_HASH",
                "LLVM_PROFILE_FILE"]
    for key in cleared:
        environment.pop(key, None)
    settings = {
        "CARGO_HOME": str(ROOT / "cargo-home"), "CARGO_TARGET_DIR": str(ROOT / "target"),
        "RUSTC": str(TOOLCHAIN / "bin/rustc"), "RUSTDOC": str(TOOLCHAIN / "bin/rustdoc"),
        "PATH": str(TOOLCHAIN / "bin") + ":/usr/bin:/bin",
        "CARGO_BUILD_JOBS": "8", "CARGO_INCREMENTAL": "0", "CARGO_TERM_COLOR": "never",
        "CARGO_PROFILE_RELEASE_LTO": "thin", "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "1",
        "CARGO_PROFILE_RELEASE_DEBUG": "1", "CARGO_PROFILE_RELEASE_OPT_LEVEL": "3",
        "CARGO_PROFILE_RELEASE_INCREMENTAL": "false", "CARGO_PROFILE_RELEASE_STRIP": "none",
        "CFG_RELEASE_CHANNEL": "dev", "LIBZ_SYS_STATIC": "1", "TMPDIR": str(ROOT / "tmp"),
        "SSL_CERT_FILE": "/etc/ssl/certs/ca-certificates.crt", "SSL_CERT_DIR": "/usr/lib/ssl/certs",
    }
    environment.update(settings)
    command = [str(TOOLCHAIN / "bin/cargo"), "build", "--release", "--locked", "--bin", "cargo",
               "--features", "all-static,ohm-defaults", "-j", "8", "-v"]
    recorded = [TOOLCHAIN / "bin/rustc", TOOLCHAIN / "bin/cargo", TOOLCHAIN / "bin/rustdoc"]
    recorded += list((TOOLCHAIN / "lib").glob("librustc_driver-*.so"))
    provenance = {
        "created_at": now(), "host": output(["hostname"]), "source": str(SOURCE),
        "target": str(ROOT / "target"), "source_commit": PINNED, "source_tree": TREE,
        "source_import": "Exact local pinned Git bundle, preserving its existing shallow boundary",
        "source_bundle_sha256": sha(ROOT / "pinned.bundle"), "patch_sha256": PATCH_HASHES,
        "driver_sha256": sha(__file__), "command": command, "environment": settings,
        "cleared_environment_names": sorted(set(cleared)),
        "rustc_version": output([settings["RUSTC"], "-Vv"], env=environment),
        "cargo_version": output([str(TOOLCHAIN / "bin/cargo"), "-Vv"], env=environment),
        "compiler_input_sha256": {str(path): sha(path) for path in recorded},
        "inherited_cargo_configuration_sha256": {
            str(path): sha(path) for path in (Path("/.cargo/config.toml"), Path("/tmp/.cargo/config.toml"))
            if path.is_file()
        },
        "inherited_native_build_environment": {
            key: environment.get(key) for key in ("CC", "CXX", "AR", "RANLIB", "CFLAGS", "CXXFLAGS",
                "CPPFLAGS", "LDFLAGS", "OPENSSL_NO_VENDOR", "OPENSSL_DIR", "OPENSSL_LIB_DIR",
                "OPENSSL_INCLUDE_DIR", "OPENSSL_STATIC", "LIBGIT2_NO_VENDOR", "LD_LIBRARY_PATH",
                "LD_PRELOAD", "LD_AUDIT")
        },
        "cc_version": output(["/usr/bin/cc", "--version"]),
        "kernel": output(["uname", "-a"]), "cpu_count": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "approximation": "Production feature/static/ThinLTO/CU1/dev-channel settings; no PGO; "
                         "stock Rust 1.99.0 instead of release bootstrap stage1; debug=1 retained "
                         "then removed with allocated-section invariance verification",
    }
    provenance["upstream_patch_commit"] = "efc8b51502f8a8d1fe76997dc984481edde2740e"
    provenance["source_import"] += "; exact PR175 patch atop pinned HEAD keeps embedded identity fixed"
    original_provenance = json.loads((ROOT / "provenance.json").read_text())
    for key in ("environment", "command", "compiler_input_sha256", "inherited_cargo_configuration_sha256",
                "inherited_native_build_environment", "source_commit", "source_tree", "target", "source"):
        if provenance[key] != original_provenance[key]:
            raise RuntimeError(f"production build inputs changed since original batch: {key}")
    if json.loads((ROOT / "status.json").read_text())["state"] != "complete":
        raise RuntimeError("original fixed build sequence has not completed")
    for prior_status in ("status-pr175.json", "status-pr175-lazy-git.json"):
        if json.loads((ROOT / prior_status).read_text())["state"] != "complete":
            raise RuntimeError(f"prior production sequence has not completed: {prior_status}")
    save(ROOT / "provenance-pr175-path-cache.json", provenance)
    binary_manifest = json.loads((ROOT / "binaries/manifest.json").read_text())
    status = {"state": "preparing", "started_at": now(), "completed_variants": []}
    save(ROOT / "status-pr175-path-cache.json", status)
    try:
        for variant, patches in VARIANTS:
            occupied = occupancy()
            save(ROOT / "logs" / f"{variant}.occupancy.json", occupied)
            if occupied["other_workloads"]:
                status.update(state="blocked-by-occupancy", variant=variant, occupancy=occupied)
                save(ROOT / "status-pr175-path-cache.json", status)
                return 2
            subprocess.run(["git", "-C", str(SOURCE), "reset", "--hard", PINNED], check=True)
            for patch in patches:
                subprocess.run(["git", "-C", str(SOURCE), "apply", "--check", str(ROOT / patch)], check=True)
                subprocess.run(["git", "-C", str(SOURCE), "apply", str(ROOT / patch)], check=True)
            index_path = ROOT / "tmp" / f"{variant}.source.index"
            if index_path.exists():
                raise RuntimeError(f"source-tree verification index already exists: {index_path}")
            index_environment = os.environ.copy()
            index_environment["GIT_INDEX_FILE"] = str(index_path)
            try:
                subprocess.run(["git", "-C", str(SOURCE), "read-tree", PINNED], env=index_environment, check=True)
                for patch in patches:
                    subprocess.run(["git", "-C", str(SOURCE), "apply", "--cached", str(ROOT / patch)], env=index_environment, check=True)
                observed_tree = output(["git", "-C", str(SOURCE), "write-tree"], env=index_environment)
                expected_diff = subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--cached", "--binary"], env=index_environment)
                subprocess.run(["git", "-C", str(SOURCE), "add", "--all"], env=index_environment, check=True)
                working_tree = output(["git", "-C", str(SOURCE), "write-tree"], env=index_environment)
                diff = subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--cached", "--binary"], env=index_environment)
                if working_tree != observed_tree:
                    raise RuntimeError(f"working source tree differs from frozen patches: {variant}")
            finally:
                index_path.unlink(missing_ok=True)
            if diff != expected_diff:
                raise RuntimeError(f"working source differs from frozen patches: {variant}")
            (ROOT / "logs" / f"{variant}.source.patch").write_bytes(diff)
            status.update(state="building", variant=variant, variant_started_at=now())
            save(ROOT / "status-pr175-path-cache.json", status)
            started = time.monotonic_ns()
            with (ROOT / "logs" / f"{variant}.stdout").open("wb") as stdout, \
                    (ROOT / "logs" / f"{variant}.stderr").open("wb") as stderr:
                result = subprocess.run(command, cwd=SOURCE, env=environment, stdout=stdout, stderr=stderr)
            if result.returncode:
                raise RuntimeError(f"{variant} build failed with exit {result.returncode}")
            linked = ROOT / "target/release/cargo"
            destination = ROOT / "binaries" / f"cargo-{variant}"
            shutil.copy2(linked, destination)
            original_hash = sha(linked)
            if sha(destination) != original_hash:
                raise RuntimeError("copied binary differs from linker output")
            record = {
                "variant": variant, "built_at": now(), "elapsed_build_seconds": (time.monotonic_ns() - started) / 1e9,
                "original_linker_output_sha256": original_hash, "path": str(destination),
                "bytes": destination.stat().st_size, "patch_sha256": {patch: PATCH_HASHES[patch] for patch in patches},
                "observed_source_tree": working_tree, "expected_source_tree_from_patches": observed_tree,
                "embedded_source_commit": PINNED,
                "upstream_patch_commit": "efc8b51502f8a8d1fe76997dc984481edde2740e",
                "observed_diff_sha256": hashlib.sha256(diff).hexdigest(),
                "version": output([str(destination), "-Vv"], env=environment),
                "dynamic_libraries": output(["/usr/bin/ldd", str(destination)], env=environment),
                "stdout_sha256": sha(ROOT / "logs" / f"{variant}.stdout"),
                "stderr_sha256": sha(ROOT / "logs" / f"{variant}.stderr"),
            }
            binary_manifest[destination.name] = record
            save(ROOT / "binaries/manifest.json", binary_manifest)
            subprocess.run([sys.executable, str(ROOT / "tools/strip_binaries.py"), destination.name], check=True)
            status["completed_variants"].append(variant)
            save(ROOT / "status-pr175-path-cache.json", status)
        status.update(state="complete", finished_at=now())
        save(ROOT / "status-pr175-path-cache.json", status)
        return 0
    except BaseException as error:
        status.update(state="failed", error=repr(error), finished_at=now())
        save(ROOT / "status-pr175-path-cache.json", status)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
