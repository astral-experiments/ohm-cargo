#!/usr/bin/env python3
"""Recompute accepted public arithmetic; no workloads or private admission checks."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import math
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("published_paired_statistics", ROOT / "reproduction/paired_statistics.py")
PAIRED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAIRED)
paired_count_statistics = PAIRED.paired_count_statistics


def read_json(name):
    return json.loads((ROOT / name).read_text())


def profile_counts(raw):
    # Framing/self-cost accounting follows the accepted v4 final_ir parser.
    text = raw.decode()
    assert text.endswith("\n") and "positions: line\n" in text
    assert "events: Ir\n" in text and "desc: Trigger: Program termination\n" in text
    assert re.findall(r"^part: (\d+)$", text, re.M) == ["1"]
    totals = re.findall(r"^totals: (\d+)$", text, re.M)
    headers = re.findall(r"^summary: (\d+)$", text, re.M)
    assert len(totals) == len(headers) == 1
    final, header = int(totals[0]), int(headers[0])
    self_total, pending = 0, False
    for line in text.splitlines():
        if line.startswith("calls="):
            assert not pending
            pending = True
        elif line and line[0] in "0123456789+-*":
            match = re.fullmatch(r"(?:\d+|[+-]\d+|\*)\s+(\d+)\s*", line)
            assert match
            if pending:
                pending = False
            else:
                self_total += int(match[1])
    assert not pending and self_total == final
    return final, header, self_total


def verify_profiles(data):
    counts = {}
    for row in data.get("profiles", []):
        record = row["file"]
        compressed = (ROOT / record["path"]).read_bytes()
        assert len(compressed) == record["bytes"]
        assert hashlib.sha256(compressed).hexdigest() == record["sha256"]
        raw = gzip.decompress(compressed)
        assert len(raw) == row["uncompressed_bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["uncompressed_sha256"]
        final, header, self_total = profile_counts(raw)
        assert final == row["final_ir"] == row["self_cost_sum"]
        assert header == row["header_summary_ir"]
        assert final - header == row["final_minus_header"]
        # This field is an authenticated review result; raw stderr is private.
        assert final == row["stderr_collected"]
        assert row["label"] not in counts
        counts[row["label"]] = final
    for pair in data["pairs"]:
        order = pair["order"]
        if isinstance(order, str):
            order = ["baseline" if value == "A" else "candidate" for value in order]
        for position, variant in enumerate(order):
            assert counts[f"pair-{pair['pair']}-{position}-{variant}"] == pair[f"{variant}_ir"]


def same_numbers(left, right):
    if isinstance(left, dict):
        return isinstance(right, dict) and left.keys() == right.keys() and all(same_numbers(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return isinstance(right, list) and len(left) == len(right) and all(same_numbers(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return isinstance(right, (int, float)) and math.isclose(left, right, rel_tol=1e-14, abs_tol=1e-14)
    return left == right


def count_pairs(data):
    result = []
    for row in data["pairs"]:
        order = row["order"]
        if not isinstance(order, str):
            order = "".join("A" if value == "baseline" else "B" for value in order)
        result.append({"baseline": row["baseline_ir"], "candidate": row["candidate_ir"], "order": order})
    return result


def main():
    status, protocol = read_json("publication-status.json"), read_json("protocol.json")
    result = {"scope": "Published arithmetic and raw-profile integrity only; private operational admission is not replayed."}
    discovery = read_json(status["discovery"])
    verify_profiles(discovery)
    pairs = count_pairs(discovery)
    assert len(pairs) == 2 and [p["order"] for p in pairs] == ["AB", "BA"]
    reduction = 1 - math.exp(statistics.fmean(math.log(p["candidate"] / p["baseline"]) for p in pairs))
    assert math.isclose(reduction, discovery["geometric_instruction_reduction"], abs_tol=1e-15)
    gate = all(p["candidate"] < p["baseline"] for p in pairs) and 400 * math.prod(p["candidate"] for p in pairs) <= 361 * math.prod(p["baseline"] for p in pairs)
    assert gate == discovery["advance_gate"]["passed"]
    result["discovery"] = {"geometric_ir_reduction": reduction, "advance_gate": gate}
    for block in [1, 2]:
        key = f"confirmation_{block}"
        if status[key] is None:
            result[key] = None
            continue
        data = read_json(status[key])
        verify_profiles(data)
        pairs = count_pairs(data)
        assert len(pairs) == 8 and [p["order"] for p in pairs] == protocol["confirmation"]["orders"][block - 1]
        stats = paired_count_statistics(pairs, confidence=0.99, resamples=200000, seed=20261022 + block)
        assert same_numbers(stats, data["statistics"])
        gate = stats["wins"] == 8 and stats["exact_two_sided_sign_p"] == 0.0078125 and stats["bootstrap_count_reduction_interval"][0] > 0.03
        assert gate == data["gate_passed"]
        result[key] = {"statistics": stats, "gate_passed": gate}
    if status.get("confirmation_combined") is not None:
        combined = read_json(status["confirmation_combined"])
        pairs = count_pairs(read_json(status["confirmation_1"])) + count_pairs(read_json(status["confirmation_2"]))
        pooled = 1 - math.exp(statistics.fmean(math.log(p["candidate"] / p["baseline"]) for p in pairs))
        assert math.isclose(pooled, combined["pooled_descriptive_instruction_reduction"], abs_tol=1e-14)
        result["pooled_descriptive_ir_reduction"] = pooled
    if status["check"] is None:
        result["check"] = None
    else:
        data = read_json(status["check"])
        verify_profiles(data)
        pairs = count_pairs(data)
        assert len(pairs) == 1 and pairs[0]["order"] == "AB"
        p = pairs[0]
        gate = 200 * p["candidate"] <= 201 * p["baseline"]
        assert gate == data["gate_passed"]
        result["check"] = {"instruction_reduction": 1 - p["candidate"] / p["baseline"], "regression_guard_passed": gate}
    if status["native"] is None:
        result["native"] = None
    else:
        data = read_json(status["native"])
        pairs = data["pairs"]
        assert len(pairs) == 8 and [p["order"] for p in pairs] == protocol["native"]["orders"]
        assert all(p[k] > 0 and math.isfinite(p[k]) for p in pairs for k in ["baseline_seconds", "candidate_seconds"])
        ratio = math.exp(statistics.fmean(math.log(p["candidate_seconds"] / p["baseline_seconds"]) for p in pairs))
        losses = sum(p["candidate_seconds"] > p["baseline_seconds"] for p in pairs)
        blocker = ratio >= 1.03 and losses >= 6
        assert blocker == data["publication_blocker"]
        result["native"] = {"geometric_candidate_to_baseline_wall_ratio": ratio, "candidate_losses": losses, "publication_blocker": blocker, "positive_wall_claim": False}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
