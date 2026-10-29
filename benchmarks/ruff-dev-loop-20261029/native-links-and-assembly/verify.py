"""Independently verify the published paired compiler counts and source-state verdicts."""

from collections import Counter
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path


here = Path(__file__).resolve().parent
data = json.loads(gzip.decompress((here / "runs.json.gz").read_bytes()))
scored = data["scored"]
original = (json.dumps(scored, sort_keys=True, indent=2) + "\n").encode()
assert hashlib.sha256(original).hexdigest() == data["cohort_result_sha256"]
assert (
    data["cohort_result_sha256"]
    == "841294469dcec3eff10199d2d3d40cf9d11fae96ea543d74c1a3b929d25b9bfe"
)
assert (
    scored["protocol_sha256"]
    == "145903f31b869d9b8e0deb6a8b2890d6b0d316c8e0a14560b0e5bee93fa86f43"
)
assert (
    scored["qualified"]
    and scored["pairs_per_mode"] == 8
    and scored["unchanged_visits"] == 192
)
assert (
    len(data["schedule"])
    == len(data["installations"])
    == len(scored["native_rosters"])
    == 32
)
hashes = {
    "A": "43acdc336b077657fc4182a2ad79a6dc1cfb2f5e84f83dcd9ab6576e037aa276",
    "C": "96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5",
}
observations = {}
elfs = {}
for label, arm, mode in data["schedule"]:
    run = data["installations"][label]
    source = run["provenance"]
    verdict = run["verdicts"]
    assert (
        source["arm"] == arm
        and source["mode"] == mode
        and source["cold"]
        and not source["pgo"]
        and not source["bolt"]
    )
    assert (
        source["cargo"] == hashes[arm]
        and source["rust"] == "ad005f99d0b51fd62b5c237bc13b31b371a1686e"
    )
    assert (
        source["Ruff"] == "93526150df078af7dd8fc4226cdcc469539d2001"
        and source["wild"]
        == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    )
    assert (
        source["old"] != source["new"]
        and verdict["status"] == "complete"
        and verdict["clean_matched"]
    )
    pair = tuple(verdict[key]["elf"] for key in ("old_verdict", "new_verdict"))
    assert list(pair) == scored["empty_and_dirty_ELFs"][label] and pair[0] != pair[1]
    elfs.setdefault(mode, set()).add(pair)
    old, new = verdict["old_verdict"], verdict["new_verdict"]
    if mode == "build":
        assert old["verdict"] == "3.14 3.14 3.10" and new["verdict"] == "3.15 3.15 3.11"
    else:
        assert (
            old["names"] == new["names"]
            and len(new["names"]) == 54
            and len(old["failed"]) == 4
            and new["failed"] == []
        )
    assert (
        run["invalid"]["diagnostic"] == "E0425"
        and run["invalid"]["expected_exit"] == 101
    )
    rows = scored["native_rosters"][label]
    unchanged = [r for name, r in rows.items() if name.startswith("unchanged-")]
    assert (
        len(unchanged) == 6
        and {**rows, "invalid": None}.keys() == run["raw_sha256"].keys()
    )
    for name in ("edited-new", "reverted-old"):
        assert "ruff_python_ast" in rows[name]["compilers"]
        if mode == "test":
            assert rows[name]["links"] == 1
    for commitments in run["raw_sha256"].values():
        assert len(commitments) == 3 and all(
            len(bytes.fromhex(h)) == 32 for h in commitments.values()
        )
    observations[label] = {
        "rustc": sum(len(r["compilers"]) for r in unchanged),
        "wild": sum(r["links"] for r in unchanged),
    }
assert all(len(v) == 1 for v in elfs.values())
for metric in scored["metrics"]:
    mode = metric["mode"]
    kind = metric["endpoint"]
    pairs = []
    for i in range(1, 9):
        pair = [
            (arm, observations[label][kind])
            for label, arm, k in data["schedule"]
            if k == mode and label.startswith(f"pair-{i:02d}-")
        ]
        assert len(pair) == 2 and set(dict(pair)) == {"A", "C"}
        pairs.append(pair)
    assert Counter(pair[0][0] for pair in pairs) == {"A": 4, "C": 4}
    observed = sum(dict(pair)["A"] - dict(pair)["C"] for pair in pairs)
    order_differences = [first[1] - second[1] for first, second in pairs]
    allocations = list(combinations(range(8), 4))
    extreme = sum(
        abs(sum(d if i in picks else -d for i, d in enumerate(order_differences)))
        >= abs(observed)
        for picks in allocations
    )
    assert (observed, extreme, len(allocations)) == (
        metric["saved"],
        metric["exact_extreme"],
        metric["assignments"],
    )
    src = sum(dict(pair)["A"] for pair in pairs)
    dest = sum(dict(pair)["C"] for pair in pairs)
    assert (src, dest) == (metric["parent_total"], metric["candidate_total"])
    assert all(
        (dict(pair)["A"], dict(pair)["C"]) == (r["A"], r["C"])
        for pair, r in zip(pairs, metric["pairs"])
    )
    print(
        f"{mode} {kind}: {src} → {dest} over eight pairs, two-sided p = {extreme}/{len(allocations)}"
    )

link_only = json.loads((here / "link-only.json").read_bytes())
assert link_only.keys() == scored["native_rosters"].keys()
for name, counts in link_only.items():
    assert counts.keys() == scored["native_rosters"][name].keys()
    assert all(count == 0 for count in counts.values())
print("No link-only rustc executions in the 352 successful Cargo build and test commands.")
