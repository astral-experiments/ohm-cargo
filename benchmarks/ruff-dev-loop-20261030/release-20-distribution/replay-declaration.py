"""Replay the changed shared-library input with one Cargo build-script declaration."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path, help="New output directory")
parser.add_argument("declaration", choices=("file", "directory", "none"))
args = parser.parse_args()
out = args.directory.resolve()
reference = (root / "native-input-repro.py").read_bytes()
expected = "dd854fa9b4eff3c5e8428694740c7355fb2bb63c3624651e4ed75233e36f4f22"
assert hashlib.sha256(reference).hexdigest() == expected
source = reference.decode()
declaration = '    println!("cargo::rerun-if-changed=build.rs");'
assert source.count(declaration) == 1
extra = {
    "file": '    println!("cargo::rerun-if-changed={}", out.join("libgcc_s.so").display());',
    "directory": '    println!("cargo::rerun-if-changed={}", out.display());',
}
if args.declaration in extra:
    source = source.replace(declaration, declaration + "\n" + extra[args.declaration])
with tempfile.TemporaryDirectory() as scratch:
    script = Path(scratch) / "reproduce.py"
    script.write_text(source)
    mode = "stale" if args.declaration == "none" else "fixed"
    subprocess.run(
        [sys.executable, "-IB", script, out, "--zmij", "--expect", mode],
        check=True,
    )
