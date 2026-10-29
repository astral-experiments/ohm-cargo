"""Verify the exact historical boundary, the release crossover and independent native values."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent
def load(name): return json.loads((root/name).read_bytes())
full = [["dep", "lib"], ["app", "lib"], ["app", "bin"]]
committed_failure = [["dep", "lib"], ["app", "lib"]]
incomplete_revert = [["dep", "lib"], ["app", "bin"]]
recovered = [["app", "lib"], ["app", "bin"]]
samples = load("original-test.json")
assert len(samples) == 9 and len({tuple(r["physical_isolated_root_identity"]) for r in samples}) == 9
records = {v["role"]: v for v in samples}
rustc = "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
for r in samples:
    assert r["rustc_sha256"] == rustc
    sequences = r["actual_crate_compilations"]
    if r["role"] == "historical-parent":
        assert sequences == [full, [["dep", "lib"]]] and "parent-timed-out" in r["checkpoints"]
        assert r["diagnostic_codes"] == [] and r["harness_exit"] == 101
    else:
        assert sequences[:2] == [full, committed_failure]
        assert sorted(r["checkpoints"]) == ["dependency-failed", "parent-started-early"]
        passed = r["role"] in ("historical-head", "historical-seedparent")
        assert sequences[2:] == [full if passed else incomplete_revert]
        assert r["diagnostic_codes"] == ([] if passed else ["E0460"])
        assert r["harness_exit"] == (0 if passed else 101)
assert records["historical-seedparent"]["source"] == "88bd5ae13cb69b1eaddc17cb8612761fc9ef8102"
assert records["historical-seeddefault"]["source"] == "af091eb21f940445b6447a3f33dc610a8c291f24"
cases = load("source-crossover.json")
assert set(cases) == {"ordinary-original-fixture", "seeds-on", "seeds-off", "checksums-only"}
for name, stages in cases.items():
    assert stages["prime"]["rustcs"] == full and stages["prime-program"]["program_value"] == "1"
    fail = stages["forced-failure"]
    assert fail["exit"] == 101 and fail["rustcs"] == committed_failure
    for suffix, length in [("/lib-dep", 0), ("/lib-app", 16)]:
        values = [v for k, v in fail["artifacts"].items() if k.endswith(suffix)]
        assert len(values) == 1 and values[0]["size"] == length
    x = stages["reverted"]
    if name == "seeds-off":
        assert x["exit"] == 0 and x["rustcs"] == full and x["errors"] == []
        assert stages["reverted-program"]["program_value"] == "1"
    else:
        assert x["exit"] == 101 and x["rustcs"] == incomplete_revert and x["errors"] == ["E0460"]
        assert stages["untouched-1"]["exit"] == 0 and stages["untouched-1"]["rustcs"] == recovered
        assert stages["untouched-1-program"]["program_value"] == "1"
p = load("provenance.json")
assert p["released"]["images"]["cargo"] == records["released18"]["cargo_sha256"] == "02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
for role, expected in (("default", "untouched-1"), ("seeds-off", "reverted")):
    outcome = p["portable_replays"][role]
    assert outcome["first_success"] == expected and outcome["value"] == 1
    assert outcome["cargo_sha256"] == p["released"]["images"]["cargo"] and outcome["rustc_sha256"] == rustc
assert len(p["setup_attempts"]) == 5
manifest = root/"SHA256SUMS"
if manifest.is_file():
    files = {str(f.relative_to(root)) for f in root.rglob("*") if f.is_file() and f != manifest}
    listed = {line.split("  ", 1)[1] for line in manifest.read_text().splitlines()}
    assert files == listed
    for line in manifest.read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected
print("9 original-test binaries, 4 synchronized release settings, 2 standalone reproductions, 5 original setup exceptions verified")
