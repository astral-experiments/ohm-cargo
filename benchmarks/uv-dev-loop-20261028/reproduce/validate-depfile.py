"""Compare Cargo's depfile bytes and mtime handling outside the benchmark targets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

work = Path(__file__).resolve().parent
fixture = work / "validation-depfile-fixture"
source = fixture / "crate space 雪"
dep = fixture / "outside helper é"
target = fixture / "output dir" / "target"
depfile = target / "debug" / "libcompare_depfile.d"
binary = target / "debug" / "libcompare_depfile.rlib"
before, after = (Path(x).resolve() for x in sys.argv[1:])

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")

put(source / "Cargo.toml", """
[package]
name = "compare_depfile"
version = "0.1.0"
edition = "2024"

[dependencies]
helper = { path = "../outside helper é" }
""")
put(source / "src" / "lib.rs", """
pub const COMBINED: (&str, u8) = (include_str!("input  two é雪.txt"), helper::VALUE);
""")
put(source / "src" / "input  two é雪.txt", "snow")
put(dep / "Cargo.toml", '[package]\nname="helper"\nversion="0.1.0"\nedition="2024"\n')
put(dep / "src" / "lib.rs", "pub const VALUE: u8 = 1;\n")
env = dict(os.environ, RUSTUP_TOOLCHAIN="stable", CARGO_HOME=str(work / "cargohome"),
           CARGO_TARGET_DIR=str(target), CARGO_TERM_COLOR="never")
toolchain = work / "toolchain" / "bin"
env.update(RUSTC=str(toolchain / "rustc"), RUSTDOC=str(toolchain / "rustdoc"),
           PATH=str(toolchain) + os.pathsep + env["PATH"])
subprocess.run([before, "generate-lockfile", "--offline"], cwd=source, env=env, check=True)

for mode, basedir in (("absolute", None), ("relative", fixture), ("mixed", source)):
    # "mixed" keeps both the external helper and the target absolute.
    options = []
    if basedir is not None:
        normalized_input = str(basedir) + "/../" + basedir.name
        options = ["--config", "build.dep-info-basedir=" + json.dumps(normalized_input, ensure_ascii=False)]
    def render(path):
        display = path
        if basedir is not None and path.is_relative_to(basedir):
            display = path.relative_to(basedir)
        return str(display).replace(" ", "\\ ").encode()
    inputs = [source / "src" / "lib.rs", source / "src" / "input  two é雪.txt",
              dep / "src" / "lib.rs"]
    expected = render(binary) + b":" + b"".join(b" " + render(p) for p in sorted(inputs)) + b"\n"
    reference = None
    stamp = 1_601_234_567_123_456_789
    for label, cargo in (("old", before), ("new", after)):
        command = [cargo, "build", "--offline", "--locked", "-j8", *options]
        depfile.unlink(missing_ok=True)
        subprocess.run(command, cwd=source, env=env, check=True)
        contents = depfile.read_bytes()
        assert contents == expected, (mode, label, contents, expected)
        if reference is None:
            reference = contents
        assert contents == reference, (mode, label)
        os.utime(depfile, ns=(stamp, stamp))
        subprocess.run(command, cwd=source, env=env, check=True)
        assert depfile.read_bytes() == reference
        assert depfile.stat().st_mtime_ns == stamp, (mode, label, depfile.stat().st_mtime_ns, stamp)
    print(mode, len(reference), hashlib.sha256(reference).hexdigest(), stamp, flush=True)
