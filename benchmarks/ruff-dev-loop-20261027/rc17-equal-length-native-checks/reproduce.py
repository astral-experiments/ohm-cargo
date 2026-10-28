"""Run the scoped native control with a Rustup toolchain named ohm on Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


parser = argparse.ArgumentParser()
parser.add_argument("destination", type=Path, help="New directory for the reproducer")
args = parser.parse_args()
root = args.destination.resolve()
root.mkdir()
code = root / "code"
template = "input/heldout-fixture/"
with tarfile.open(Path(__file__).with_name("observations.tar.gz")) as archive:
    for entry in archive:
        if entry.isfile() and entry.name.startswith(template):
            target = code / entry.name.removeprefix(template)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(entry).read())

main = code / "hold_direct/src/main.rs"
main.write_text(main.read_text().replace(');}', ');println!("escape-value={}",escape_fixture::value());}'))
actual = root / "input space/libescape_fixture.rlib"
decoy = root / "input\\ space/libescape_fixture.rlib"
actual.parent.mkdir()
decoy.parent.mkdir()
env = os.environ.copy()
for name in ("RUSTC", "RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
             "CARGO_ENCODED_RUSTFLAGS", "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST",
             "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST"):
    env.pop(name, None)
env.update(CARGO_HOME=str(root / "cargo-home"), CARGO_TARGET_DIR=str(root / "target"),
           CARGO_BUILD_BUILD_DIR=str(root / "shared"), CARGO_BUILD_JOBS="4")
external = root / "external.rs"
staging = root / "stable-output.rlib"
compile_external = [
    "rustc", "+ohm", "--crate-name", "escape_fixture", "--crate-type=rlib",
    "-Copt-level=1", "-Cmetadata=keep-identical-tag", "-Cdebuginfo=0",
    str(external), "-o", str(staging),
]
for value, output in [(17, actual), (29, decoy)]:
    external.write_text(f"pub fn value()->u32 {{{value}}}\n")
    subprocess.run(compile_external, cwd=root, env=env, check=True)
    shutil.copy2(staging, output)
env["CARGO_ENCODED_RUSTFLAGS"] = "--extern\x1fescape_fixture=" + str(actual)


def build(phase, environment):
    command = ["cargo", "+ohm", "build", "--offline", "-p", "hold_direct", "--message-format=json"]
    run = subprocess.run(command, cwd=code, env=environment, capture_output=True)
    (root / f"{phase}.stdout").write_bytes(run.stdout)
    (root / f"{phase}.stderr").write_bytes(run.stderr)
    run.check_returncode()
    records = [json.loads(line) for line in run.stdout.splitlines()]
    unit, = [record for record in records if record.get("reason") == "compiler-artifact"
             and record["target"]["name"] == "hold_direct"]
    text = subprocess.check_output([unit["executable"]], cwd=root, text=True)
    return {"value": int(text.split("escape-value=")[-1].strip()), "fresh": unit["fresh"]}


results = {phase: build(phase, env) for phase in ("first", "train", "unchanged")}
stamp = actual.stat()
new = decoy.read_bytes()
assert len(new) == stamp.st_size and hashlib.sha256(new).digest() != hashlib.sha256(actual.read_bytes()).digest()
actual.write_bytes(new)
os.utime(actual, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
current = actual.stat()
assert (current.st_ino, current.st_size, current.st_mtime_ns) == (stamp.st_ino, stamp.st_size, stamp.st_mtime_ns)
results["changed"] = build("changed", env)
results["empty"] = build("empty", {**env, "CARGO_TARGET_DIR": str(root / "clean-target"),
                                   "CARGO_BUILD_BUILD_DIR": str(root / "clean-shared")})
print(json.dumps(results, indent=2))
assert results["unchanged"]["value"] == 17 and results["empty"]["value"] == 29
