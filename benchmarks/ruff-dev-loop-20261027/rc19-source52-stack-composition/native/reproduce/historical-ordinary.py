"""Run one provider/reader publication order with a private installed Linux SDK."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("sdk", type=Path, help="directory containing bin/cargo and bin/rustc")
parser.add_argument("root", type=Path, help="new directory for this one run")
parser.add_argument("order", choices=["provider-late", "provider-first"])
parser.add_argument("--expect", choices=["stale", "correct"])
args = parser.parse_args()
here = Path(__file__).resolve().parent
sdk = args.sdk.resolve(strict=True)
root = args.root.resolve()
root.mkdir(mode=0o700)
src = root / "src"
shutil.copytree(here / "fixture", src)
proxy = shutil.which("cargo")
assert proxy and (sdk / "bin/cargo").is_file()
aliases = root / "rustup" / "toolchains"
aliases.mkdir(parents=True)
(aliases / "ohm").symlink_to(sdk, target_is_directory=True)
env = dict(PATH=os.environ["PATH"], HOME=str(root), CARGO_HOME=str(root / "home"),
           RUSTUP_HOME=str(aliases.parent), RUSTUP_AUTO_INSTALL="0", LANG="C", LC_ALL="C",
           CARGO_TARGET_DIR=str(root / "target"), CARGO_BUILD_BUILD_DIR=str(root / "shared"))
def check(label, overrides=None):
    result = subprocess.run([proxy, "+ohm", "check", "--workspace", "--locked", "--offline",
                             "-j4", "--message-format=json"], cwd=src, env=env | (overrides or {}),
                            capture_output=True, timeout=60)
    (root / (label + ".stdout")).write_bytes(result.stdout)
    (root / (label + ".stderr")).write_bytes(result.stderr)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    errors = [(r["target"]["name"], (r["message"]["code"] or {}).get("code"))
              for r in rows if r["reason"] == "compiler-message" and r["message"]["level"] == "error"]
    assert rows[-1] == {"reason": "build-finished", "success": result.returncode == 0}
    assert (result.returncode, errors) in [(0, []), (101, [("client", "E0034")])], (label, errors)
    fresh = [r["target"]["name"] for r in rows if r["reason"] == "compiler-artifact" and r["fresh"]]
    print(label, result.returncode, errors, "fresh", sorted(fresh), flush=True)
    return result.returncode, len(fresh)

assert check("original")[0] == 0
assert check("original-repeat") == (0, 4)
provider = src / "provider/src/lib.rs"
reader = src / "reader/src/lib.rs"
origin, middle = provider.read_bytes(), reader.read_bytes()
provider.write_bytes(origin + b"impl api::Second for Token { fn priority(&self) -> u8 { 29 } }\n")
assert middle.count(b"{ 11 }") == 1
reader.write_bytes(middle.replace(b"{ 11 }", b"{ 12 }"))
warm, _ = check("edited")
repeat, fresh = check("edited-repeat")
assert warm == repeat and (warm != 0 or fresh == 4)
empty, _ = check("edited-clean", dict(CARGO_TARGET_DIR=str(root / "cold-target"),
                                      CARGO_BUILD_BUILD_DIR=str(root / "cold-shared")))
assert empty == 101
provider.write_bytes(origin)
reader.write_bytes(middle)
assert check("restore")[0] == 0 and check("restore-repeat") == (0, 4)
verdict = "stale" if warm == 0 else "correct"
print("Warm result:", verdict)
assert args.expect is None or args.expect == verdict
