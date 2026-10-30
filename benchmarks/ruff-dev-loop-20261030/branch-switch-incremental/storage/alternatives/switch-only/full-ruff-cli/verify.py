"""Recompute complete CLI storage and match its executables to the native comparison."""

from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
CENSUS = ROOT / "census"


def recorded(directory, script, report, *arguments):
    result = subprocess.check_output(
        [sys.executable, "-IB", directory / script, *arguments], cwd=directory
    )
    expected = json.loads((directory / report).read_bytes())
    assert json.loads(result) == expected, report
    return expected


for name in ("census", "by-crate", "native"):
    subprocess.run(
        ["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=ROOT / name, check=True
    )
recorded(CENSUS, "audit.py", "verified.json")
storage = recorded(CENSUS, "metrics.py", "storage.json")
recorded(CENSUS, "mutations.py", "mutations.json")
recorded(ROOT / "by-crate", "by-unit.py", "by-unit.json", CENSUS)
bound = ROOT / "object-dedup-bound"
if bound.is_dir():
    subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=bound, check=True)
    subprocess.run([sys.executable, "-IB", bound / "verify.py", CENSUS, "--check"], check=True)
subprocess.run([sys.executable, "-IB", ROOT / "native/verify.py"], check=True)
native = json.loads((ROOT / "native/native.json").read_bytes())
for branch, compared in native["branches"].items():
    for mode, cli in zip(("off", "on"), compared["cli_off_on"], strict=True):
        reference = storage["complete_own_mode_elf_and_reader"][f"{mode}-{branch}"]
        assert reference["matches_empty"] and reference["cli"] == cli
        assert reference["reader"] == compared["consumer"]
assert storage["phases"]["unchanged-B"]["all"] == storage["phases"]["return-B"]["all"]
print("Verified whole-directory allocation, physical file classes and native outputs for all 12 builds.")
