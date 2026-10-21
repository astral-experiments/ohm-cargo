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

ROOT = Path("/tmp/ohm-hillclimb-20261021-inheritance-production")
SOURCE = ROOT / "source"
PINNED = "5e5d271d763d7beb38b48755e22bd59e93f02b97"
TREE = "f359174bb51dd7adb6a6e94dac43661d27086193"
TOOLCHAIN = Path("/home/dev-user/.rustup/toolchains/1.99.0-x86_64-unknown-linux-gnu")
VARIANTS = (('inheritance-stack180-baseline', ('stack180-baseline.patch',)), ('inheritance-stack180-shared', ('stack180-shared.patch',)))
PATCH_HASHES = {'stack180-baseline.patch': 'c6903b9c8d161553d8993b35744186a840163431f2da741c516bd12ae11b6435', 'stack180-shared.patch': 'e03566d5109989053f94721ac430527f10b6ff079fb8dc03cb6ce8e139d8f086'}
EXPECTED_TREES = {'inheritance-stack180-baseline': '0a392258c801cff734d223a3f9af73d5b5a4e3c0', 'inheritance-stack180-shared': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e'}
STRIP_HELPER_SHA256 = "67d6f781d1e77bbc4f9111e88589fdf0819d19c6073592b422ad832a7c41f6a1"


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
             "clang", "clang++", "make", "ninja", "ld", "ld.lld", "collect2",
             "valgrind", "perf", "hyperfine"}
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
        benchmark = any(arg.endswith(("/controller/launch-linux.py", "/controller/run-suite.py",
                        "/paired.py", "/paired_repeated.py", "/loader_fixture.py")) for arg in arguments)
        if executable in names or executable.startswith(("callgrind-", "cachegrind-")) or benchmark:
            busy.append({"pid": int(entry.name), "executable": arguments[0],
                         "benchmark_controller": benchmark})
    return {"at": now(), "load_average": list(os.getloadavg()), "other_workloads": busy}


def current_source_tree():
    index_path = ROOT / "tmp" / "host2-inheritance-stack180.working-source.index"
    if index_path.exists():
        raise RuntimeError("working source verification index already exists")
    index_environment = os.environ.copy()
    index_environment["GIT_INDEX_FILE"] = str(index_path)
    try:
        subprocess.run(["git", "-C", str(SOURCE), "read-tree", PINNED], env=index_environment, check=True)
        subprocess.run(["git", "-C", str(SOURCE), "add", "--all"], env=index_environment, check=True)
        return output(["git", "-C", str(SOURCE), "write-tree"], env=index_environment)
    finally:
        index_path.unlink(missing_ok=True)


def verify_common_inputs(provenance, environment):
    observed = {}
    for key in ("compiler_input_sha256", "native_build_tool_sha256"):
        observed[key] = {name: sha(name) for name in provenance[key]}
        if observed[key] != provenance[key]:
            raise RuntimeError(f"frozen build tools changed: {key}")
    observed["inherited_cargo_configuration_sha256"] = {
        str(path): sha(path) for path in (Path("/.cargo/config.toml"), Path("/tmp/.cargo/config.toml"))
        if path.is_file()
    }
    observed["execution_environment_sha256"] = hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode()).hexdigest()
    for key in ("inherited_cargo_configuration_sha256", "execution_environment_sha256"):
        if observed[key] != provenance[key]:
            raise RuntimeError(f"frozen execution inputs changed: {key}")
    observed["command"] = provenance["command"]
    observed["environment"] = provenance["environment"]
    return hashlib.sha256(json.dumps(observed, sort_keys=True).encode()).hexdigest()



def relocated_reference(value):
    """Compare the original reference after relocating this owned build root."""
    old = "/tmp/ohm-hillclimb-20261021-production"
    new = "/tmp/ohm-hillclimb-20261021-inheritance-production"
    if isinstance(value, str) and (value == old or value.startswith(old + "/")):
        return new + value[len(old):]
    if isinstance(value, dict):
        return {key: relocated_reference(item) for key, item in value.items()}
    if isinstance(value, list):
        return [relocated_reference(item) for item in value]
    return value


