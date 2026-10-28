"""Audit real-edit raw records and write the summary and executable roster."""

import csv
import json
import math
from pathlib import Path
import re
import statistics
import sys


def summarize(root):
    protocol = json.loads((root / "protocol.json").read_text())
    rows = list(csv.DictReader((root / "pairs.csv").open()))
    n = protocol["pairs"]
    assert len(rows) == 2 * n
    assert len({row["source_sha256"] for row in rows}) == n
    arms = {"base": [], "candidate": []}
    locks = {"base": [], "candidate": []}
    work = {}
    rosters = {}
    for pair in range(n):
        trial = rows[2 * pair:2 * pair + 2]
        assert [r["arm"] for r in trial] == protocol["order"][pair]
        assert trial[0]["source_sha256"] == trial[1]["source_sha256"]
        pair_work = []
        for pos, r in enumerate(trial):
            arm = r["arm"]
            assert int(r["pair"]) == pair and int(r["order"]) == pos
            body = (root / f"pair-{pair:02}-{pos}-{arm}.log").read_text()
            compiled = sorted(re.findall(r"^\s*(Checking|Compiling) (.+)$", body, re.M))
            exes = sorted(re.findall(r"^\s*Executable (.+)$", body, re.M))
            assert compiled == [tuple(item) for item in json.loads(r["compiled"])]
            assert any(re.match(r"uv v\d", desc) for _, desc in compiled)
            assert "test_executables" not in r or exes == json.loads(r["test_executables"])
            assert re.search(r"^\s*Finished ", body, re.M)
            assert not re.search(r"^\s*(?:Running|Downloading|Updating) |^running \d+ tests?", body, re.M)
            assert root.name != "test" or any(exe.startswith("tests/it/main.rs ") for exe in exes)
            value = int(r["value"])
            if protocol.get("mode", "dynamorio") == "dynamorio":
                traces = re.findall(r"^DynamoRIO (.+)$", body, re.M)
                assert len(traces) == 1
                trace = json.loads(traces[0])
                assert str(trace["pid"]) in trace["threads"]
                assert sum(trace["threads"].values()) == trace["instructions"] == value
            arms[arm].append(value)
            locks[arm].append(body.count("Blocking waiting for file lock on package cache"))
            pair_work.append((compiled, exes))
        assert pair_work[0] == pair_work[1]
        compiled, exes = pair_work[0]
        packages = tuple(f"{action} {desc.split(' (', 1)[0]}" for action, desc in compiled)
        work.setdefault(packages, []).append(pair)
        if exes:
            rosters.setdefault(tuple(exes), []).append(pair)

    gains = sorted(1 - c / b for b, c in zip(arms["base"], arms["candidate"]))
    absolute = [b - c for b, c in zip(arms["base"], arms["candidate"])]
    wins, losses = sum(g > 0 for g in gains), sum(g < 0 for g in gains)
    rank = max((k for k in range(1, n // 2 + 1)
                if 2 * sum(math.comb(n, j) for j in range(k)) / 2**n <= 0.05), default=0)
    summary = dict(pairs=n, wins=wins, base_median=statistics.median(arms["base"]),
                   candidate_median=statistics.median(arms["candidate"]),
                   median_paired_absolute_saving=statistics.median(absolute),
                   median_paired_proportional_saving=statistics.median(gains),
                   median_interval=[gains[rank-1], gains[-rank]] if rank else None,
                   interval_coverage=1 - 2 * sum(math.comb(n, j) for j in range(rank)) / 2**n,
                   exact_two_sided_p=min(1, 2 * sum(math.comb(wins+losses, j) for j in
                                         range(max(wins, losses), wins+losses+1)) / 2**(wins+losses)),
                   package_rosters=[dict(packages=k, pairs=v) for k, v in work.items()],
                   test_executable_rosters=[dict(executables=len(k), pairs=v) for k, v in rosters.items()],
                   package_cache_lock_diagnostics=locks)
    for i, (roster, pairs) in enumerate(rosters.items()):
        (root / f"executables-{i}.txt").write_text(f"Pairs: {pairs}\n" + "\n".join(roster) + "\n")
    return summary


if __name__ == "__main__":
    study = Path(sys.argv[1])
    result = {ep: summarize(study / ep) for ep in ["check", "build", "test"]}
    (study / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
