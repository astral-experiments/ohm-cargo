"""Compare released Ohm Cargo variants on uv's complete feature graphs."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

work = Path(__file__).resolve().parent
outputs = work / "validation-uv-features"
outputs.mkdir(exist_ok=True)
compiler = work / "toolchain" / "bin"
env = dict(os.environ, RUSTUP_TOOLCHAIN="stable", CARGO_HOME=str(work / "cargohome"),
           CARGO_TARGET_DIR=str(outputs / "target"), RUSTC=str(compiler / "rustc"),
           RUSTDOC=str(compiler / "rustdoc"), PATH=str(compiler) + os.pathsep + os.environ["PATH"],
           CARGO_TERM_COLOR="never")
cargos = [Path(x).resolve() for x in sys.argv[1:]]
for name, targets in [("linux", ["x86_64-unknown-linux-gnu"]), ("windows", ["x86_64-pc-windows-msvc"]),
                      ("linux-and-windows", ["x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc"])]:
    for cmd, args, filter_option in [
        ("tree", ["--workspace", "-e", "features", "--charset", "ascii"], "--target"),
        ("metadata", ["--format-version", "1"], "--filter-platform"),
    ]:
        args += [arg for target in targets for arg in (filter_option, target)]
        data = None
        for cargo in cargos:
            command = [cargo, cmd, "--offline", "--locked", *args]
            result = subprocess.check_output(command, cwd=work / "uv", env=env)
            output = outputs / f"{name}-{cmd}-{cargo.name}.txt"
            output.write_bytes(result)
            if data is None:
                data = result
            assert result == data, output
        print(name, cmd, len(data), hashlib.sha256(data).hexdigest(), flush=True)
