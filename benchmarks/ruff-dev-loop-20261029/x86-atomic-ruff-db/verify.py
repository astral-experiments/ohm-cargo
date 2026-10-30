"""Verify the predeclared paired endpoints and each independent build and test verdict."""

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import itertools
import json
from pathlib import Path

W = "ad005f99d0b51fd62b5c237bc13b31b371a1686e"
X = "b9b4105463dd4a9a16f39509d868aa15d5f96e00"
CARGO = "96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
order = ["QP", "QP", "PQ", "PQ", "QP", "PQ", "PQ", "QP"]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def total(row, kind):
    return sum(job[0] == kind for job in row["jobs"])


def atomic(row):
    return sum(job[:2] == ["full", "portable_atomic"] for job in row["jobs"])


def verify(data, screen=False):
    panels = (
        [["member-p", "P", 0], ["member-q", "Q", 0]]
        if screen
        else [
            [f"pair-{i:02d}-{arm.lower()}", arm, i]
            for i, sequence in enumerate(order, 1)
            for arm in sequence
        ]
    )
    assert (
        data["scope"] == ("screen" if screen else "registered")
        and data["schedule"] == panels
    )
    assert set(data["arms"]) == {p[0] for p in panels}
    first_products = None
    drivers = {}
    by_pair = {}
    allfiles = 0
    harness_count = 0
    for label, arm, i in panels:
        row = data["arms"][label]
        id = row["subjects"]
        assert row["arm"] == arm and id["commit"] == {"P": W, "Q": X}[arm]
        assert (
            id["cargo"] == CARGO
            and id["stock"] == WILD
            and drivers.setdefault(arm, id["driver"]) == id["driver"]
        )
        pr = row["products"]
        first_products = pr if first_products is None else first_products
        assert (
            pr == first_products
            and pr["old/build"]["verdict"] == "Other"
            and pr["new/build"]["verdict"] == "DirectoryNotEmpty"
        )
        assert (
            pr["old/test"]["inventory"] == pr["new/test"]["inventory"]
            and len(pr["old/test"]["inventory"]) > 50
        )
        assert all(
            pr["old/" + kind]["elf"] != pr["new/" + kind]["elf"]
            for kind in ("build", "test")
        )
        phases = row["phases"]
        for tag, phase in phases.items():
            assert (
                phase["trace_files"] > 0
                and phase["typed"] >= phase["fresh"] >= 0
                and phase["typed"] > 10
            )
            assert (
                len(bytes.fromhex(phase["exec_sha256"]))
                == len(bytes.fromhex(phase["cargo_sha256"]))
                == 32
            )
            assert all(
                len(bytes.fromhex(j[2])) == 32 and j[0] in ("full", "cached", "wild")
                for j in phase["jobs"]
            )
            assert not total(phase, "cached")
            allfiles += phase["trace_files"]
            harness_count += 1
            if tag.startswith("invalid-"):
                assert phase["errors"] == ["E0425"] and not phase["runtime"]
                assert any(j[:2] == ["full", "ruff_db"] for j in phase["jobs"])
                continue
            assert not phase["errors"]
            version = "old" if tag.startswith(("original-", "reverted-")) else "new"
            kind = "build" if "-build" in tag else "test"
            assert phase["product"] == pr[version + "/" + kind]["elf"]
            if kind == "build":
                assert phase["runtime"] == [pr[version + "/build"]["verdict"]]
            else:
                assert phase["runtime"] == (
                    ["FAILED", "ok", "ok"] if version == "old" else ["ok"] * 3
                )
                raw = json.dumps(
                    pr[version + "/test"]["inventory"], separators=(",", ":")
                ).encode()
                assert phase["inventory_sha256"] == digest(raw)
            if any(
                tag == stage + "-" + kind
                for stage in ("original", "edited", "reverted", "independent-new")
            ):
                assert any(j[:2] == ["full", "ruff_db"] for j in phase["jobs"])
                if kind == "test":
                    assert total(phase, "wild") >= 1
        assert len(phases) == 20
        for kind in ("build", "test"):
            assert (
                phases["independent-new-" + kind]["product"]
                == phases["edited-" + kind]["product"]
            )
            assert (
                phases["reverted-" + kind]["product"]
                == phases["original-" + kind]["product"]
            )
        by_pair.setdefault(i, {})[arm] = phases
    assert drivers["P"] != drivers["Q"]
    endpoints = {}
    for kind in ("build", "test"):
        rows = []
        position = []
        for i, arms in sorted(by_pair.items()):
            key = "edited-" + kind + "-unchanged-1"
            P, Xr = arms["P"][key], arms["Q"][key]
            assert (
                atomic(P) - atomic(Xr) >= 1
                and total(P, "full") > total(Xr, "full")
                and total(P, "wild") >= total(Xr, "wild")
            )
            byname = lambda p: Counter(j[1] for j in p["jobs"] if j[0] == "full")
            assert byname(P) == byname(Xr) + Counter({"portable_atomic": 1})
            assert Counter(j[1] for j in P["jobs"] if j[0] == "wild") == Counter(
                j[1] for j in Xr["jobs"] if j[0] == "wild"
            )

            def measure(p):
                return [total(p, "full"), total(p, "cached"), total(p, "wild")]

            section = {
                s: {a: measure(v[s + "-" + kind]) for a, v in arms.items()}
                for s in ("original", "edited", "independent-new", "reverted")
            }
            rows.append(
                {
                    "pair": i,
                    "parent": measure(P),
                    "child": measure(Xr),
                    "other_phases": section,
                }
            )
            signed = atomic(P) - atomic(Xr)
            position.append(signed if screen or order[i - 1][0] == "P" else -signed)
        record = {"all_pairs": rows}
        if not screen:
            observed = sum(
                atomic(arms["P"]["edited-" + kind + "-unchanged-1"])
                - atomic(arms["Q"]["edited-" + kind + "-unchanged-1"])
                for arms in by_pair.values()
            )
            perm = [
                sum(n if i in control_first else -n for i, n in enumerate(position))
                for control_first in itertools.combinations(range(8), 4)
            ]
            extreme = sum(abs(v) >= abs(observed) for v in perm)
            assert extreme == 2 and len(perm) == 70 and extreme / len(perm) < 0.05
            record["two_sided_exact"] = [extreme, len(perm)]
        endpoints[kind] = record
    return {
        "installations": len(panels),
        "cargo_commands": harness_count,
        "physical_trace_files": allfiles,
        "test_names": len(first_products["old/test"]["inventory"]),
        "endpoints": endpoints,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("observations", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--screen", action="store_true")
    args = ap.parse_args()
    data = json.loads(gzip.decompress(args.observations.read_bytes()))
    result = verify(data, args.screen)
    if args.self_test:
        first = next(l for l, a, _ in data["schedule"] if a == "P")
        bad = [
            ("edited-build-unchanged-1", "jobs", []),
            ("edited-test-unchanged-1", "runtime", ["ok", "FAILED", "ok"]),
            ("invalid-test", "errors", []),
            ("independent-new-test", "product", "0" * 64),
        ]
        for phase, key, value in bad:
            mutated = copy.deepcopy(data)
            mutated["arms"][first]["phases"][phase][key] = value
            try:
                verify(mutated, args.screen)
            except AssertionError:
                continue
            raise RuntimeError("accepted corrupt " + phase + "/" + key)
        result["rejected_mutations"] = len(bad)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
