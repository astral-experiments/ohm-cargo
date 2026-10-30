#!/usr/bin/env python3
"""Check the original schedules, native controls, paired results, and confidence bounds."""
from hashlib import sha256
from itertools import combinations
from math import comb, isclose, log
from pathlib import Path
from statistics import median
import gzip
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CRATES = {"ruff_python_ast", "ruff_python_parser"}


def read(name):
    content = (ROOT / name).read_bytes()
    return json.loads(gzip.decompress(content) if name.endswith(".gz") else content)


def check_manifest():
    manifest = ROOT / "SHA256SUMS"
    covered = set()
    for line in manifest.read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert name not in covered and re.fullmatch(r"[0-9a-f]{64}", digest)
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        covered.add(name)
    files = {str(f.relative_to(ROOT)) for f in ROOT.rglob("*") if f.is_file() and f != manifest}
    assert files == covered


def median_interval(values, coverage):
    # For sorted iid paired ratios, choose the tightest order statistics with this coverage.
    n = len(values)
    cutoff = max(k for k in range(1, n // 2 + 1)
                 if 1 - 2 * sum(comb(n, j) for j in range(k)) / 2**n >= coverage)
    ordered = sorted(values)
    return [ordered[cutoff - 1], ordered[-cutoff]]


def scores(parent, candidate, order):
    ratios = [p / q for p, q in zip(parent, candidate, strict=True)]
    first_minus_second = [(log(p) - log(q)) * sign for p, q, sign in zip(parent, candidate, order, strict=True)]
    observed = abs(sum(sign * delta for sign, delta in zip(order, first_minus_second, strict=True)))
    n = len(parent)
    allowed = list(combinations(range(n), n // 2))
    extreme = sum(abs(sum((1 if i in chosen else -1) * d for i, d in enumerate(first_minus_second)))
                  >= observed - 1e-12 for chosen in allowed)
    above = sum(r > 2 for r in ratios)
    sign_p = min(1.0, 2 * sum(comb(n, j) for j in range(min(n-above, above) + 1)) / 2**n)
    return ratios, median_interval(ratios, .975), extreme / len(allowed), sign_p


def verify_workflow(name, declaration):
    schedule = read("registrations/" + name + ".json")
    assert sha256((ROOT / "registrations" / (name + ".json")).read_bytes()).hexdigest() == declaration["schedule_sha256"]
    slots = declaration["paired_slots"]
    assert slots == [s for s in schedule["slots"] if s["mode"] == slots[0]["mode"]]
    complete = declaration.get("completed_pairs")
    if complete is None:
        return
    file = read("measurements-" + name + ".json.gz")
    data = file["slots"]
    assert set(data) == {s["id"] for s in slots}
    pairs = [slots[i:i+2] for i in range(0, len(slots), 2)]
    order = [1 if first["arm"] == "P" else -1 for first, _ in pairs]
    assert len(pairs) == complete and sum(order) == 0
    ruff = read("sources.json")["ruff"]
    for first, second in pairs:
        assert first["id"][:-1] == second["id"][:-1] and {first["arm"], second["arm"]} == {"P", "Q"}
    for slot in slots:
        tag = slot["id"]
        assert f"{tag}/identity.json" in file["selected_streams"]
        for phase in ("return-A", "return-B"):
            row = data[tag][phase]
            assert set(row["dirty"]) == CRATES
            assert row["commit"] == ruff[phase[-1]]
            assert f"{tag}/{phase}/cargo.stdout" in file["selected_streams"]
            if name == "test-no-run":
                counted = data[tag]["counted-" + phase[-1]]
                assert row["tests"] == 245 and counted["wild"] == 1
                assert counted["rustc"] == {crate: 1 for crate in CRATES}
                assert counted["objects"] >= 0 and counted["ELF"] == row["ELF"]
            elif name == "check":
                assert row["expected_size"] == (64 if phase.endswith("A") else 56)
                assert set(row["metadata"]) == CRATES
            elif name == "build-compiler-instructions":
                assert sum(row["compiler_ir"].values()) == row["both_compilers_ir"]
                assert all(f"{tag}/{phase}/profile/{crate}/full-rustc.callgrind.gz" in file["selected_streams"]
                           for crate in CRATES)
    metric = "both_compilers_ir" if name == "build-compiler-instructions" else "wall_s"
    for phase in ("return-A", "return-B"):
        def arm_values(arm):
            return [data[next(s["id"] for s in pair if s["arm"] == arm)][phase][metric] for pair in pairs]
        parent, candidate = arm_values("P"), arm_values("Q")
        ratios, interval, p, p_two = scores(parent, candidate, order)
        recorded = file["statistics"][phase][metric]
        assert all(isclose(v, w) for v, w in zip(ratios, recorded["paired_ratios"], strict=True))
        assert all(isclose(v, w) for v, w in zip(interval, recorded["simultaneous_two_endpoints"]["range"], strict=True))
        assert isclose(p, recorded["balanced_randomization_p_no_effect"])
        assert isclose(p_two, recorded["paired_sign_p_above_two"])
        print(f"{name:28} {phase}: {median(ratios):.3f}x ({interval[0]:.3f}–{interval[1]:.3f}), "
              f"{complete} pairs, exact p={p:.5f}")


def main():
    check_manifest()
    source = read("sources.json")
    p, q = [source[k]["native_sdk"] for k in ("parent", "candidate")]
    assert len(p) == len(q) == 55 and p.keys() == q.keys()
    changed = [key for key in p if p[key] != q[key]]
    assert changed == ["lib/librustc_driver-15d35e5526bb94f8.so"]
    assert source["parent"]["cargo"] == source["candidate"]["cargo"]
    for name, reg in read("registrations.json").items():
        verify_workflow(name, reg)
    before_after = read("regression.json")["data"]
    assert before_after["U"]["actual_from_stale_binary"] == 17 and before_after["U"]["physical_input"] == 29
    assert before_after["P"]["exit"] == before_after["G"]["exit"] == 0
    assert len(read("units.json")["data"]["tested"]) == 4
    build = read("admission-build.json.gz")["slots"]
    test = read("admission-test-no-run.json.gz")["slots"]
    for phase in ("return-A", "return-B"):
        assert [build[f"N-admit-{arm}"][phase]["object_writes"] for arm in "PQ"] == [89, 0]
        assert [test[f"test-trace-{arm}"][phase]["objects"] for arm in "PQ"] == [90, 1]
        assert all(test[f"test-trace-{arm}"][phase]["wild"] == 1 for arm in "PQ")
    for mode in ["before-fix", "fixed"]:
        subprocess.run([sys.executable, "-IB", ROOT / "native-inputs" / mode / "verify.py"], check=True)
    subprocess.run([sys.executable, "-IB", ROOT / "concurrent-sessions" / "verify.py"], check=True)
    subprocess.run([sys.executable, "-IB", ROOT / "formatter-screen" / "verify.py"], check=True)
    if (ROOT / "formatter-confirmation").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "formatter-confirmation" / "verify.py"], check=True)
    subprocess.run([sys.executable, "-IB", ROOT / "moved-branch" / "verify.py"], check=True)
    if (ROOT / "block-device").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "block-device" / "verify.py"], check=True)
    if (ROOT / "formatter-reviewer-replay").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "formatter-reviewer-replay" / "verify.py"], check=True)
    if (ROOT / "storage" / "alternatives").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "storage" / "alternatives" / "verify.py"], check=True)
    compact = ROOT / "storage" / "alternatives" / "native-compact"
    if compact.is_dir():
        subprocess.run([sys.executable, "-IB", compact / "verify.py"], check=True)
        subprocess.run([sys.executable, "-IB", compact / "grammar-edits" / "verify.py"], check=True)
        full_cli = compact / "full-ruff-cli"
        if full_cli.is_dir():
            for name in ("verify.py", "verify-checkouts.py"):
                subprocess.run([sys.executable, "-IB", name, "observations.json"], cwd=full_cli, check=True)
    switched = ROOT / "storage" / "alternatives" / "switch-only"
    if switched.is_dir():
        subprocess.run([sys.executable, "-IB", switched / "verify.py"], check=True)
        subprocess.run([sys.executable, "-IB", switched / "grammar-edits" / "verify.py"], check=True)
        current_cli = switched / "full-ruff-cli" / "verify.py"
        if current_cli.is_file():
            subprocess.run([sys.executable, "-IB", current_cli], check=True)
        for verifier in (switched / "verify-verbs.py",
                         switched / "grammar-edits" / "replay" / "check-recording.py",
                         switched / "grammar-edits" / "instructions" / "verify.py"):
            if verifier.is_file():
                subprocess.run([sys.executable, "-IB", verifier], check=True)
        replay = switched / "grammar-edits" / "replay"
        qualification = replay / "qualification"
        if qualification.is_dir():
            subject = sha256((replay / "replay-same-branch.py").read_bytes()).hexdigest()
            assert json.loads((qualification / "registration.json").read_bytes())["reviewer_python"] == subject
            assert json.loads((qualification / "terminal.json").read_bytes())["public"] == subject
            subprocess.run([sys.executable, "-IB", qualification / "verify.py"], check=True)
        cli_plan = switched / "full-cli-timing" / "registration"
        if cli_plan.is_dir():
            for script in ("analyze.py", "test_plan.py"):
                subprocess.run([sys.executable, "-IB", script], cwd=cli_plan, check=True)
    if (ROOT / "check-test-instructions").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "check-test-instructions" / "verify.py"], check=True)
    if (ROOT / "opt-in" / "compiler.json").is_file():
        subprocess.run([sys.executable, "-IB", ROOT / "opt-in" / "verify.py"], check=True)
    if (ROOT / "storage" / "full-ruff-cli").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "storage" / "full-ruff-cli" / "verify.py"], check=True)
    if (ROOT / "full-cli-screen").is_dir():
        subprocess.run([sys.executable, "-IB", ROOT / "full-cli-screen" / "verify.py"], check=True)
    if (ROOT / "storage" / "alternatives" / "same-branch-edits").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "storage" / "alternatives" / "same-branch-edits" / "verify.py"], check=True)
    if (ROOT / "storage").exists():
        subprocess.run([sys.executable, "-IB", ROOT / "storage" / "verify.py"], check=True)
    if (ROOT / "portable-instruction-smoke.json").exists():
        measured = read("portable-instruction-smoke.json")["data"]
        guards = read("counter-reader-validation.json")
        assert sha256((ROOT / "compiler_counts.py").read_bytes()).hexdigest() == guards["reader_sha256"] == measured["published_reader_sha256"]
        assert guards["controls"]["original"] == {"accepted": True, "whole_rustcs": 2, "wild_links": 1}
        assert set(guards["controls"]) == {"original", "other-parent", "child-events", "extra-profile", "wrong-root-pid"}
        for phase in ("return-A", "return-B"):
            slots = measured["installations"]
            ratios = [slots[f"pair-{i:02}-P"][phase] / slots[f"pair-{i:02}-Q"][phase] for i in (1, 2)]
            assert ratios == measured["summary"][phase]["paired_ratios"]
    print("The SDK, source, schedules, native-input controls and available paired endpoints agree.")


if __name__ == "__main__":
    main()
