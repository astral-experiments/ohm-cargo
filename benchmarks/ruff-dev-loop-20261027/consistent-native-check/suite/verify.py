import gzip
import hashlib
import json
from pathlib import Path
p = Path(__file__).resolve().parent
for line in (p / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.file_digest((p / name).open("rb"), "sha256").hexdigest() == digest, name
raw = json.loads(gzip.decompress((p / "raw-output.json.gz").read_bytes()))
results = json.loads((p / "results.json").read_text())
for label, data in raw["registry-test"].items():
    fixed = label.endswith("-fixed")
    assert ("test result: ok. 1 passed" in data["stdout"]) == fixed
    assert ("colliding StableCrateId" in data["stderr"]) != fixed
for policy, data in results["established-tests"].items():
    assert data["parent"] == data["candidate"]
    assert [*data["candidate"].values()].count("ok") == {"packaged": 3, "only-nightly-calls-opt-out": 2, "uniform-opt-out": 6}[policy]
for arm, records in results["portable"].items():
    assert len(records) == 9
    for case, phase, status in records:
        expected = 101 if arm == "baseline" and phase == "native-to-check" and case != "pure" else 0
        assert int(status) == expected
print("Matched checked-in regression 2×2, 18 portable commands, and 36 existing-suite observations verified.")
