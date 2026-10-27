"""Prespecified simultaneous one-sided median bounds for paired application instructions."""
from pathlib import Path
import hashlib
import json
import math
import statistics
import sys


def analyze(rows, plan):
    assert len(rows) == 48
    expected = [(i, ep, arm) for i, block in enumerate(plan["blocks"])
                for ep in block["endpoints"] for arm in block[ep]]
    assert [(r["pair"], r["endpoint"], r["arm"]) for r in rows] == expected
    results = {}
    for ep in ["retained", "empty"]:
        pairs = []
        for i in range(12):
            selected = [r for r in rows if (r["endpoint"], r["pair"]) == (ep, i)]
            counts = {r["arm"]: r["instructions"] for r in selected}
            assert set(counts) == {"parent", "candidate"}
            for r in selected:
                assert r["thread_count"] >= 2 and r["events"]["T"] == r["events"]["F"] == r["thread_count"]
                assert r["events"]["B"] == r["events"]["P"] == 1 and r["instructions"] > 100000000
                assert r["archive_rmeta_sha256"] == r["rmeta_sha256"] and r["child"]["exit"] == 0
            pairs.append({"pair": i, "order": [r["arm"] for r in selected], **counts,
                          "log_ratio": math.log(counts["candidate"] / counts["parent"])})
        logs = sorted(p["log_ratio"] for p in pairs)
        pct = lambda x: 100 * math.expm1(x)
        results[ep] = {"paired_median_delta_pct": pct(statistics.median(logs)),
                       "one_sided_upper_pct": pct(logs[9]),
                       "strict_upper_under_3pct": pct(logs[9]) < 3,
                       "shorter_pairs": sum(p["candidate"] < p["parent"] for p in pairs),
                       "parent_median_Ir": statistics.median(p["parent"] for p in pairs),
                       "candidate_median_Ir": statistics.median(p["candidate"] for p in pairs),
                       "pairs": pairs}
    return {"histories": results, "passed": all(r["strict_upper_under_3pct"] for r in results.values()),
            "per_history_one_sided_coverage": 1 - 79/4096, "simultaneous_lower_bound": 1 - 158/4096,
            "metric": "all application basic-block entry instructions in the resolved native rustc process"}


if __name__ == "__main__":
    rows = json.loads(Path(sys.argv[1]).read_bytes())
    plan = json.loads(Path(sys.argv[2]).read_bytes())
    print(json.dumps(analyze(rows, plan), indent=2))
