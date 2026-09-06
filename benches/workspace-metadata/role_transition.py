#!/usr/bin/env python3
"""Measure root-role changes while retaining the parser's dependency feature graph."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import time

from run_apfs import measure, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    for label in ["off1", "on1", "on2", "off2"]:
        evidence = args.results / label
        original = json.loads((evidence / "receipt.json").read_text())
        mount = Path(original["volume"])
        assert not mount.is_mount()
        image = mount.parent / "storage.sparsebundle"
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(image)],
                       check=True, capture_output=True)
        donor = mount / "donor"
        env = dict(os.environ, **original["environment"])
        env.update(CARGO_TARGET_DIR=str(mount / "targets/role-transition"),
                   CARGO_BUILD_BUILD_DIR=str(mount / "shared/role-transition"), INSTA_UPDATE="no")
        cargo = Path(env["CARGO"])
        assert sha256(cargo) == original["cargo_sha256"]
        env["PATH"] = os.pathsep.join([str(cargo.parent), str(Path(env["RUSTC"]).parent), os.environ["PATH"]])
        for variable in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"]:
            env.pop(variable, None)
        assert not Path(env["CARGO_TARGET_DIR"]).exists()
        assert not Path(env["CARGO_BUILD_BUILD_DIR"]).exists()
        receipt = {"label": label, "cargo_sha256": original["cargo_sha256"],
                   "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=donor, text=True).strip(),
                   "environment": {key: value for key, value in env.items() if key in original["environment"]},
                   "commands": [], "measurements": {"before": measure(mount)}}
        output = evidence / "role-transition.json"
        assert not output.exists()
        def save():
            output.write_text(json.dumps(receipt, indent=2) + "\n")
        for name, packages in [("role-01-parser", ["ruff_python_parser"]),
                               ("role-02-add-ast-root", ["ruff_python_parser", "ruff_python_ast"]),
                               ("role-03-return-parser", ["ruff_python_parser"]),
                               ("role-04-noop", ["ruff_python_parser"])]:
            argv = [str(cargo), "build", "--offline"]
            for package in packages:
                argv.extend(["-p", package])
            start_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = time.monotonic()
            log = evidence / (name + ".log")
            with log.open("xb") as file:
                process = subprocess.run(argv, cwd=donor, env=env, stdout=file, stderr=subprocess.STDOUT)
            elapsed = time.monotonic() - start
            end_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            lines = log.read_text(errors="replace").splitlines()
            receipt["commands"].append({"name": name, "argv": argv, "elapsed_seconds": elapsed,
                "returncode": process.returncode, "child_user_seconds": end_usage.ru_utime - start_usage.ru_utime,
                "child_system_seconds": end_usage.ru_stime - start_usage.ru_stime,
                "compiling": [line for line in lines if "Compiling " in line]})
            receipt["measurements"][name] = measure(mount)
            save()
            print(label, name, round(elapsed, 3), process.returncode, flush=True)
            if process.returncode:
                raise RuntimeError("\n".join(lines[-50:]))
        receipt["complete"] = True
        receipt["detach_attempts"] = []
        for attempt in range(5):
            detached = subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True, text=True)
            receipt["detach_attempts"].append({"returncode": detached.returncode,
                                              "stdout": detached.stdout, "stderr": detached.stderr})
            save()
            if detached.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"Measurements completed, but volume remains busy: {mount}")


if __name__ == "__main__":
    main()
