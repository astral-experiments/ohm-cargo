"""Render the Ohm and uv report from original paired measurements."""
import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from statistics import median


COMMANDS = {"check": "check", "build": "build", "test": "test --no-run"}
STEPS = [
    ("unit", 264, "Borrow unit dependencies", "test"),
    ("warnings", 267, "Defer unused-key warning paths", "check"),
    ("feature", 268, "Cache filtered feature dependencies", "check"),
    ("depfile", 269, "Borrow unescaped depfile paths", "build"),
    ("semver", 270, "Move locked version requirements", "check"),
]


@dataclass(frozen=True)
class Stats:
    base: float
    head: float
    gain: float
    low: float
    high: float
    n: int
    wins: int
    ties: int
    p: float


def interval_rank(n):
    for k in range(n // 2, 0, -1):
        coverage = 1 - 2 * sum(math.comb(n, i) for i in range(k)) / 2**n
        if coverage >= 0.95:
            return k, coverage
    raise ValueError(f"no finite distribution-free 95% median interval for {n} pairs")


def stats(pairs):
    base, head = zip(*pairs)
    gains = sorted(1 - b / a for a, b in pairs)
    n = len(gains)
    k, _ = interval_rank(n)
    wins = sum(x > 0 for x in gains)
    ties = gains.count(0)
    used = n - ties
    tail = sum(math.comb(used, i) for i in range(max(wins, used - wins), used + 1))
    return Stats(median(base), median(head), median(gains), gains[k-1], gains[-k],
                 n, wins, ties, min(1, 2 * tail / 2**used))


def cohort(root, name, ep, expected, mode):
    edited = name.startswith("edit-holdout-")
    folder = root / name / ep if edited else root / name
    samples = folder / "pairs.csv"
    if not samples.exists():
        return "No samples"
    meta = json.loads((folder / "protocol.json").read_text())
    if meta.get("mode", "dynamorio") != mode or meta["pairs"] != expected:
        raise ValueError(f"unexpected mode or trial count in {folder}")
    scale = 1
    if mode == "wall" and edited:
        if "nanoseconds" not in meta["metric"]:
            raise ValueError(f"unknown unit for edited wall times in {folder}")
        scale = 1e9
    pairs = {}
    with samples.open() as f:
        for row in csv.DictReader(f):
            if row["endpoint"] != ep:
                continue
            i, pos, arm = int(row["pair"]), int(row["order"]), row["arm"]
            pair = pairs.setdefault(i, {})
            if not (0 <= i < expected and pos in (0, 1) and arm in ("base", "candidate") and arm not in pair):
                raise ValueError(f"invalid or duplicate observation in {samples}: {row}")
            if edited and meta["order"][i][pos] != arm:
                raise ValueError(f"arm order disagrees with the registered schedule in {samples}")
            value = float(row["value"]) / scale
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"invalid observation in {samples}: {value}")
            pair[arm] = (pos, value)
    complete = [pair for pair in pairs.values() if len(pair) == 2]
    if len(complete) != expected:
        return f"Incomplete ({len(complete)}/{expected} pairs)" if pairs else "No samples"
    if (any(a["base"][0] == a["candidate"][0] for a in complete)
            or sum(a["base"][0] == 0 for a in complete) != expected // 2):
        raise ValueError(f"unbalanced paired order in {samples}")
    return stats([(p["base"][1], p["candidate"][1]) for p in complete])


def gate(primary, repeat, alpha, positive_interval=False):
    def outcome(r, threshold, require_interval):
        if isinstance(r, str):
            return r.lower()
        if r.p < threshold and r.gain > 0 and (not require_interval or r.low > 0):
            return "pass"
        if r.p < threshold and r.gain < 0 and (not require_interval or r.high < 0):
            return "slower"
        return "inconclusive"
    first = outcome(primary, alpha, positive_interval)
    second = outcome(repeat, 0.05, False)
    if first == second:
        return {"pass": "Pass", "slower": "Slower in both cohorts", "no samples": "No observations",
                "inconclusive": "Inconclusive in both cohorts"}.get(first, "Incomplete")
    return f"Primary {first}, repeat {second}"


def reduction(r):
    return r if isinstance(r, str) else f"{r.gain:.3%}"


def estimate(r):
    return f"{r.gain:.3%} [{r.low:.3%}, {r.high:.3%}]"


def win_count(r):
    return f"{r.wins}/{r.n}" + (f" ({r.ties} tied)" if r.ties else "")


def table(headings, rows):
    return "\n".join("| " + " | ".join(row) + " |" for row in
                     [headings, ["---"] * len(headings), *rows])


def instruction_table(items):
    rows = []
    for label, ep, r in items:
        data = [r, "—", "—", "—"] if isinstance(r, str) else [
            f"{r.base/1e6:,.2f} → {r.head/1e6:,.2f}", estimate(r), win_count(r), f"{r.p:.6g}"]
        rows.append([label, f"`{COMMANDS[ep]}`", *data])
    return table(["Comparison", "Cargo command", "Parent → candidate (M instructions)",
                  "Paired reduction [rank interval]", "Wins/pairs", "Exact p"], rows)


def wall_cell(r):
    if isinstance(r, str):
        return r
    return (f"{r.base:.4f} → {r.head:.4f} s<br>{estimate(r)}<br>"
            f"{win_count(r)} wins, p = {r.p:.6g}")


def wall_table(root, studies):
    rows = []
    for label, name, n, interval in studies:
        for ep in COMMANDS:
            a = cohort(root, name, ep, n, "wall")
            b = cohort(root, name + "-replica", ep, n, "wall")
            rows.append([label, f"`{COMMANDS[ep]}`", wall_cell(a), wall_cell(b), gate(a, b, 0.05/3, interval)])
    return table(["Workspace", "Cargo command", "Initial", "Independent repeat", "Elapsed-time gate"], rows)


def toolchain_arms(root):
    seen = set()
    for protocol in root.glob("edit-holdout-toolchain-wall*/*/protocol.json"):
        meta = json.loads(protocol.read_text())
        seal = protocol.with_name("seal.json")
        if seal.exists():
            frozen = json.loads(seal.read_text())
            seen.add(tuple(frozen[k][arm] for k in ("cargo_sha256", "wild_sha256") for arm in ("base", "candidate")))
            if meta["cargo_sha256"]["base"] != frozen["cargo_sha256"]["base"] or meta["wild_sha256"] != frozen["wild_sha256"]:
                raise ValueError(f"protocol and seal disagree in {protocol.parent}")
            raw = protocol.with_name("pairs.csv")
            if raw.exists():
                with raw.open() as invocations:
                    for r in csv.DictReader(invocations):
                        if any(r[k] != frozen[k][r["arm"]] for k in ("cargo_sha256", "wild_sha256")):
                            raise ValueError(f"unsealed executable in {raw}")
        elif protocol.with_name("pairs.csv").exists():
            raise ValueError(f"all-components observations lack a pre-measurement seal in {protocol.parent}")
    if len(seen) > 1:
        raise ValueError("all-components cohorts used different Cargo or Wild binaries")
    if not seen:
        return ""
    (old_cargo, new_cargo, old_wild, new_wild), = seen
    return (f" Sealed Cargo SHA-256 prefixes are `{old_cargo[:12]}` → `{new_cargo[:12]}`. "
            f"Wild prefixes are `{old_wild[:12]}` → `{new_wild[:12]}`.")


def edit_roster(root):
    rosters = set()
    rebuilds = set()
    for ep in COMMANDS:
        path = root / "edit-holdout-cumulative" / ep / "pairs.csv"
        if not path.exists():
            return None
        with path.open() as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 16:
            return None
        for r in rows:
            rebuilds.add(tuple(sorted({name.split(" (", 1)[0] for _, name in json.loads(r["compiled"])})))
            if ep == "test":
                rosters.add(tuple(json.loads(r["test_executables"])))
    if len(rosters) != 1:
        raise ValueError("full-workspace edited test executables differed across invocations")
    if len(rebuilds) != 1:
        raise ValueError("full-workspace edits did not rebuild the same package set")
    packages, = rebuilds
    roster, = rosters
    owners = {re.search(r"/debug/build/([^/]+)/", path)[1] for path in roster}
    return (f"All 48 edited invocations rebuilt exactly `{', '.join(packages)}`. "
            f"All 16 test builds reported the same {len(roster)} executables from {len(owners)} packages.")


def component_results(root):
    blocks = ["## Standard library and linker drafts",
              "The standard-library change scans shared path prefixes a machine word at a time. "
              "Both Cargo executables were rebuilt with the released Ohm compiler, ThinLTO and one "
              "codegen unit. The original distribution's PGO profile was unavailable. "
              "The test matrix includes the public `Path` suite, an added ordering regression test, "
              "and three independent comparison oracles. [Rust #247](https://github.com/astral-sh/ohm-rust/pull/247)",
              instruction_table([(label, 'build', cohort(root, name, 'build', n, mode))
                                 for label, name, n, mode in (
                                     ('76-byte checkout, DynamoRIO', 'std-path-confirm', 12, 'dynamorio'),
                                     ('28-byte checkout, Cachegrind', 'std-path-replica', 8, 'instructions'))]),
              "Replaying 93,550 recorded path comparisons saved 45.64% of the instructions in the "
              "isolated workload. Long paths that differ in their second byte cost three extra "
              "instructions per comparison (+0.21%)."]
    original = root / 'edit-link-profile/native-instrument/paired-undefined-normal-confirmatory/block-results.csv'
    packed = root.parent / 'components/wild/edited/block-results.csv'
    file = original if original.is_file() else packed
    if file.is_file():
        with file.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 8 and sorted(row['order'] for row in rows) == ['ABBA'] * 4 + ['BAAB'] * 4
        r = stats([(int(row['baseline_instructions']), int(row['candidate_instructions'])) for row in rows])
        blocks += [f"Wild moves undefined-symbol reporting into a cold function. Each real edited "
                   f"`cargo test --no-run` launched five linkers. All eight four-command blocks improved "
                   f"across 160 linker processes. The median reduction in Wild instructions was {estimate(r)} "
                   f"(two-sided sign p = {r.p:.6g}, order-conditioned randomization p = 0.02857). "
                   "An independent Callgrind replay of the largest link saved 1.155%. "
                   "All 20 serial ELF replays and 18 native parallel replays matched their respective "
                   "reference outputs. [Wild #45](https://github.com/astral-sh/ohm-wild/pull/45)"]
    blocks += ["## Combined Cargo and standard-library driver",
               "These direct comparisons use identically built Cargo executables with the parent or "
               "all five Cargo changes plus the standard-library change. A settled workspace invokes "
               "no linker. The two checkout lengths expose variation in the path-scanning gain.",
               instruction_table([('28-byte checkout, DynamoRIO', ep,
                                   cohort(root, 'std-path-stack-confirm', ep, 8, 'dynamorio')) for ep in COMMANDS]
                                 + [('76-byte checkout, Cachegrind', 'build',
                                     cohort(root, 'std-path-stack-replica', 'build', 8, 'instructions'))]),
               wall_table(root, [('Warm', 'std-path-stack-wall', 48, True)]),
               "## Independently built Cargo drivers",
               "The standalone build script rebuilt the original and fifth Cargo revisions from clean "
               "source archives. A second comparison applied all five changes to the exact source of "
               "the concurrent Cargo stack through #266. These runs used Cachegrind. "
               "[Cargo #266](https://github.com/astral-sh/ohm-cargo/pull/266)",
               instruction_table([('Clean driver builds', ep, cohort(root, 'cumulative-repro-build' if ep == 'build' else
                                     'cumulative-repro-remaining', ep, 8, 'instructions')) for ep in COMMANDS]
                                 + [('Concurrent stack', ep, cohort(root, 'cumulative-rc18', ep, 8, 'instructions'))
                                    for ep in COMMANDS]),
               "The fresh-build check harness rejected an invocation that rebuilt dependencies. Its "
               "log is retained. Subsequent native and instrumented traces were fresh. The remaining "
               "check and test cohorts required the second instrumented warmup for each arm to be "
               "fresh before collecting their full eight pairs."]
    return blocks


def render(root):
    blocks = ["# Ohm developer-loop performance on uv",
              "Five stacked Cargo changes, one standard-library change and one Wild change were measured "
              "on the pinned uv workspace using "
              "Ohm 1.99.0-17. A warm command reuses its settled build artifacts. An edited command "
              "rebuilds after a change to the private installation-source predicate in an archived "
              "copy of uv. All test-construction commands use `--no-run`. "
              "[uv source](https://github.com/astral-sh/uv/tree/c22e6b71933443e9cd299d4b6ac8de035ed4825b) · "
              "[Cargo baseline](https://github.com/astral-sh/ohm-cargo/tree/a0c7d08c898d3fdff992f2f431dec57d2486add2)",
              "## Five changes together",
              "Dynamic counts cover user-space instructions in the Cargo process and its threads. "
              "Kernel work and executed compiler and linker subprocesses are outside that count. "
              "Native elapsed time below includes the whole command "
              "from launch through exit. Each comparison uses the same binary and target paths for both arms."]
    combined = []
    for label, name, n in [("Warm workspace", "cumulative-confirm", 12),
                           ("Edited workspace", "edit-holdout-cumulative", 8)]:
        combined += [(label, ep, cohort(root, name, ep, n, "dynamorio")) for ep in COMMANDS]
    blocks.append(instruction_table(combined))
    if roster := edit_roster(root):
        blocks.append(roster)
    blocks.extend(["## Native elapsed time for the five Cargo changes",
                   "The `matched-base` and `semver` Cargo drivers run the same released Ohm rustc and Wild. "
                   "Each cell gives baseline → stack median seconds, then the median paired reduction "
                   "and rank interval, wins, and exact two-sided sign-test p. A speedup requires "
                   "positive medians, p < 0.05/3 on the initial cohort and p < 0.05 on its independent "
                   "repeat. The warm-workspace gate also requires a positive initial interval."])
    blocks.append(wall_table(root, [("Warm", "cumulative-wall", 48, True),
                                    ("Edited", "edit-holdout-cumulative-wall", 8, False)]))
    if (root / 'native-diagnostic.json').exists():
        blocks += ["A formatter invocation pinned to CPU 28 started a rustup download during the warm "
                   "five-Cargo repeat. It was interrupted after 18 seconds. The original observations, "
                   "overlap timestamps and host telemetry are included in the archive. An additional "
                   "48-pair repeat used a fresh balanced order after the scheduled runs and an idle preflight. "
                   "The original qualification gate still applies.",
                   table(['Extra warm repeat', 'Parent → candidate, paired reduction and interval'],
                         [[f'`{COMMANDS[ep]}`', wall_cell(cohort(root, 'cumulative-wall-clean-repeat', ep, 48, 'wall'))]
                          for ep in COMMANDS])]
    if (root / "edit-holdout-toolchain-wall").exists():
        blocks += ["## Native elapsed time for the combined Cargo, standard-library and Wild changes",
                   "The baseline uses the `base` Cargo driver and `wild-baseline`. The candidate uses "
                   "`guard-stack`, which contains the five Cargo changes and the guarded standard-library "
                   "path comparison, with `wild-undefined`. The same released Ohm rustc compiles uv in "
                   "both arms. Each comparison uses a private copy of the release with a stable linker path."
                   + toolchain_arms(root),
                   wall_table(root, [("Edited", "edit-holdout-toolchain-wall", 8, False)])]
    blocks += component_results(root)
    blocks += ["## Individual Cargo draft PRs",
               "Each change is measured against its immediate parent. The initial primary uses DynamoRIO, "
               "and the independently warmed repeat uses Cachegrind. The additional release-style "
               "comparison uses Cachegrind with binaries built by the Ohm compiler using ThinLTO, one "
               "codegen unit and statically linked native libraries. The published distribution's PGO "
               "profile was unavailable for these source builds. The primary threshold is p < 0.05/6 "
               "and the repeat threshold is p < 0.05."]
    compact, details = [], []
    for stage, number, title, primary in STEPS:
        conf = {ep: cohort(root, stage+"-confirm", ep, 12, "dynamorio") for ep in COMMANDS}
        rep = cohort(root, stage+"-replica", primary, 8, "instructions")
        rel = cohort(root, stage+"-release-like", primary, 8, "instructions")
        link = f"[#{number} {title}](https://github.com/astral-sh/ohm-cargo/pull/{number})"
        compact.append([link, f"`{COMMANDS[primary]}`", reduction(conf[primary]), reduction(rep),
                        reduction(rel), gate(conf[primary], rep, 0.05/6)])
        details.extend((f"#{number} initial", ep, r) for ep, r in conf.items())
        details.extend([(f"#{number} repeat", primary, rep), (f"#{number} release-style", primary, rel)])
    blocks += [table(["Draft", "Primary command", "Initial reduction", "Repeat", "Release-style", "Instruction gate"], compact),
               "<details>\n<summary>Arm medians, intervals and sign tests for each change</summary>",
               instruction_table(details), "</details>"]
    rss = cohort(root, "feature-memory", "check", 16, "rss")
    if isinstance(rss, str):
        blocks.append(f"Feature-cache peak RSS on warm check. {rss}.")
    else:
        blocks.append(f"Keeping the filtered dependencies increased peak RSS on warm `cargo check`. "
                      f"GNU time reported parent and candidate medians of {rss.base/1024:.1f} and "
                      f"{rss.head/1024:.1f} MiB. The median paired increase was {-rss.gain:.3%} "
                      f"[{-rss.high:.3%}, {-rss.low:.3%}] across {rss.n} pairs (p = {rss.p:.6g}).")
    unit = [(args, ep, cohort(root, "edit-holdout-unit", ep, 8, "dynamorio")) for ep, args in
            [("check", "`-p uv --lib`"), ("build", "`-p uv`"), ("test", "`-p uv --test it`")]]
    blocks += ["<details>\n<summary>Package-targeted real edits for the first draft</summary>",
               instruction_table(unit), "</details>", "## Reading the measurements",
               "Reductions are medians of paired `1 − candidate/parent` values. Arm columns are separate "
               "medians. Positive reductions mean less work or elapsed time. The exact two-sided sign test "
               "omits ties. Distribution-free intervals use symmetric order statistics at the highest "
               "rank that retains at least 95% coverage. Actual coverage is "
               + ", ".join(f"{interval_rank(n)[1]:.2%} at {n} pairs" for n in (8, 12, 16, 48)) + ".",
               "The warm instruction cohorts use `--locked --offline -j16` and the real-edit cohorts "
               "use `-j8`. Each edited comparison changes the same source bytes for both arms and "
               "moves each arm's copy of a common warmed target to the same visible path. All reported "
               "comparisons use fixed balanced pair counts. Missing or partial cohorts cannot pass a gate."]
    return "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=here, help="work directory or unpacked runs directory")
    parser.add_argument("--output", type=Path, default=here / "results-preview.md")
    args = parser.parse_args()
    args.output.write_text(render(args.runs))
