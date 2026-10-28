#!/usr/bin/env python3
"""Print the next stage, failure, or slow-build alert without running any build work."""
import argparse
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("arm")
parser.add_argument("stage", choices=["profile", "ready"])
parser.add_argument("--acknowledged-slow", action="append", default=[])
a = parser.parse_args()
suite = Path("work/pgo-intermediates")
rec = suite / "records" / a.arm
until = rec / ("profile-info.json" if a.stage == "profile" else "ready.json")
while True:
    if until.exists():
        try:
            report = json.loads(until.read_text())
        except json.JSONDecodeError:
            time.sleep(0.05)
            continue
        print(
            until, report.get("cargo_sha256", ""), report["profdata_sha256"], flush=True
        )
        break
    commands = [
        json.loads(line)
        for line in (suite / "commands.jsonl").read_text().splitlines()
        if line.endswith("}")
    ]
    for row in commands:
        if row.get("status", 0):
            raise SystemExit(
                f'Failed subprocess, retained log {row["log"]} ({row["status"]})'
            )
    records = {}
    for row in commands:
        records.setdefault(row["log"], {}).update(row)
    slow = [
        (p, r)
        for p, r in records.items()
        if p.endswith(".build.log")
        and "finish" not in r
        and time.time() - r["start"] >= 14 * 60
        and Path(p).parent.name + "/" + Path(p).name not in a.acknowledged_slow
    ]
    if slow:
        p, r = slow[-1]
        raise SystemExit(f"Build phase {p} exceeded 14 minutes without completion")
    runner = Path("work/pgo-holdout/intermediates.log").read_text()
    if "Traceback (most recent call last)" in runner or "command failed" in runner:
        raise SystemExit(runner[-1000:])
    time.sleep(5)
