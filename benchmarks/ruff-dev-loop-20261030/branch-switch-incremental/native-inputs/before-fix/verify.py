#!/usr/bin/env python3
"""Recheck the projected branch-return traces and standalone Cargo replay."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

base = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
def digest(value):
    assert re.fullmatch(r"[a-f0-9]{64}", value)
def state(row):
    return row["rc"], row.get("value"), row.get("ELF")
def equal_refs(rows, name):
    chosen = rows[name]
    forced, empty = (rows[name + suffix] for suffix in ("-forced", "-empty"))
    assert chosen["assets"] == forced["assets"] == empty["assets"]
    assert chosen["source"] == forced["source"] == empty["source"]
    assert state(forced) == state(empty)
    assert forced["forced_input_custody"]
    return state(empty)
def file_seen(row, name, outcome):
    return any(result == outcome for _, result in row["asset_opens"][name])

for line in (base/"SHA256SUMS").read_text().splitlines():
    expected, name = line.split("  ", 1)
    assert "/" not in name and sha((base/name).read_bytes()) == expected
blob = (base/"projection.json.gz").read_bytes()
raw = gzip.decompress(blob)
for name in (b"/home/", b"/mnt/", b"openai.org", b"/run/user/"):
    assert name not in raw
data = json.loads(raw)
repaired = "guarded" in data["subject"]
treatment = "guarded" if repaired else "final"
assert set(data["subject"]) == {"parent", treatment}
assert data["subject"]["parent"]["source"] == "7e71d3150938ff8ed82aca03416439d7e5b87ef3"
assert data["subject"][treatment]["source"] == ("6b7f424ece4bc978ead5546b73e1b31d5ccb1e70" if repaired else "a6865b6a180a05e2609e80cc9862e5cabb926bde")
assert data["subject"]["parent"]["driver"] != data["subject"][treatment]["driver"]
for subject in data["subject"].values():
    assert subject["cargo"] == "1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add"
    assert subject["cargo_source"] == "2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c"
    assert subject["wild"] == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
for cargo_mode, size in (("default", 90), ("opt_out", 30)):
    arms = data["cohorts"][cargo_mode]
    all_rows = [case for modes in arms.values() for stages in modes.values() for case in stages.values()]
    assert len(all_rows) == size
    products = data["products"][cargo_mode]
    for key, product in products.items():
        digest(key); digest(product["archive"])
        assert key == product["sha256"] and product["bytes"] > 10000
    charged = set()
    for arm, modes in arms.items():
        assert set(modes) == ({"assembler", "tracked", "archive"} if cargo_mode == "default" else {"assembler"})
        stale = not repaired and cargo_mode == "opt_out" and arm == treatment
        for mode, rows in modes.items():
            assert Counter(row["ref"] for row in rows.values()) == {"warm":9, "empty":3, "forced":3}
            for case in rows.values():
                digest(case["raw_trace"])
                for stream in case["streams"].values():
                    for name in ("stdout","stderr","record"): digest(stream[name])
                assert len(case["complete_native_argv"]["cargo"]) == 1
                assert case["source"] == data["sources"][mode][case["branch"]]
                if case["rc"] == 0:
                    charged.add(case["ELF"])
                    assert products[case["ELF"]]["bytes"] == case["bytes"] and case["streams"]["program"]["rc"] == 0
                else: assert case["rc"] == 101 and case["diagnostic_tokens"]
            assert rows["01-A17"]["value"] == 17 and rows["02-B43"]["value"] == 43
            source_a, working_b = rows["02-B43"]["dep_graph_copies"][0]
            selected, working_a = rows["03-A-29"]["dep_graph_copies"][0]
            assert working_b.endswith("-working") and working_a.endswith("-working")
            keyed = arm == treatment and (not repaired or cargo_mode == "default")
            assert (selected == source_a if keyed else selected.startswith(working_b.removesuffix("-working") + "-"))
            assert working_a.split("-")[2].startswith("_") == keyed
            for phase in ("03-A-29","05-A-missing","08-A-invalid"):
                row = rows[phase]
                reference = equal_refs(rows, phase)
                assert reference[:2] == ((0,29) if phase == "03-A-29" else (101,None))
                assert len(row["complete_native_argv"]["roots"]) == 1
                if stale:
                    assert state(row) == state(rows["01-A17"]) and not any(row["asset_opens"].values())
                else:
                    assert state(row) == reference
                    if mode == "assembler":
                        if phase == "03-A-29": assert all(file_seen(row, name, "opened") for name in ("symbol.inc","payload.bin"))
                        if phase == "05-A-missing": assert file_seen(row, "payload.bin", "ENOENT")
                        if phase == "08-A-invalid": assert "ohm_bad_branch_directive" in row["diagnostic_tokens"]
            positive = rows["03-A-29"]
            assert rows["06-A-repair29"]["value"] == (17 if stale else 29)
            if cargo_mode == "default":
                assert positive["complete_native_argv"]["wild"]
                if mode == "assembler": assert any(entry["asm_marker"] and not entry["tracked_blob"] for entry in positive["dep_info"].values())
                if mode == "tracked": assert any(entry["tracked_blob"] for entry in positive["dep_info"].values())
                if mode == "archive": assert file_seen(positive,"libbranchfixture_native.a","opened")
            else:
                assert not positive["complete_native_argv"]["wild"]
                assert any(key.startswith("ld-") for key in positive["package_linker_chain"])
    assert charged == set(products)
    for mode in arms["parent"]:
        for key, row in arms["parent"][mode].items():
            if cargo_mode == "default" or repaired:
                assert state(row) == state(arms[treatment][mode][key])
mini = json.loads((base/"standalone.json").read_bytes())
assert mini["driver"] == data["subject"][treatment]["driver"]
assert mini["reproducer"] == sha((base/"reproduce.py").read_bytes())
assert len(mini["streams"]) == len(mini["result"]) == 10
for key, row in mini["result"].items():
    streams = mini["streams"][key]
    digest(streams["cargo_stdout"]); digest(streams["cargo_stderr"])
    if row["exit"] == 0: digest(row["ELF"]); digest(streams["native_stdout"])
    else: assert row["exit"] == 101 and streams["diagnostics"]
x = mini["result"]
assert x["03-return-A29"]["value"] == (29 if repaired else 17)
assert x["04-empty-A29"]["value"] == 29
if repaired: assert x["03-return-A29"]["ELF"] == x["04-empty-A29"]["ELF"]
for k in ("06-return-A-missing","09-return-A-malformed"):
    assert x[k]["exit"] == (101 if repaired else 0)
    if not repaired: assert x[k]["ELF"] == x["01-A17"]["ELF"]
assert x["07-empty-missing"]["exit"] == x["10-empty-malformed"]["exit"] == 101
print("Verified 120 traced Cargo builds, all recorded executable digests and 10 standalone Cargo builds.")
