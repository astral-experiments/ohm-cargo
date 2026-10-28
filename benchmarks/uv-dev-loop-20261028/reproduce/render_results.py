"""Render the Ohm and uv report from original paired measurements."""
import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wild_prefix_evidence import block_rows


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
    meta = root / 'wild-prefix/pr.json'
    if meta.is_file():
        prefix = root / json.loads(meta.read_text())['directory']
    else:
        prefix = root.parent / 'components/wild-prefix'
        meta = prefix / 'pr.json'
    if meta.is_file():
        pr = json.loads(meta.read_text())
        _, pairs = block_rows(prefix)
        real = stats([(b['baseline_instructions'], b['candidate_instructions']) for b in pairs])
        records = [('Edited test builds, five linkers per command', real)]
        for name, label in [('uv', 'Independent 319 MB uv executable'),
                            ('uv-c84366b26c530121', 'Independent 10 MB test harness')]:
            with (prefix / 'links' / f'{name}.csv').open() as stream:
                raw = list(csv.DictReader(stream))
            assert len(raw) == 20 and len({v['output_sha256'] for v in raw}) == 1
            groups = [{r['arm']: int(r['linker_instructions']) for r in raw if int(r['pair']) == i} for i in range(10)]
            records.append((label, stats([(g['parent'], g['v2']) for g in groups])))
        with (prefix / 'pilot/samples.csv').open() as stream:
            pilot = list(csv.DictReader(stream))
        controls = []
        for name, label in [('partial', '188-member uv-client archive, partial link'),
                            ('script', 'Data-heavy object, custom script'), ('data', 'Same object, default rules')]:
            raw = [r for r in pilot if r['case'] == name]
            assert len(raw) == 18 and len({r['out_sha256'] for r in raw}) == 1
            groups = [{r['arm']: int(r['instructions']) for r in raw if int(r['block']) == i} for i in range(6)]
            controls.append([label, *(f'{median(g[a] / g["parent"] - 1 for g in groups):+.4%}' for a in ('v1', 'v2'))])
        artifacts = json.loads((prefix / 'actual/artifacts.json').read_text())
        equal = sum(set(g['observed']['parent']) == set(g['observed']['v2']) for g in artifacts.values())
        variants = sum(len(g['observed']['parent']) > 1 for g in artifacts.values())
        restricted = json.loads((prefix / 'actual/summary.json').read_text())['sign_and_permutation_p'][1]
        blocks += [f"## Second Wild change, on top of #45",
                   "Wild recognizes the default `.text*` and `.rela*` ELF placement rules from a validated "
                   "section-name table. Both arms used the same Cargo rebuilt from unmodified release sources "
                   "and the same shipped rustc. The primary workload executed 32 edited `cargo test --no-run "
                   "--locked --offline -j4` commands and counted all threads in 160 Wild invocations. The "
                   f"balanced-order randomization p was {restricted:.6g}. [Wild #{pr['number']}]({pr['url']})",
                   table(['Workload', 'Wild instruction reduction [rank interval]', 'Improved', 'Sign p'],
                         [[label, estimate(r), win_count(r), f'{r.p:.6g}'] for label, r in records]),
                   f"The complete output digest sets matched for {equal}/{len(artifacts)} output and edit "
                   f"combinations. The parent itself produced multiple complete digests in {variants} combinations. "
                   "Both reserved replay inputs reproduced their reference bytes on all 40 invocations. "
                   "[Output digests](components/wild-prefix/actual/artifacts.json) · "
                   "[Byte comparisons](components/wild-prefix/actual/byte-differences.json)",
                   "Controls used six complete permutations of parent, first implementation and published "
                   "implementation. Positive values below are additional instructions relative to #45. "
                   "[Control samples](components/wild-prefix/pilot/samples.csv)",
                   table(['Control', 'First implementation', 'Published implementation'], controls)]
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
    if (root / 'distributed-base/pairs.csv').is_file():
        comparisons = [('Unmodified local build, Cachegrind', 'distributed-base', 'instructions'),
                       ('Combined local build, Cachegrind', 'distributed-guard-stack', 'instructions')]
        if (root / 'distributed-pgo-base/pairs.csv').is_file():
            comparisons += [('Retrained unmodified build, DynamoRIO', 'distributed-pgo-base', 'dynamorio'),
                            ('Retrained combined build, DynamoRIO', 'distributed-pgo-guard-stack', 'dynamorio')]
        blocks += ["## Downloaded release binary",
                   "Each row compares the downloaded Ohm Cargo to a locally built driver at a fixed "
                   "path. The complete packaging, compiler and profile differences enter this comparison. "
                   "The matched parent/candidate rows above isolate the changes in this work.",
                   instruction_table([(label, ep, cohort(root, name, ep, 8, mode))
                                      for label, name, mode in comparisons for ep in COMMANDS])]
        if (root / 'distributed-control/pairs.csv').is_file():
            blocks += ["The negative control put the identical downloaded executable in both arms and "
                       "ran each default Cargo command with a populated offline registry. Its paired "
                       "differences show measurement variation on this host.",
                       instruction_table([('Released binary against itself', ep, cohort(root, 'distributed-control', ep, 8, 'dynamorio'))
                                          for ep in COMMANDS])]
    if (root / 'pgo-confirm/pairs.csv').is_file():
        blocks += ["## Retrained profile-guided builds",
                   "Both source states were instrumented, trained and rebuilt independently with the "
                   "released compiler and identical build paths. Each used the same Diesel and bitmaps "
                   "workloads from the release training corpus. The timed uv checkout was excluded "
                   "from training. The shipped profile covers additional release workloads. "
                   "[Training and build provenance](reproduce/pgo-holdout/README.md)",
                   instruction_table([(label, ep, cohort(root, name, ep, n, mode))
                                      for label, name, n, mode in [('DynamoRIO, 28-byte checkout', 'pgo-confirm', 12, 'dynamorio'),
                                                                    ('Cachegrind, 76-byte checkout', 'pgo-replica', 8, 'instructions')]
                                      for ep in COMMANDS]),
                   table(['Endpoint', 'Registered primary and replication gate'],
                         [[f'`{COMMANDS[ep]}`', gate(cohort(root, 'pgo-confirm', ep, 12, 'dynamorio'),
                                                    cohort(root, 'pgo-replica', ep, 8, 'instructions'), 0.05/3)]
                          for ep in COMMANDS])]
        if (root / 'pgo-ordinary/pairs.csv').is_file():
            blocks += ["The additional default-argument comparison ran `cargo check`, `cargo build` and "
                       "`cargo test --no-run`. Cargo chose its job count, the populated registry stayed "
                       "offline through the environment, and the uv lockfile was checked byte-for-byte.",
                       instruction_table([('Default Cargo arguments', ep, cohort(root, 'pgo-ordinary', ep, 8, 'dynamorio'))
                                          for ep in COMMANDS])]
    if (root / 'pgo-unit-confirm/pairs.csv').is_file():
        rows = []
        for stage, number, title, ep in [*STEPS, ('std', 247, 'Compare path prefixes by word', 'build')]:
            first = cohort(root, f'pgo-{stage}-confirm', ep, 12, 'dynamorio')
            repeat = cohort(root, f'pgo-{stage}-replica', ep, 8, 'instructions')
            repo = 'ohm-rust' if stage == 'std' else 'ohm-cargo'
            rows.append([f'[{title} #{number}](https://github.com/astral-sh/{repo}/pull/{number})',
                         f'`{COMMANDS[ep]}`', estimate(first) if isinstance(first, Stats) else first,
                         estimate(repeat) if isinstance(repeat, Stats) else repeat, gate(first, repeat, 0.05 / 6)])
        blocks += ['## Individual changes under profile-guided optimization',
                   'Each adjacent Cargo revision was trained and rebuilt separately using the same non-uv '
                   'workload. The last row adds the path change to the fifth Cargo revision. The primary '
                   'criterion used two-sided sign p < 0.05/6 on 12 DynamoRIO pairs. The independent '
                   'eight-pair Cachegrind cohort used p < 0.05. Brackets give distribution-free intervals '
                   'for the median paired reduction. [Frozen protocol](reproduce/pgo-steps/registration.json) · '
                   '[Driver, profile and standard-library hashes](profile-build/intermediates/driver-index.tsv)',
                   table(['Change', 'Command', '28-byte checkout', '76-byte checkout', 'Outcome'], rows)]
        profile_comparison = root / 'pgo-intermediates/guard-vs-semver-block-profiles.json'
        if not profile_comparison.is_file():
            profile_comparison = root.parent / 'profile-build/intermediates/guard-vs-semver-block-profiles.json'
        if profile_comparison.is_file():
            profile = json.loads(profile_comparison.read_text())
            blocks.append(f"The final two builds have identical Cargo source and different standard libraries. Their independently "
                          f"collected Cargo profiles shared {profile['common_cfg_hashes']:,} function names and control-flow hashes. "
                          f"Of {profile['equal_cfg_total_counters']:,} comparable basic-block counters, {profile['changed_counters']:,} differed "
                          f"across {profile['functions_with_changed_counters']:,} functions. [Training-profile comparison]"
                          "(profile-build/intermediates/guard-vs-semver-block-profiles.json)")
    return blocks


