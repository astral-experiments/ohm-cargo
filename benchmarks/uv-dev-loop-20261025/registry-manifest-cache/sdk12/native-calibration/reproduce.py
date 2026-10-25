#!/usr/bin/env python3
"""Replay the complete, fixed A/A calibration. No benchmark is executed."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis_core


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_samples(root, protocol, provenance):
    columns = ["host", "pair", "position", "order", "label", "cargo_binary", "elapsed_ns", "raw_file", "raw_sha256"]
    with (root / "samples.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == columns
        rows = list(reader)
    assert len(rows) == 32
    results = []
    for index, host in enumerate(protocol["hosts"]):
        selected = rows[index * 16:(index + 1) * 16]
        pairs = []
        for pair, order in enumerate(protocol["phases"]["aa"]["orders"][str(index)]):
            values = {}
            for position, letter in enumerate(order):
                row = selected[2 * pair + position]
                assert (row["host"], row["pair"], row["position"], row["order"], row["label"], row["cargo_binary"]) == (host, str(pair), str(position), order, letter, "baseline")
                assert re.fullmatch(r"[1-9][0-9]*", row["elapsed_ns"])
                relative = Path(row["raw_file"])
                assert relative == Path("raw") / host / f"pair-{pair:02}-pos-{position}-{letter}.json"
                assert sha(root / relative) == row["raw_sha256"]
                raw = json.loads((root / relative).read_bytes())
                assert set(raw) == {"unit", "elapsed_ns"} and raw["unit"] == "nanoseconds"
                assert type(raw["elapsed_ns"]) is int and raw["elapsed_ns"] == int(row["elapsed_ns"]) > 0
                assert provenance["sample_custody"][index * 16 + pair * 2 + position]["elapsed_sha256"] == row["raw_sha256"]
                values[protocol["labels"][letter]] = raw["elapsed_ns"]
            pairs.append({"order": order, **values})
        results.append(pairs)
    return results


def reproduce(root):
    manifest = json.loads((root / "artifact-manifest.json").read_bytes())
    for relative, expected in manifest["files"].items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts
        actual = root / path
        assert actual.is_file() and not actual.is_symlink()
        assert actual.stat().st_size == expected["bytes"] and sha(actual) == expected["sha256"]
    protocol = json.loads((root / "protocol.json").read_bytes())
    provenance = json.loads((root / "provenance.json").read_bytes())
    assert protocol["hosts"] == ["host-1", "host-2"]
    assert protocol["phases"]["aa"]["bootstrap_seeds"] == [20261025251, 20261025252]
    assert protocol["phases"]["aa"]["pairs_per_host"] == 8
    assert set(protocol["AA_cargo_by_label"].values()) == {provenance["baseline_Cargo_sha256"]}
    # Validate the complete two-host integer inventory before either statistic.
    all_pairs = load_samples(root, protocol, provenance)
    summaries = []
    for index, pairs in enumerate(all_pairs):
        summary = analysis_core.summarize(pairs, "aa", protocol["phases"]["aa"]["bootstrap_seeds"][index])
        summary.update(hostname=protocol["hosts"][index], phase="aa", pairs=pairs)
        assert summary == json.loads((root / "expected" / f"host-{index + 1}-summary.json").read_bytes())
        summaries.append(summary)
    decision = analysis_core.decision("aa", summaries, provenance["original_protocol_sha256"])
    assert decision == json.loads((root / "decision.json").read_bytes())
    assert decision["disposition"] == "native-closed-AA-noise" and decision["ab_eligible"] is False
    return {"state": "portable-AA-replay-exact", "samples": 32, "summaries": summaries, "decision": decision,
            "native_candidate_comparisons": 0, "candidate_elapsed_effect": "unknown", "pooled_statistics": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reproduce(Path(__file__).resolve().parent)
    if args.output:
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps({"state": result["state"], "samples": result["samples"], "disposition": result["decision"]["disposition"],
                      "native_candidate_comparisons": 0, "candidate_elapsed_effect": "unknown"}))


if __name__ == "__main__":main()
