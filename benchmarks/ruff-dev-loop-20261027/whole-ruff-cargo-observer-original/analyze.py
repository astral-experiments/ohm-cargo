"""Audit saved native receipts and analyze the two fixed families without third-party packages."""

import csv
import itertools
import math
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compare_elf, trace, dump, load, need, sha


def evaluate(orders, durations):
    need(
        len(orders) == len(durations) == 12
        and sum(o[0] == "parent" for o in orders) == 6
        and all(set(o) == {"parent", "candidate"} and len(o) == 2 for o in orders),
        "unbalanced order",
    )
    per_arm = {a: [] for a in ("parent", "candidate")}
    slot = []
    ratios = []
    for order, pair in zip(orders, durations):
        need(len(pair) == 2 and all(isinstance(t, int) and t > 0 for t in pair), pair)
        values = dict(zip(order, pair))
        for a in per_arm:
            per_arm[a].append(values[a] / 1e9)
        slot.append(math.log(pair[1] / pair[0]))
        ratios.append(math.log(values["candidate"] / values["parent"]))
    observed = st.mean(ratios)
    extreme = 0
    all_assignments = 0
    for perm in itertools.combinations(range(12), 6):
        second = set(perm)
        v = st.mean(value if n in second else -value for n, value in enumerate(slot))
        extreme += abs(v) + 1e-12 >= abs(observed)
        all_assignments += 1
    need(all_assignments == 924, all_assignments)
    rng = random.Random(831361)
    sampled = sorted(100 * (-math.expm1(st.mean(rng.choices(ratios, k=12)))) for _ in range(20000))
    return dict(
        median_s={a: st.median(ts) for a, ts in per_arm.items()},
        faster_pairs=sum(x < 0 for x in ratios),
        geometric_wall_time_reduction_pct=-100 * math.expm1(observed),
        paired_bootstrap_95_pct=[sampled[499], sampled[19500]],
        exact_two_sided_balanced_p=extreme / all_assignments,
        assignments=all_assignments,
        extreme_assignments=extreme,
        bootstrap_seed=831361,
        bootstrap_reps=20000,
    )


def holm(reports):
    need(set(reports) == {"build", "test"}, "both registered endpoints required")
    prior = 0
    for i, item in enumerate(sorted(reports.values(), key=lambda x: x["exact_two_sided_balanced_p"])):
        adjusted = min(1, max(prior, (2 - i) * item["exact_two_sided_balanced_p"]))
        item["holm_p"] = prior = adjusted
        item["qualifies_for_speedup"] = adjusted < 0.05 and item["paired_bootstrap_95_pct"][0] > 0


def audit(out):
    need(load(out / "complete.json")["source_clean"], "incomplete attempt")
    subjects = load(out / "subjects.json")
    registered = load(out / "plan.json")
    need(sha(out / "plan.json") == subjects["plan"], "changed plan")
    spec = registered["cargo_companion_support"]
    reports = {}
    for mode in ("build", "test"):
        loc = out / mode
        orders = spec[mode]["orders"]
        rows = list(csv.DictReader((loc / "observations.csv").open()))
        need(len(rows) == 24, mode)
        durations = []
        mechanism = {}
        quality = {}
        for n, order in enumerate(orders, 1):
            pair = []
            for j, arm in enumerate(order, 1):
                row = rows[2 * (n - 1) + j - 1]
                need([row["pair"], row["slot"], row["arm"]] == [str(n), str(j), arm], row)
                step = loc / arm / f"pair-{n:02}"
                raw = load(step / "receipt.json")
                inv = load(step / "invocation.json")
                base = load(loc / arm / "preflight/receipt.json")
                cmd = (
                    ["cargo", "+ohm", mode]
                    + (["--no-run"] if mode == "test" else [])
                    + ["--locked", "--offline"]
                )
                need(
                    raw["argv"] == inv["argv"] == cmd
                    and raw["timed"]
                    and raw["returncode"] == 0
                    and raw["elapsed_ns"] == inv["elapsed_ns"] == int(row["elapsed_ns"]),
                    row,
                )
                need(not any(step.glob("exec.*")) and raw["diagnostics"] == base["diagnostics"], step)
                if arm == "candidate":
                    need(raw["candidate_elf_stats_unchanged"] and not raw["compile_status"], step)
                pair.append(raw["elapsed_ns"])
            durations.append(pair)
        for arm in ("parent", "candidate"):
            witness = {
                p: load(loc / arm / p / "receipt.json")
                for p in ("cold", "training", "preflight", "final", "edit", "restore", "restored-noop")
            }
            initial = witness["preflight"]
            mechanism[arm] = {}
            for p, raw in witness.items():
                physical = trace(loc / arm / p)
                need(physical == load(loc / arm / p / "trace.json"), ["raw trace discrepancy", mode, arm, p])
                need(
                    raw["cargo"] == subjects["cargo"][arm]
                    and raw["driver"] == subjects["driver"]
                    and initial["roster"] == raw["roster"]
                    and initial["executables"] == raw["executables"],
                    [mode, arm, p],
                )
                need(physical["rustc"] == raw["rustc"] and physical["linkers"] == raw["linkers"], p)
                need(physical["executions"] and any((loc / arm / p).glob("exec.*")), p)
                mechanism[arm][p] = dict(
                    total_units=raw["units"],
                    dirty_units=len(raw["dirty"]),
                    rustc_full=sum(t[1] == "full" for t in raw["rustc"]),
                    rustc_link_only=sum(t[1] == "link-only" for t in raw["rustc"]),
                    linkers=len(raw["linkers"]),
                    elf_products=len(raw["elf"]),
                    executable_paths=len(raw["executables"]),
                )
                if p in ("preflight", "final", "restored-noop") and arm == "candidate":
                    need(
                        not raw["dirty"]
                        and not raw["rustc"]
                        and not raw["linkers"]
                        and not physical["target_execs"],
                        [arm, p],
                    )
            need(
                all(
                    initial[k] == witness["final"][k]
                    for k in ("roster", "diagnostics", "compiler_messages", "dirty", "rustc", "linkers")
                ),
                arm,
            )
            need(
                witness["edit"]["diagnostics"] != initial["diagnostics"]
                and witness["restore"]["diagnostics"] == initial["diagnostics"],
                [arm, mode],
            )
            quality[arm + "-unexplained_rejected_known_fields_reported"] = list(
                compare_elf(initial["elf"], witness["final"]["elf"])
            )
        quality["cross_arm_masked_only_differences"] = {
            p: list(
                compare_elf(load(loc / "parent" / p / "elf.json"), load(loc / "candidate" / p / "elf.json"))
            )
            for p in ("preflight", "final", "edit", "restore")
        }
        reports[mode] = dict(
            evaluate(orders, durations),
            registered_orders=orders,
            mechanism=mechanism,
            elf_comparisons=quality,
        )
    holm(reports)
    dump(out / "statistics.json", reports)
    return reports


if __name__ == "__main__":
    print(__import__("json").dumps(audit(Path(sys.argv[1])), indent=2))
