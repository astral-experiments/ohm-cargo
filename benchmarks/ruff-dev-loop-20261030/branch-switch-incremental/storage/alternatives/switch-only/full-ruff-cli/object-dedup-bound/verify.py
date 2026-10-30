#!/usr/bin/env python3
"""Calculate object-sharing bounds from the published Ruff CLI allocation ledgers."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
LABELS = {"3372b4745d5226e8": "A", "a3a1413392b7d81d": "B"}
SESSION = re.compile(r"s-[a-z0-9]+-_(?P<label>[0-9a-f]{16})_[a-z0-9]+-[a-z0-9]+")


@dataclass(frozen=True)
class Object:
    size: int
    blocks: int
    mtime_ns: int
    names: tuple


def ledger(root, name, digest):
    data = (root / "classes" / (name + ".jsonl.gz")).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"input hash mismatch for {name}")

    objects = {}
    units = defaultdict(lambda: defaultdict(dict))
    for line in gzip.decompress(data).splitlines():
        row = json.loads(line)
        categories = {category for _, category in row["names"]}
        if "native-object" not in categories:
            continue
        assert categories == {"native-object"} and row["format"] == "elf-relocatable"
        dev, ino, mode, links, size, blocks, mtime, _ = row["signature"]
        ident = (dev, ino)
        names = tuple(path for path, _ in row["names"])
        assert ident == (row["device"], row["ino"]) and ident not in objects
        assert links == len(names) and size > 0 and blocks > 0 and mode & 0o170000 == 0o100000
        objects[ident] = Object(size, blocks, mtime, names)
        if not name.startswith("on-"):
            continue
        for path in names:
            parts = path.split("/")
            if "incremental" not in parts or not path.endswith(".o"):
                continue
            index = parts.index("incremental")
            assert len(parts) == index + 5
            unit = "/".join(parts[:index + 3])
            label = LABELS[SESSION.fullmatch(parts[-2])["label"]]
            files = units[unit][label]
            assert parts[-1] not in files
            files[parts[-1]] = ident
    return objects, units


def quantity(objects, ids):
    ids = set(ids)
    return {"inodes": len(ids), "allocated_bytes": sum(objects[i].blocks * 512 for i in ids)}


def same_file(first, last, key):
    unit, label, name = key
    before, after = first[1][unit][label][name], last[1][unit][label][name]
    if before != after:
        return False
    a, b = first[0][before], last[0][after]
    return (a.size, a.blocks, a.mtime_ns) == (b.size, b.blocks, b.mtime_ns)


def analyze(census):
    sources = json.loads((HERE / "inputs.json").read_text())
    inputs = {k: ledger(census, k, v) for k, v in sources["compressed_ledgers"].items()}
    objects, by_unit = final = inputs["on-storage--unchanged-B"]
    baseline = inputs["off-storage--unchanged-B"][0]
    native_keys = {"A": set(), "B": set()}
    alternate = set()
    shared = set()
    buckets = defaultdict(set)
    units = {}
    for unit, branches in sorted(by_unit.items()):
        if set(branches) != {"A", "B"}:
            assert set(branches) == {"A"}
            continue
        a, b = branches["A"], branches["B"]
        assert a.keys() == b.keys()
        b_sizes = {objects[i].size for i in b.values()}
        groups = defaultdict(set)
        for name, i in a.items():
            j = b[name]
            for label in ("A", "B"):
                native_keys[label].add((unit, label, name))
            if i == j:
                category = "one_physical_inode"
                shared.add(i)
            else:
                assert i not in alternate
                assert all("_3372b4745d5226e8_" in n for n in objects[i].names)
                alternate.add(i)
                category = ("different_inodes_equal_length" if objects[i].size == objects[j].size
                            else "different_inodes_unequal_length")
                if objects[i].size in b_sizes:
                    groups["has_a_length_match_anywhere_in_own_B_unit"].add(i)
            groups[category].add(i)
        for category, ids in groups.items():
            buckets[category].update(ids)
        units[unit.split("/")[-1]] = {k: quantity(objects, v) for k, v in sorted(groups.items())}

    # This wider bound also allows identical bodies in unrelated crates and CGUs.
    by_size = defaultdict(set)
    for i, obj in objects.items():
        by_size[obj.size].add(i)
    candidates = set()
    singletons = set()
    old_only_groups = []
    for size, ids in sorted(by_size.items()):
        old = ids & alternate
        if old != ids:
            candidates.update(old)
        elif len(old) == 1:
            singletons.update(old)
        elif old:
            # At least one representative has to survive. Keep the smallest physical
            # allocation to obtain an upper bound even if a sparse file is present.
            keep = min(old, key=lambda i: (objects[i].blocks, i))
            old_only_groups.append({"size": size, "members": len(old),
                                    "minimum_retained_bytes": objects[keep].blocks * 512})
            candidates.update(old - {keep})

    physical = quantity(objects, objects)
    off = quantity(baseline, baseline)
    extra = quantity(objects, alternate)
    assert extra == {k: physical[k] - off[k] for k in physical}
    continuity = {}
    for label, start, returned in (("A", "empty-A", "return-A"), ("B", "first-B", "return-B")):
        first = inputs["on-storage--" + start]
        again = inputs["on-storage--" + returned]
        keys = native_keys[label]
        assert all(same_file(first, again, k) and same_file(again, final, k) for k in keys)
        ids = {by_unit[u][s][n] for u, s, n in keys}
        continuity[label] = {"all": quantity(objects, ids),
                             "distinct_from_other_branch": quantity(objects, ids - shared)}

    return {"native_objects_off": off, "native_objects_on": physical,
            "additional_alternate_objects": extra, "two_checkout_units": len(units),
            "same_unit_cgu": {k: quantity(objects, v) for k, v in sorted(buckets.items())},
            "any_named_native_object": {
                "singletons_by_file_length": quantity(objects, singletons),
                "length_groups_entirely_in_alternate_with_multiple_members": old_only_groups,
                "whole_file_reclamation_upper_bound": quantity(objects, candidates)},
            "preserved_inode_size_blocks_mtime_ns_through_own_return": continuity,
            "by_unit": units,
            "separate_inode_payload_hashes_in_these_ledgers": 0,
            "reclaimable_bytes_proven_by_full_payload_equality": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", type=Path, help="published census directory containing classes/")
    parser.add_argument("--check", action="store_true", help="also compare the complete result to results.json")
    args = parser.parse_args()
    result = analyze(args.census)
    if args.check and result != json.loads((HERE / "results.json").read_text()):
        raise SystemExit("computed result differs from results.json")
    print(json.dumps(result, indent=2, sort_keys=True))
