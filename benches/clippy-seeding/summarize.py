#!/usr/bin/env python3
"""Validate and reduce the four APFS receipts without treating inode totals as allocation."""
import argparse
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--arms", default="off1,on1,on2,off2")
    args = parser.parse_args()
    rows = {}
    receipts = {}
    for label in args.arms.split(","):
        data = json.loads((args.results / label / "receipt.json").read_text())
        receipts[label] = data
        assert data["complete"] and data["enabled"] == label.startswith("on")
        assert all(command["returncode"] == 0 for command in data["commands"])
        assert all(measurement["stable"] for measurement in data["measurements"].values())
        steps = {command["name"]: command for command in data["commands"]}
        measurements = data["measurements"]
        source_bytes = measurements["sources"]["volume_used_bytes"]
        retained = {name: value["volume_used_bytes"] - source_bytes
                    for name, value in measurements.items() if name not in ["empty", "sources"]}
        # Exclude checkout/fetch/setup and allocator measurement overhead from command timings.
        commands = [step for name, step in steps.items() if int(name[:2]) >= 2]
        row = {"cargo_sha256": data["cargo_sha256"], "rustc_sha256": data["rustc_sha256"],
               "retained_physical_bytes_after_source_checkout": retained,
               "workflow_wall_seconds": sum(step["elapsed_seconds"] for step in commands),
               "workflow_child_cpu_seconds": sum(step["child_user_seconds"] + step["child_system_seconds"] for step in commands),
               "steps": {name: {key: step[key] for key in ["elapsed_seconds", "child_user_seconds", "child_system_seconds", "compiling_lines", "summaries"]}
                         for name, step in steps.items() if int(name[:2]) >= 2},
               "final_artifact_groups_clone_unaware": measurements["final"]["artifact_groups"]}
        if "donor" in measurements:
            row["child_marginal_physical_bytes"] = measurements["final"]["volume_used_bytes"] - measurements["donor"]["volume_used_bytes"]
            row["fork_and_child_wall_seconds"] = sum(step["elapsed_seconds"] for name, step in steps.items() if int(name[:2]) >= 5)
        rows[label] = row
    assert len({row["cargo_sha256"] for row in rows.values()}) == 1
    assert len({row["rustc_sha256"] for row in rows.values()}) == 1
    pairs = []
    for suffix in sorted(label[3:] for label in rows if label.startswith("off")):
        off, on = rows["off" + suffix], rows["on" + suffix]
        def change(a, b):
            return 100 * (b / a - 1)
        pair = {"pair": suffix,
                "workflow_wall_change_percent": change(off["workflow_wall_seconds"], on["workflow_wall_seconds"]),
                "workflow_child_cpu_change_percent": change(off["workflow_child_cpu_seconds"], on["workflow_child_cpu_seconds"]),
                "retained_physical_change_percent": {name: change(value, on["retained_physical_bytes_after_source_checkout"][name])
                    for name, value in off["retained_physical_bytes_after_source_checkout"].items()}}
        if "child_marginal_physical_bytes" in off:
            pair["child_marginal_physical_change_percent"] = change(off["child_marginal_physical_bytes"], on["child_marginal_physical_bytes"])
            pair["fork_and_child_wall_change_percent"] = change(off["fork_and_child_wall_seconds"], on["fork_and_child_wall_seconds"])
        pairs.append(pair)
    aggregates = {}
    for metric in ["workflow_wall_seconds", "workflow_child_cpu_seconds", "fork_and_child_wall_seconds", "child_marginal_physical_bytes"]:
        values = {mode: [row[metric] for label, row in rows.items() if label.startswith(mode)]
                  for mode in ["off", "on"]}
        aggregates[metric] = {mode: {"samples": samples, "median": statistics.median(samples),
                                    "min": min(samples), "max": max(samples)}
                              for mode, samples in values.items()}
        aggregates[metric]["change_percent"] = change(statistics.median(values["off"]), statistics.median(values["on"]))
    for step in next(iter(rows.values()))["steps"]:
        values = {mode: [row["steps"][step]["elapsed_seconds"] for label, row in rows.items() if label.startswith(mode)]
                  for mode in ["off", "on"]}
        aggregates[step] = {mode: {"samples": samples, "median": statistics.median(samples),
                                  "min": min(samples), "max": max(samples)}
                            for mode, samples in values.items()}
        aggregates[step]["change_percent"] = change(statistics.median(values["off"]), statistics.median(values["on"]))
    print(json.dumps({"rows": rows, "pairs": pairs, "aggregates": aggregates,
                      "sample_order": args.arms.split(","),
                      "timing_caveat": next(iter(receipts.values()))["timing_caveat"],
                      "allocation_scope": "Dedicated APFS volume growth after donor checkout: build and incremental state, plus child checkout in the seeding workflow."}, indent=2))


if __name__ == "__main__":
    main()