def main():
    if ROOT.resolve() != ROOT or Path(__file__).resolve().parent != ROOT:
        raise RuntimeError("driver must remain in the authorized task directory")
    owner = json.loads((ROOT / "ownership-host2-inheritance-stack180.json").read_text())
    expected_owner = {"cohort": "host2-inheritance-stack180", "root": str(ROOT), "uid": os.getuid(),
                      "inputs_sha256": sha(ROOT / "host2-inheritance-stack180-inputs.json")}
    if owner != expected_owner or ROOT.stat().st_uid != os.getuid() or SOURCE.resolve() != SOURCE:
        raise RuntimeError("production root ownership or source path differs from the frozen task")
    for name in ("status-host2-inheritance-stack180.json", "provenance-host2-inheritance-stack180.json"):
        if (ROOT / name).exists():
            raise RuntimeError(f"refusing to overwrite an earlier attempt: {name}")
    occupied = occupancy()
    if occupied["other_workloads"]:
        raise RuntimeError(f"host is occupied: {occupied}")
    for variant, _ in VARIANTS:
        paths = [ROOT / "binaries" / f"cargo-{variant}",
                 ROOT / "binaries/stripped" / f"cargo-{variant}",
                 ROOT / "binaries/stripped" / f"cargo-{variant}.json"]
        paths += [ROOT / "logs" / f"{variant}.{suffix}"
                  for suffix in ("stdout", "stderr", "source.patch", "occupancy.json")]
        if any(path.exists() for path in paths):
            raise RuntimeError(f"refusing to overwrite existing variant evidence: {variant}")
    if sha(ROOT / "tools/strip_binaries.py") != STRIP_HELPER_SHA256:
        raise RuntimeError("strip helper differs from frozen helper")
    if current_source_tree() != TREE:
        raise RuntimeError("initial source differs from the pinned source bundle")
    previous_manifest = {}
    preserved_paths = [ROOT / filename for filename in (
        "reference-host7-provenance.json", "pinned.bundle", "stack180-baseline.patch", "stack180-shared.patch",
        "host2-inheritance-stack180-inputs.json", "ownership-host2-inheritance-stack180.json", "build_driver_host2_inheritance_stack180.py", "tools/strip_binaries.py")]
    preserved_artifacts = {str(path.relative_to(ROOT)): sha(path) for path in preserved_paths}
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
    provenance["upstream_patch_commit"] = "c40676e264501bc8a93095d3a273a1c300b80875"
    provenance["expected_variant_source_trees"] = EXPECTED_TREES
    provenance["strip_helper_sha256"] = STRIP_HELPER_SHA256
    provenance["frozen_input_manifest_sha256"] = sha(ROOT / "host2-inheritance-stack180-inputs.json")
    provenance["preserved_artifact_sha256"] = preserved_artifacts
    provenance["source_import"] += "; exact current180/shared-workspace-dependencies patches atop pinned HEAD keeps embedded identity fixed"
    original_provenance = json.loads((ROOT / "reference-host7-provenance.json").read_text())
    for key in ("source", "target", "source_commit", "source_tree", "source_bundle_sha256",
                "compiler_input_sha256", "rustc_version", "cargo_version", "cc_version", "environment",
                "command", "inherited_cargo_configuration_sha256", "inherited_native_build_environment",
                "affinity", "approximation"):
        if provenance[key] != relocated_reference(original_provenance[key]):
            raise RuntimeError(f"production build inputs changed since original batch: {key}")
    if provenance["host"] != "charlie-oss-2":
        raise RuntimeError("this frozen cohort is restricted to host2")
    provenance["reference_path_relocation"] = {"from": '/tmp/ohm-hillclimb-20261021-production', "to": '/tmp/ohm-hillclimb-20261021-inheritance-production'}
    provenance["cohort"] = "host2-inheritance-stack180"
    provenance["reference_host7_provenance_sha256"] = sha(ROOT / "reference-host7-provenance.json")
    provenance["native_build_tool_sha256"] = {
        name: sha(name) for name in ("/usr/bin/cc", "/usr/bin/ar", "/usr/bin/ld",
                                   "/usr/bin/ranlib", "/usr/bin/as", "/usr/bin/make", "/usr/bin/perl")
    }
    provenance["execution_environment_sha256"] = hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode()).hexdigest()
    common_input_identity = verify_common_inputs(provenance, environment)
    provenance["common_build_inputs_sha256"] = common_input_identity
    save(ROOT / "provenance-host2-inheritance-stack180.json", provenance)
    binary_manifest = {}
    sealed_artifacts = {}
    status = {"state": "preparing", "started_at": now(), "completed_variants": []}
    save(ROOT / "status-host2-inheritance-stack180.json", status)
    try:
        for variant, patches in VARIANTS:
            occupied = occupancy()
            save(ROOT / "logs" / f"{variant}.occupancy.json", occupied)
            if occupied["other_workloads"]:
                status.update(state="blocked-by-occupancy", variant=variant, occupancy=occupied)
                save(ROOT / "status-host2-inheritance-stack180.json", status)
                return 2
            if verify_common_inputs(provenance, environment) != common_input_identity:
                raise RuntimeError("non-candidate build inputs changed between variants")
            for filename, expected_hash in sealed_artifacts.items():
                if sha(ROOT / filename) != expected_hash:
                    raise RuntimeError(f"completed artifact changed before the next build: {filename}")
            subprocess.run(["git", "-C", str(SOURCE), "reset", "--hard", PINNED], check=True)
            for patch in patches:
                subprocess.run(["git", "-C", str(SOURCE), "apply", "--check", str(ROOT / patch)], check=True)
                subprocess.run(["git", "-C", str(SOURCE), "apply", str(ROOT / patch)], check=True)
            subprocess.run(["git", "-C", str(SOURCE), "add", "--intent-to-add", "--all"], check=True)
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
                if observed_tree != EXPECTED_TREES[variant]:
                    raise RuntimeError(f"source differs from the independently frozen tree: {variant}")
                expected_diff = subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--cached", "--binary", "--full-index"], env=index_environment)
                subprocess.run(["git", "-C", str(SOURCE), "add", "--all"], env=index_environment, check=True)
                working_tree = output(["git", "-C", str(SOURCE), "write-tree"], env=index_environment)
                diff = subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--cached", "--binary", "--full-index"], env=index_environment)
                if working_tree != observed_tree:
                    raise RuntimeError(f"working source tree differs from frozen patches: {variant}")
            finally:
                index_path.unlink(missing_ok=True)
            if diff != expected_diff:
                raise RuntimeError(f"working source differs from frozen patches: {variant}")
            (ROOT / "logs" / f"{variant}.source.patch").write_bytes(diff)
            status.update(state="building", variant=variant, variant_started_at=now())
            save(ROOT / "status-host2-inheritance-stack180.json", status)
            started = time.monotonic_ns()
            with (ROOT / "logs" / f"{variant}.stdout").open("wb") as stdout, \
                    (ROOT / "logs" / f"{variant}.stderr").open("wb") as stderr:
                result = subprocess.run(command, cwd=SOURCE, env=environment, stdout=stdout, stderr=stderr)
            if result.returncode:
                raise RuntimeError(f"{variant} build failed with exit {result.returncode}")
            if current_source_tree() != EXPECTED_TREES[variant]:
                raise RuntimeError("source changed during compilation")
            if verify_common_inputs(provenance, environment) != common_input_identity:
                raise RuntimeError("non-candidate build inputs changed during compilation")
            linked = ROOT / "target/release/cargo"
            destination = ROOT / "binaries" / f"cargo-{variant}"
            shutil.copy2(linked, destination)
            original_hash = sha(linked)
            if sha(destination) != original_hash:
                raise RuntimeError("copied binary differs from linker output")
            record = {
                "variant": variant, "common_build_inputs_sha256": common_input_identity, "built_at": now(), "elapsed_build_seconds": (time.monotonic_ns() - started) / 1e9,
                "original_linker_output_sha256": original_hash, "path": str(destination),
                "bytes": destination.stat().st_size, "patch_sha256": {patch: PATCH_HASHES[patch] for patch in patches},
                "observed_source_tree": working_tree, "expected_source_tree_from_patches": observed_tree,
                "embedded_source_commit": PINNED,
                "upstream_patch_commit": "c40676e264501bc8a93095d3a273a1c300b80875",
                "observed_diff_sha256": hashlib.sha256(diff).hexdigest(),
                "version": output([str(destination), "-Vv"], env=environment),
                "dynamic_libraries": output(["/usr/bin/ldd", str(destination)], env=environment),
                "stdout_sha256": sha(ROOT / "logs" / f"{variant}.stdout"),
                "stderr_sha256": sha(ROOT / "logs" / f"{variant}.stderr"),
            }
            if any(binary_manifest.get(name) != old for name, old in previous_manifest.items()):
                raise RuntimeError("previous manifest records changed")
            binary_manifest[destination.name] = record
            save(ROOT / "binaries/manifest.json", binary_manifest)
            subprocess.run([sys.executable, str(ROOT / "tools/strip_binaries.py"), destination.name], check=True)
            for filename in (f"binaries/cargo-{variant}",
                             f"binaries/stripped/cargo-{variant}",
                             f"binaries/stripped/cargo-{variant}.json",
                             f"logs/{variant}.stdout", f"logs/{variant}.stderr",
                             f"logs/{variant}.source.patch", f"logs/{variant}.occupancy.json"):
                sealed_artifacts[filename] = sha(ROOT / filename)
            previous_manifest = dict(binary_manifest)
            status["completed_variants"].append(variant)
            save(ROOT / "status-host2-inheritance-stack180.json", status)
        for filename, expected in preserved_artifacts.items():
            if sha(ROOT / filename) != expected:
                raise RuntimeError(f"previous artifact changed: {filename}")
        for filename, expected_hash in sealed_artifacts.items():
            if sha(ROOT / filename) != expected_hash:
                raise RuntimeError(f"completed artifact changed during the batch: {filename}")
        status["sealed_artifact_sha256"] = sealed_artifacts
        status["preserved_artifacts_verified"] = len(preserved_artifacts)
        status.update(state="complete", finished_at=now())
        save(ROOT / "status-host2-inheritance-stack180.json", status)
        return 0
    except BaseException as error:
        status.update(state="failed", error=repr(error), finished_at=now())
        save(ROOT / "status-host2-inheritance-stack180.json", status)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
