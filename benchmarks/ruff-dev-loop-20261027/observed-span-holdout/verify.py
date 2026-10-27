"""Verify all public records, the declared population, native outputs, traced work, and paired statistics."""

from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import sys

BASE = Path(__file__).resolve().parent
NAMES = ("hold_direct", "hold_indirect", "hold_plain")


def read(name):
    return json.loads((BASE / name).read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(name):
    with (BASE / name).open(newline="") as f:
        return list(csv.DictReader(f))


def require(value, message):
    if not value:
        raise ValueError(message)


def verify():
    plan, subject = read("cooperating-plan.json"), read("subjects.json")
    require(
        sha(BASE / "cooperating-plan.json")
        == subject["plan"]
        == "f169b2d0ffcdf3caf531ab2bd1fe39409f65cefe379544f13e3d61f68aad1b06",
        "unregistered schedule",
    )
    require(
        sha(BASE / "native.csv") == "714dae13556c1b3594379971201f0f059ba7e6377c8ccc92966bfd3d8bce0026",
        "native CSV hash",
    )
    require(
        sha(BASE / "cargo-observer-pr253-v3.patch") == subject["candidate_patch_sha256"],
        "reviewed patch hash",
    )
    require(set(subject["sha256"]) == {"P", "C", "rustc", "driver"}, "frozen subjects")
    fix = read("heldout-fixture-sha256.json")
    require(
        sha(BASE / "heldout-fixture-sha256.json")
        == subject["source_manifest"]
        == "1a309c176ba8ea129414be486ce87a040c171d294e9d12a5388bdaaa94d6f78e",
        "fixture manifest",
    )
    root = BASE / "heldout-fixture"
    require(
        {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()} == fix, "fixture content"
    )
    original = (root / "hold_shapes/src/types.rs").read_bytes()
    needle = b"/// One private shape\n"
    require(original.count(needle) == 1, "historical fixture edit")
    edited = original.replace(needle, b"/// One private shapes\n")
    hs = [hashlib.sha256(x).hexdigest() for x in (original, edited)]
    raw = [json.loads(x) for x in (BASE / "command-records.jsonl").read_bytes().splitlines()]
    record = {x["phase"]: x for x in raw}
    require(
        len(raw) == len(record) == 114 and all(x["success"] for x in raw), "complete successful command set"
    )
    exe = rows("successful-execs.csv")
    byphase = defaultdict(list)
    for call in exe:
        byphase[call["phase"]].append(call)
    traced = [x["phase"] for x in raw if not x["native_timing"]]
    quality = read("trace-quality.json")
    require(
        len(exe) == quality["completed_execve_events"] == 798
        and len(traced) == quality["traced_invocations"] == 66
        and set(traced) == byphase.keys(),
        "complete trace set",
    )
    require(
        all(
            v == 1 and p in byphase
            for p, v in quality["unknown_unfinished_without_syscall_name_or_result"].items()
        ),
        "unrecognized incomplete record disclosure",
    )
    for phase, calls in byphase.items():
        require([int(c["ordinal"]) for c in calls] == list(range(1, len(calls) + 1)), phase)
        require(
            all(
                c["image"] in ("rustup-cargo-proxy", "cargo", "cc", "collect2", "ld.bfd", "rustc")
                for c in calls
            ),
            phase,
        )
        require(
            [(c["image"], c["local_process"]) for c in calls[:2]]
            == [("rustup-cargo-proxy", "1"), ("cargo", "1")],
            phase,
        )
    empty = {flag: record["empty-" + str(flag)] for flag in (0, 1)}
    for flag, g in empty.items():
        require(g["source_sha256"] == hs[flag] and set(g["products"]) == set(NAMES), "empty-target reference")
    for n in NAMES:
        a, b = [empty[x]["products"][n] for x in (0, 1)]
        require((a == b) == (n == "hold_plain"), ("reference ELF or printed value", n))
        require((a["output"] == b["output"]) == (n == "hold_plain"), ("value shift", n))
    for name in ("training", "audit-training"):
        for arm in "PC":
            for i in range(4):
                rec = record[f"{name}-{arm}-{i}"]
                require(
                    not rec["native_timing"]
                    and rec["source_sha256"] == hs[0]
                    and rec["products"] == empty[0]["products"],
                    ("training reference", name, arm, i),
                )
            last = byphase[f"{name}-{arm}-3"]
            require(
                {c["crate"] for c in last if c["rustc_mode"] == "full"}
                == ({"hold_direct", "hold_bridge"} if arm == "P" else set()),
                ("training completion", name, arm),
            )
    native = rows("native.csv")
    require(len(native) == 48, "unexpected number of scored commands")
    expected_native = []
    ratios = {p: [] for p in ("noop", "edit")}
    marginal = {p: {a: [] for a in "PC"} for p in ratios}
    readers = {"hold_direct", "hold_bridge"}
    for i, block in enumerate(plan["orders"], 1):
        require(block["block"] == i and block["edit"] == ("add" if i % 2 else "remove"), block)
        for phase, order in [("noop", block["no_op"]), ("edit", block["edit_order"])]:
            direction = int((block["edit"] == "add") == (phase == "edit"))
            times = {}
            for arm in order:
                scored = f"native-{i:02}-{phase}-{arm}"
                audit = f"audit-{i:02}-{phase}-{arm}"
                n = record[scored]
                t = record[audit]
                gold = empty[direction]["products"]
                rawcsv = native[len(expected_native)]
                expected_native.append(scored)
                require(
                    [rawcsv[k] for k in ("block", "phase", "order", "arm")] == [str(i), phase, order, arm]
                    and int(rawcsv["nanoseconds"]) == n["ns"] > 0,
                    scored,
                )
                require(
                    n["native_timing"]
                    and not t["native_timing"]
                    and n["arm"] == t["arm"] == arm
                    and n["source_sha256"] == t["source_sha256"] == hs[direction] == rawcsv["source_sha256"],
                    scored,
                )
                require(
                    n["products"] == t["products"] == gold
                    and set(n["readers"]) == set(t["readers"]) == readers,
                    scored,
                )
                for name in NAMES:
                    prefix = name.removeprefix("hold_")
                    require(
                        rawcsv[prefix + "_value"] == gold[name]["output"]
                        and rawcsv[prefix + "_elf_sha256"] == gold[name]["sha256"],
                        (scored, name),
                    )
                for row in (n, t):
                    for reader in row["readers"].values():
                        require(
                            reader["complete"] is (True if arm == "C" else None)
                            and reader["record_bytes"] > 0,
                            scored,
                        )
                        if arm == "C":
                            require(
                                reader["marker_index"] >= 0
                                and re.fullmatch("[a-f0-9]{64}", reader["stored_blake3"]),
                                scored,
                            )
                calls = byphase[audit]
                compiles = [(c["crate"], c["rustc_mode"]) for c in calls if c["rustc_mode"]]
                full = (
                    readers | {"hold_shapes", "hold_indirect"}
                    if phase == "edit"
                    else (readers if arm == "P" else set())
                )
                relink = {"hold_plain"} if phase == "edit" else ({"hold_indirect"} if arm == "P" else set())
                require(
                    Counter(compiles)
                    == Counter([(n, "full") for n in full] + [(n, "relink") for n in relink]),
                    audit,
                )
                captures = [c["crate"] for c in calls if c["binary_depinfo"] == "True"]
                require(
                    Counter(captures) == Counter(readers if phase == "edit" and arm == "C" else []), audit
                )
                require(
                    sum(c["image"] == "ld.bfd" for c in calls)
                    == (3 if phase == "edit" else 2 if arm == "P" else 0),
                    ("final ELF links", audit),
                )
                times[arm] = n["ns"]
                marginal[phase][arm].append(n["ns"] / 1e6)
            ratios[phase].append(math.log(times["P"] / times["C"]))
    require(set(expected_native) == {n for n in record if n.startswith("native-")}, "timed command set")
    stats = {}
    for phase, r in ratios.items():
        percentages = sorted(-100 * math.expm1(-l) for l in r)
        stats[phase] = dict(
            control_median_ms=statistics.median(marginal[phase]["P"]),
            candidate_median_ms=statistics.median(marginal[phase]["C"]),
            paired_median_reduction_pct=statistics.median(percentages),
            candidate_faster_pairs=sum(x > 0 for x in r),
            pairs=12,
        )
    r = ratios["noop"]
    orders = [b["no_op"] for b in plan["orders"]]
    require(Counter(orders) == {"PC": 6, "CP": 6}, "balanced prior schedule")
    slot = [x if o == "PC" else -x for o, x in zip(orders, r)]
    extreme = sum(
        sum(d if i in sel else -d for i, d in enumerate(slot)) >= sum(r) - 1e-12
        for sel in itertools.combinations(range(12), 6)
    )
    q = sorted(-100 * math.expm1(-x) for x in r)
    stats["noop"].update(
        paired_median_interval_pct=[q[2], q[9]], balanced_assignments=924, one_sided_p=extreme / 924
    )
    lib = rows("library-reads.csv")
    sums = Counter()
    for x in lib:
        require(
            re.fullmatch(r"lib[a-zA-Z0-9_-]+\.(rlib|rmeta|so)", x["library_basename"])
            and x["input_class"] in ("sdk", "other"),
            x,
        )
        sums[(x["phase"], x["process"], x["input_class"])] += int(x["bytes"])
    aggregate = {
        (x["phase"], x["process"], x["input_class"]): int(x["bytes"]) for x in rows("process-reads.csv")
    }
    require(dict(sums) == aggregate, "per-file read-byte aggregation")
    require(aggregate["steady-C", "cargo", "sdk"] == 98902551, "steady SDK read bytes")
    for direction in ("first-edit-C", "back-edit-C"):
        require(
            [aggregate[direction, p, "sdk"] for p in ("cargo", "rustc:hold_bridge", "rustc:hold_direct")]
            == [187964474, 88319067, 98902551],
            "edited SDK read bytes",
        )
    repeated = {
        (x["phase"], x["process"], x["input_class"]): int(x["bytes"])
        for x in rows("streaming-replication-reads.csv")
    }
    require(set(repeated) == set(aggregate), "streaming replication phase set")
    require(
        repeated["steady-C", "cargo", "sdk"] == aggregate["steady-C", "cargo", "sdk"],
        "renewed no-op SDK reads",
    )
    for direction in ("first-edit-C", "back-edit-C"):
        require(
            [repeated[direction, p, "sdk"] for p in ("cargo", "rustc:hold_bridge", "rustc:hold_direct")]
            == [140324731, 88319067, 98902551],
            "separate streaming replication",
        )
    require(read("statistics.json") == stats, "published statistics differ from raw observations")
    mf = BASE / "SHA256SUMS"
    if mf.exists():
        manifest = {path: h for h, path in (l.split("  ", 1) for l in mf.read_text().splitlines())}
        found = {str(p.relative_to(BASE)): sha(p) for p in BASE.rglob("*") if p.is_file() and p != mf}
        require(found == manifest, "manifest file set or checksum mismatch")
    return stats


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
