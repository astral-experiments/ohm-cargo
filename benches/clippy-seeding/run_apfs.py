#!/usr/bin/env python3
"""Run an off/on/on/off Ruff workflow on fresh, isolated APFS volumes."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import plistlib
import platform
import resource
import struct
import subprocess
import time

BASE = "1edf9fe2cab23e34c383419b8c7830324c428a58"
EDIT = "0ecff877901a0377ad966ffab528488ce872b50e"
LIBC = ctypes.CDLL(None, use_errno=True)


class AttrList(ctypes.Structure):
    _fields_ = [("bitmapcount", ctypes.c_uint16), ("reserved", ctypes.c_uint16),
                ("commonattr", ctypes.c_uint32), ("volattr", ctypes.c_uint32),
                ("dirattr", ctypes.c_uint32), ("fileattr", ctypes.c_uint32),
                ("forkattr", ctypes.c_uint32)]


def allocation(mount):
    attrs = AttrList(bitmapcount=5, commonattr=0x80000000, volattr=0x80800000)
    buffer = ctypes.create_string_buffer(256)
    result = LIBC.getattrlist(os.fsencode(mount), ctypes.byref(attrs), buffer, len(buffer), 0x21)
    if result:
        raise OSError(ctypes.get_errno(), "getattrlist failed")
    returned = struct.unpack_from("=5I", buffer, 4)
    assert returned[1] & 0x00800000, "ATTR_VOL_SPACEUSED unavailable"
    used = struct.unpack_from("=q", buffer, 24)[0]
    stat = os.statvfs(mount)
    return {"volume_used_bytes": used,
            "container_used_bytes": (stat.f_blocks - stat.f_bfree) * stat.f_frsize}


def measure(mount):
    assert os.path.ismount(mount)
    groups = {}
    for root in [mount / "shared", mount / "targets"]:
        for parent, _, names in os.walk(root):
            for name in names:
                path = Path(parent) / name
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                kind = "query-cache" if name == "query-cache.bin" else path.suffix if path.suffix in {".rlib", ".rmeta", ".o"} else "other"
                group = groups.setdefault(kind, {"files": 0, "logical_bytes": 0, "inode_allocated_clone_unaware_bytes": 0})
                group["files"] += 1
                group["logical_bytes"] += stat.st_size
                group["inode_allocated_clone_unaware_bytes"] += stat.st_blocks * 512
    result = LIBC.sync_volume_np(os.fsencode(mount), 3)
    if result:
        raise OSError(ctypes.get_errno() if result == -1 else result, "volume sync failed")
    samples = []
    for _ in range(25):
        samples.append(allocation(mount))
        if len(samples) >= 3 and samples[-1] == samples[-2] == samples[-3]:
            return dict(samples[-1], stable=True, samples=samples, artifact_groups=groups)
        time.sleep(0.2)
    raise RuntimeError(f"APFS allocation did not stabilize: {samples}")


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--ruff", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--jobs", default="4")
    parser.add_argument("--toolchain", default="ohm")
    parser.add_argument("--arms", default="off1,on1,on2,off2")
    parser.add_argument("--production", action="store_true",
                        help="compare automatic production defaults with explicit isolation=false")
    parser.add_argument("--require-quiet", action="store_true",
                        help="reject external Rust processes before and after every command")
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    assert args.cargo.is_file() and args.ruff.is_dir()
    sysroot = Path(subprocess.check_output(["rustc", "+" + args.toolchain, "--print", "sysroot"], text=True).strip())
    toolchain = {"rustc_version": subprocess.check_output([str(sysroot / "bin/rustc"), "-vV"], text=True),
                 "clippy_sha256": sha256(sysroot / "bin/clippy-driver"),
                 "driver_sha256": {path.name: sha256(path) for path in (sysroot / "lib").glob("librustc_driver-*.dylib")}}
    for label in args.arms.split(","):
        enabled = label.startswith("on")
        root = args.root / label
        root.mkdir(parents=True, exist_ok=False)
        evidence = args.evidence / label
        evidence.mkdir(exist_ok=False)
        mount = root / "volume"
        mount.mkdir()
        image = root / "storage.sparsebundle"
        subprocess.run(["hdiutil", "create", "-size", "24g", "-type", "SPARSEBUNDLE", "-fs", "APFS",
                        "-volname", "OhmClippy-" + label, str(image)], check=True, capture_output=True)
        attached = subprocess.check_output(["hdiutil", "attach", "-nobrowse", "-noautoopen", "-mountpoint",
                                            str(mount), "-plist", str(image)])
        (mount / ".metadata_never_index").touch()
        (mount / ".fseventsd").mkdir(exist_ok=True)
        (mount / ".fseventsd/no_log").touch()
        donor = mount / "donor"
        child = mount / "child"
        env = dict(os.environ, CARGO_HOME="/private/tmp/codex-cargo-home", RUSTUP_TOOLCHAIN=args.toolchain,
                   RUSTC=str(sysroot / "bin/rustc"), CARGO=str(args.cargo), CARGO_BUILD_JOBS=args.jobs,
                   CARGO_TARGET_DIR=str(mount / "targets/donor"), CARGO_BUILD_BUILD_DIR=str(mount / "shared"),
                   CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all", CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
                   CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION=str(int(enabled)), INSTA_UPDATE="no",
                   CARGO_PROFILE_DEV_DEBUG="line-tables-only", CARGO_PROFILE_DEV_OPT_LEVEL="1",
                   CARGO_PROFILE_DEV_LTO="off", PATH=os.pathsep.join([str(args.cargo.parent), str(sysroot / "bin"), os.environ["PATH"]]))
        for variable in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                         "CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION", "CARGO_UNSTABLE_OHM_WORKTREE_SEEDS",
                         "CARGO_UNSTABLE_OHM_DEFAULTS", "__CARGO_OHM_DEFAULTS", "__CARGO_OHM_WORKTREE_SEEDS",
                         "__CARGO_OHM_CLIPPY_SEED_ISOLATION"]:
            env.pop(variable, None)
        if args.production:
            env.pop("CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION", None)
            if not enabled:
                env["CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION"] = "false"
        receipt = {"label": label, "enabled": enabled, "base": BASE, "edit": EDIT,
                   "production": args.production, "require_quiet": args.require_quiet,
                   "harness_sha256": sha256(Path(__file__)),
                   "cargo_version": subprocess.check_output([str(args.cargo), "-Vv"], text=True),
                   "cargo_sha256": sha256(args.cargo), "rustc_sha256": sha256(sysroot / "bin/rustc"),
                   "source_root": str(args.ruff), "volume": str(mount), "attach": plistlib.loads(attached),
                   "environment": {key: env.get(key) for key in ["CARGO_HOME", "RUSTUP_TOOLCHAIN", "RUSTC", "CARGO",
                       "CARGO_BUILD_JOBS", "CARGO_TARGET_DIR", "CARGO_BUILD_BUILD_DIR", "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST",
                       "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", "CARGO_EXPERIMENTAL_CLIPPY_SEED_ISOLATION",
                       "CARGO_UNSTABLE_OHM_CLIPPY_SEED_ISOLATION",
                       "CARGO_PROFILE_DEV_DEBUG", "CARGO_PROFILE_DEV_OPT_LEVEL", "CARGO_PROFILE_DEV_LTO"]},
                   "commands": [], "measurements": {}, "toolchain": toolchain,
                   "machine": {"platform": platform.platform(), "cpu_count": os.cpu_count()},
                   "timing_caveat": ("External Rust processes checked before/after commands; ordinary host activity remains."
                                      if args.require_quiet else "Other development workloads were active; use as a storage screen, not a precise wall-time speedup.")}
        def save():
            (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        def quiet_snapshot():
            rows = []
            output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pcpu=,comm="], text=True)
            for line in output.splitlines():
                pid, ppid, cpu, executable = line.split(None, 3)
                if int(pid) == os.getpid() or Path(executable).name == "ps":
                    continue
                rust = Path(executable).name in {"cargo", "rustc", "clippy-driver", "cargo-clippy"}
                if rust or float(cpu) >= 20:
                    rows.append({"pid": int(pid), "ppid": int(ppid), "cpu_percent": float(cpu),
                                 "executable": executable, "rust": rust})
            return rows

        def command(name, argv, cwd, environment=env):
            entry = {"name": name, "argv": list(map(str, argv)), "cwd": str(cwd)}
            if args.require_quiet:
                entry["processes_before"] = quiet_snapshot()
                assert not any(row["rust"] for row in entry["processes_before"]), entry["processes_before"]
            receipt["commands"].append(entry)
            save()
            usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = time.monotonic()
            with (evidence / (name + ".log")).open("xb") as log:
                process = subprocess.run(argv, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT)
            usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            entry.update(elapsed_seconds=time.monotonic() - start, returncode=process.returncode,
                         child_user_seconds=usage_after.ru_utime - usage_before.ru_utime,
                         child_system_seconds=usage_after.ru_stime - usage_before.ru_stime)
            if args.require_quiet:
                entry["processes_after"] = quiet_snapshot()
                save()
                assert not any(row["rust"] for row in entry["processes_after"]), entry["processes_after"]
            text = (evidence / (name + ".log")).read_text(errors="replace")
            entry["summaries"] = [line for line in text.splitlines() if "test result:" in line or "Seeded " in line or "snapshot" in line]
            entry["compiling_lines"] = sum("Compiling " in line for line in text.splitlines())
            save()
            print(label, name, round(entry["elapsed_seconds"], 3), process.returncode, flush=True)
            if process.returncode:
                raise RuntimeError(text[-8000:])
        receipt["measurements"]["empty"] = measure(mount)
        # A local clone avoids changing the source checkout's worktree registry.
        command("00-clone", ["git", "clone", "--shared", "--no-checkout", args.ruff, donor], root)
        command("01-checkout", ["git", "checkout", "--detach", BASE], donor)
        command("01b-fetch", [args.cargo, "fetch", "--locked"], donor)
        receipt["measurements"]["sources"] = measure(mount)
        tests = [args.cargo, "test", "--offline", "-p", "ruff_python_parser"]
        clippy = [args.cargo, "clippy", "--offline", "-p", "ruff_python_parser", "--all-targets", "--", "-D", "warnings", "-A", "clippy::format_push_string"]
        command("02-donor-test", tests, donor)
        command("03-donor-clippy", clippy, donor)
        command("04-donor-noop", tests, donor)
        receipt["measurements"]["donor"] = measure(mount)
        command("05-fork", [args.cargo, "worktree", "add", "--detach", child, "--target-dir", mount / "targets/child", BASE], donor)
        child_env = dict(env, CARGO_TARGET_DIR=str(mount / "targets/child"))
        command("06-child-test", tests, child, child_env)
        receipt["measurements"]["child_fresh"] = measure(mount)
        command("07-edit", ["git", "checkout", "--detach", EDIT], child, child_env)
        command("08-child-edit-test", tests, child, child_env)
        command("09-child-clippy", clippy, child, child_env)
        command("10-child-noop", tests, child, child_env)
        receipt["measurements"]["final"] = measure(mount)
        receipt["complete"] = True
        save()
        receipt["detach_attempts"] = []
        for attempt in range(5):
            detached = subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True, text=True)
            receipt["detach_attempts"].append({"returncode": detached.returncode, "stdout": detached.stdout, "stderr": detached.stderr})
            save()
            if detached.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"Completed measurements, but volume remains busy: {mount}")


if __name__ == "__main__":
    main()