def render(root):
    extra_linker = (root / 'wild-prefix/pr.json').is_file() or (root.parent / 'components/wild-prefix/pr.json').is_file()
    linker_count = 'two stacked Wild changes' if extra_linker else 'one Wild change'
    blocks = ["# Ohm developer-loop performance on uv",
              f"Five stacked Cargo changes, one standard-library change and {linker_count} were measured "
              "on the pinned uv workspace using "
              "Ohm 1.99.0-17. A warm command reuses its settled build artifacts. An edited command "
              "rebuilds after a change to the private installation-source predicate in an archived "
              "copy of uv. All test-construction commands use `--no-run`. "
              "[uv source](https://github.com/astral-sh/uv/tree/c22e6b71933443e9cd299d4b6ac8de035ed4825b) · "
              "[Cargo baseline](https://github.com/astral-sh/ohm-cargo/tree/a0c7d08c898d3fdff992f2f431dec57d2486add2)",
              "The archive includes the build recipes, original logs, calibration and analysis scripts. "
              "[Reproduction steps](REPRODUCTION.md) · [Ordered samples](samples.csv) · [Reproduction archive](uv-ohm-benchmarks.zip)",
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
    major = root / 'tree-count/identical/summary.md'
    if not major.is_file():
        major = root.parent / 'components/edited-roles/identical/summary.md'
    if major.is_file():
        blocks.append(re.sub(r'^(#{1,5}) ', r'#\1 ', major.read_text().strip(), flags=re.MULTILINE))
        if (major.parent.parent / 'order-sensitivity-results.md').is_file():
            blocks.append('The supplemental randomization test was specified after the initial cohorts and before any independent repeat finished. '
                          'It conditions on the registered balance of baseline-first and candidate-first pairs. '
                          '[Assignment-conditioned results](components/edited-roles/order-sensitivity-results.md)')
    complete = root / 'eight-roles/summary.json'
    if not complete.is_file():
        complete = root.parent / 'components/eight-roles/summary.json'
    if complete.is_file():
        result = json.loads(complete.read_text())
        role_rows = []
        for cohort_name, result_row in result['cohorts'].items():
            if result_row['state'] not in {'qualified', 'inconclusive'}:
                role_rows.append([cohort_name, '—', '—', '—', '—', '—', result_row['state']])
                continue
            arm = result_row['median_instructions_by_role']
            lo, hi = result_row['rank_interval_99_21875']
            role_rows.append([cohort_name, f"{arm['base']['total']/1e9:.3f} → {arm['candidate']['total']/1e9:.3f}",
                              f"{result_row['median_saving']:.3%} [{lo:.3%}, {hi:.3%}]", f"{result_row['wins']}/8",
                              f"{result_row['two_sided_sign_p']:.6g}", f"{result_row['balanced_order_randomization_p']:.6g}", result_row['state']])
        blocks += ['## Edited test-build instructions with all eight changes',
                   'The two arms use separately trained Cargo binaries, the same released rustc, and the parent or stacked Wild. '
                   'The count sums all threads of Cargo, six rustc processes and five Wild processes during each edited '
                   '`cargo test --no-run --locked --offline -j8`. The registration requires both an exact sign test and an '
                   'order-conditioned randomization test to pass in each independent cohort. [Protocol and raw counts](components/eight-roles/)',
                   table(['Cohort', 'Parent → candidate (G instructions)', 'Paired reduction [rank interval]',
                          'Improved', 'Sign p', 'Order p', 'Gate'], role_rows)]
    timing = root / 'eight-wall/summary.md'
    if not timing.is_file():
        timing = root.parent / 'components/eight-wall/summary.md'
    if timing.is_file():
        blocks.append(re.sub(r'^(#{1,5}) ', r'#\1 ', timing.read_text().strip(), flags=re.MULTILINE))
        if (timing.parent / 'order-sensitivity-results.md').is_file():
            blocks.append('The elapsed-time sensitivity analysis was specified before timing and enumerates the 2,704,156 balanced arm allocations in each cohort. '
                          '[Assignment-conditioned results](components/eight-wall/order-sensitivity-results.md)')
        if (timing.parent / 'host-observations.json').is_file():
            blocks.append('The repeat waited 30 seconds for residual writeback before its two clean preflight windows. '
                          'Median I/O wait on the reserved CPUs was 0.252% initially and 0.220% in the repeat. '
                          'Foreign-process checks ran during preflights. The in-window host monitor recorded aggregate counters. '
                          '[Host observations](components/eight-wall/host-observations.json) · '
                          '[Source, process and executable audit](components/eight-wall/complete-audit.json)')
    snapshot = root / 'ci-snapshot.json'
    if not snapshot.is_file():
        snapshot = root.parent / 'verification/ci-snapshot.json'
    if snapshot.is_file():
        ci = json.loads(snapshot.read_text())
        passed = lambda checks: sum(check['conclusion'] == 'SUCCESS' for check in checks)
        cargo = [draft for draft in ci['drafts'] if draft['number'] in {264, 267, 268, 269, 270}]
        rust, = [draft for draft in ci['drafts'] if draft['number'] == 247]
        wild, = [draft for draft in ci['drafts'] if draft['number'] == 45]
        native = ci['wild_native']
        blocks += ['## Correctness and CI',
                   f"The five Cargo drafts have {sum(passed(d['checks']) for d in cargo)} passing checks "
                   f"in total. The Rust draft has {passed(rust['checks'])} passing checks. Wild's release "
                   f"workflow has {sum(c['conclusion'] == 'FAILURE' for c in wild['checks'])} setup failures "
                   "before source checkout because its action references do not satisfy the organization's "
                   f"full-SHA policy. A separate workflow checked out the exact Wild PR head and passed "
                   f"{passed(native['jobs'])} jobs. It covers 12 selected x86-64 ELF cases, four native arm64 "
                   "Mach-O cases, and two AArch64 LLVM 21 fixtures whose release and PR output bytes matched. "
                   f"[Wild CI validation]({native['url']}) · [Recorded checks](verification/ci-snapshot.json)"]
        if 'wild_prefix_native' in ci:
            prefix, = [d for d in ci['drafts'] if '/ohm-wild/' in d['url'] and d['number'] != 45]
            run = ci['wild_prefix_native']
            blocks.append(f"Wild #{prefix['number']} also inherits the release workflow. Its PR checks include "
                          f"{sum(c['conclusion'] == 'FAILURE' for c in prefix['checks'])} setup failures. "
                          f"The native workflow checked out `{prefix['headRefOid'][:12]}` and passed "
                          f"{passed(run['jobs'])} of {len(run['jobs'])} jobs. The suites cover 35 x86-64 ELF fixtures, "
                          "the new ELF regression test, four native arm64 Mach-O fixtures and byte comparisons of two "
                          f"AArch64 LLVM 21 fixtures. [Native run]({run['url']}) · [Test receipts](verification/wild-prefix/prefix-results.txt)")
    document = "\n\n".join(blocks) + "\n"
    introduction, *sections = re.split(r'(?m)(?=^## )', document)
    first = ['## Native edited test-build time with all eight changes',
             '## Edited test-build instructions with all eight changes',
             '## Retrained profile-guided builds',
             '## Edited uv instruction sums',
             '## Individual changes under profile-guided optimization']
    ranks = {title: i for i, title in enumerate(first)}
    sections.sort(key=lambda section: ranks.get(section.splitlines()[0], len(first)))
    return introduction + '\n\n'.join(section.rstrip() for section in sections) + '\n'


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=here, help="work directory or unpacked runs directory")
    parser.add_argument("--output", type=Path, default=here / "results-preview.md")
    args = parser.parse_args()
    args.output.write_text(render(args.runs))
