#!/usr/bin/env python3
"""Build the small driver with matching rustc-dev metadata; never rebuild rustc or LLVM."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess


def output(command):
    return subprocess.check_output(command, text=True).strip()


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rustc", required=True, type=Path)
    parser.add_argument("--rustc-dev", type=Path, help="directory containing matching rustc-dev .rmeta files")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.rustc.resolve(strict=True)
    sysroot = Path(output([str(compiler), "--print", "sysroot"])).resolve(strict=True)
    verbose = output([str(compiler), "-vV"])
    host = next(line.removeprefix("host: ") for line in verbose.splitlines() if line.startswith("host: "))
    metadata = args.rustc_dev or sysroot / "lib" / "rustlib" / host / "lib"
    drivers = list((sysroot / "lib").glob("librustc_driver-*.so"))
    if len(drivers) != 1:
        parser.error("expected exactly one installed rustc_driver shared library")
    driver = drivers[0].resolve(strict=True)
    development_driver = metadata / driver.name
    if not development_driver.is_file() or digest(driver) != digest(development_driver):
        parser.error("rustc-dev must match the selected compiler's exact driver build")
    session = list(metadata.glob("librustc_session-*.rmeta"))
    if len(session) != 1:
        parser.error("expected matching rustc_session metadata in --rustc-dev")
    environment = os.environ.copy()
    environment.update({
        "RUSTC_BOOTSTRAP": "1",
        "SESSION_WORKER_COMPILER": str(compiler),
        "SESSION_WORKER_COMPILER_SHA256": digest(compiler),
        "SESSION_WORKER_DRIVER": str(driver),
        "SESSION_WORKER_DRIVER_SHA256": digest(driver),
        "SESSION_WORKER_SYSROOT": str(sysroot),
        "SESSION_WORKER_VERBOSE_VERSION": verbose,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler), "--edition=2024", str(Path(__file__).with_name("main.rs")),
        "--extern", f"rustc_driver={development_driver}",
        "--extern", f"rustc_session={session[0]}",
        "-L", f"dependency={metadata}", "-L", f"native={sysroot / 'lib'}",
        "-Cprefer-dynamic", "-Copt-level=2",
        "-Clink-arg=-Wl,-rpath," + str(sysroot / "lib"),
        "-Clink-arg=-Wl,-rpath," + str(sysroot / "lib" / "rustlib" / host / "lib"),
        "-o", str(args.output),
    ]
    subprocess.run(command, env=environment, check=True)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
