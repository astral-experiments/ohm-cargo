"""Independently verify all recorded Cargo outcomes, native process counts and ELF bindings."""
import argparse
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--elf-pair", nargs=2, type=Path, metavar=("OLD", "NEW"))
parser.add_argument("--raw", type=Path, help="Optionally rehash every retained command stream and source trace")
args = parser.parse_args()
old = "a2edd1b5d8b970835126f19c467eb5bca07835874bfc7b0b2d14ba6fca820fa4"
new = "749cde35ef1f4fb78954d7110ee4ee9a8271159aec9f9f67390fcb1e5419b3b6"
rustc = "fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
wild = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
version = "9a788145e8e7172a1e397cde2a77250adba7d0e3c7644bdde3ac7a7877259367"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()

def read(name):
    data = (root / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

manifest = {}
for line in (root / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ")
    assert name == Path(name).name and name not in manifest
    assert sha((root / name).read_bytes()) == digest
    manifest[name] = digest
assert set(manifest) == {p.name for p in root.iterdir() if p.is_file()} - {"SHA256SUMS"}
assert manifest["cargo-version.txt"] == version
subjects = read("subjects.json")
assert subjects["candidate"] == new and subjects["initial_stamp_sha256"] == version
assert subjects["source"]["base"] == "2447f7f4eacb4fdf499899929f08d0de19abb4d0"
assert subjects["source"]["patch_sha256"] == "a8ece61b242750e04a662f6527d61f54917a70d72e1192d9967c10f44f0867a5"
assert subjects["sdk"]["rust_commit"] == "ca780121cea38bb9b0538d020d4bcce76ca30cbc"
assert subjects["sdk"]["target_files"] == 53
assert manifest["cargo-source.json"] == subjects["source_receipt"]
assert read("cargo-source.json") == subjects["source"]

def fresh(report):
    assert report["status"] == 0 and not report["processes"] and not report["asset_opens"]
    assert report["typed"] and all(t[-1] for t in report["typed"])

def assembled(report, missing=False):
    assert report["status"] == (101 if missing else 0)
    assert any(p.get("unit") == "reader" and not p["link_only"] for p in report["processes"])
    assert any(e["nearest_compiler"] == "reader" and e["missing" if missing else "open_successful"] for e in report["asset_opens"])
    if missing:
        assert report["incbin_diagnostic"] and report["asset"] is None and "elf" not in report
        assert report["missing_diagnostic"]["message_template"] == "Could not find incbin file '<workspace>/payload.bin'"
    else:
        assert [p["exe"] for p in report["processes"] if p["type"] == "linker"] == [wild]

cases = read("eight-upgrades.json.gz")
expected = {"-".join(c) for c in itertools.product(("bin", "test"), ("missing", "valid"), ("default", "explicit-no"))}
assert set(cases) == expected
assert subjects["previous"]["cases"] == {k: 0 for k in expected} | {"broad-native-roster": 1}
primary = 0
for case_name, case in cases.items():
    target, poison, flag = case_name.split("-", 2)
    t = case["terminal"]
    assert t["all_passed"] and t["old"] == old and t["new"] == new and t["same_full_version"] == version
    assert (t["inputs"]["kind"], t["inputs"]["poison"], t["inputs"]["new_flag"]) == (target, poison, flag)
    assert (t["inputs"]["runtime"], t["inputs"]["wild"]) == (rustc, wild)
    assert t["inputs"]["study"] == manifest["migration.py"] and sha(canonical(t)) == case["new_receipt"]
    s = case["swap"]
    assert s["old_version"] == s["new_version"] == version and s["old"]["sha"] == old and s["new"]["sha"] == new
    assert s["old"]["inode"] != s["new"]["inode"]
    assert s["lineage_before"] == s["lineage_after"]
    assert {"workspace/Cargo.toml","workspace/Cargo.lock","workspace/src/lib.rs","environment.json","sdk/bin/rustc"} <= s["lineage_before"].keys()
    v = case["visits"]
    assert set(v) == set(t["raw"]) and len(v) == (19 if poison == "missing" else 17)
    primary += len(v)
    if args.raw:
        home = args.raw / "dev-stamp-v2" / case_name
        assert sha((home/"trained.json").read_bytes()) == case["old_receipt"]
        assert sha((home/"terminal.json").read_bytes()) == case["new_receipt"]
        assert json.loads((home/"swap.json").read_bytes()) == s
    for name, r in v.items():
        assert name == r["label"] and r["argv"][:2] == ["cargo", "+ohm"]
        number = int(name[:2])
        assert ("-Zrelink-only=no" in r["argv"]) == (number >= 10 and flag == "explicit-no")
        assert r["cargo"] == (old if number < 9 else new) and r["rustc"] == rustc
        for p in r["processes"]:
            assert (p["type"], p["exe"]) in (("rustc", rustc), ("linker", wild))
            assert not p.get("incremental", False)
        assert {"stdout","stderr"} <= r["raw"].keys() and any(k.startswith("trace.") for k in r["raw"])
        if "program_stdout" in r:
            assert sha(r["program_stdout"].encode()) == r["raw"]["program.stdout"]
            assert re.search(rf'native-value={r["native"]},rust-value={r["rust"]}(?:\D|$)', r["program_stdout"])
            if target == "test": assert "1 passed" in r["program_stdout"]
        literal = {k: value for k, value in r.items() if k not in ("program_stdout", "missing_diagnostic")}
        assert sha(canonical(literal)) == t["raw"][name]
        if args.raw:
            ev = home / "visits" / name
            assert sha((ev/"result.json").read_bytes()) == t["raw"][name]
            for fname, digest in r["raw"].items():
                assert fname == Path(fname).name and sha((ev/fname).read_bytes()) == digest
    for label in ("02-original-repeat", "06-settled-check", "06-settled-lib", "07-wrong-fresh-repeat",
                  "08-identical-Cargo-replacement", "09-upgrade-unaffected-check", "09-upgrade-unaffected-lib",
                  "13-new-settled", "15-subsequent-noop"):
        fresh(v[label])
    orig, red, first, clean = (v[k] for k in ("01-original", "03-actual-edit-poison", "10-first-unchanged-upgrade", "04-independent-clean"))
    assert orig["native"] == red["native"] == 17 and orig["library_source"] != red["library_source"]
    assert not red["asset_opens"] and any(p.get("unit") == "reader" and p["link_only"] for p in red["processes"])
    assert [p["exe"] for p in red["processes"] if p["type"] == "linker"] == [wild]
    if target == "bin": assert (orig["rust"], red["rust"]) == (6, 10)
    for label in ("07-wrong-fresh-repeat", "08-identical-Cargo-replacement"):
        assert (v[label]["native"], v[label]["elf"]) == (17, red["elf"])
    assert red["elf"] == case["old_elf"] and clean.get("elf") == case["empty_initial_elf"]
    assert [p["unit"] for p in first["processes"] if p["type"] == "rustc"] == ["reader"]
    for key in ("consumer_source","library_source","source_inputs","asset"):
        assert red[key] == first[key] == clean[key] == v["08-identical-Cargo-replacement"][key]
    for r in (first, clean): assembled(r, poison == "missing")
    if poison == "missing":
        assembled(v["11-unchanged-missing"], True)
        assembled(v["12-provide-missing"])
        assert v["12-provide-missing"]["native"] == 29
    else:
        assert first["elf"] == clean["elf"] and first["native"] == clean["native"] == 29
    assert v["13-new-settled"]["native"] == 29
    final, empty = v["14-normal-source-edit"], v["16-empty-new-source"]
    for r in (final, empty): assembled(r)
    assert final["library_source"] == orig["library_source"] and final["asset"] != orig["asset"]
    assert final["elf"] == empty["elf"] == v["15-subsequent-noop"]["elf"]
    assert final["native"] == empty["native"] == v["15-subsequent-noop"]["native"] == 41

scope = read("all-targets.json.gz")
reports, binding = scope["reports"], scope["binding"]
assert len(reports) == 12 and binding["initial_strict_status"] == 1 and binding["next_native_noop"]
for name, r in reports.items():
    assert r["rc"] == 0 and not r["cached"] and sha(canonical(r)) == binding["reports"][name]
    if args.raw:
        ev = args.raw / "coverage-v1" / name
        assert sha((ev/"result.json").read_bytes()) == binding["reports"][name]
        for fname, digest in r["raw"].items():
            assert fname == Path(fname).name and sha((ev/fname).read_bytes()) == digest
    if name.endswith("-2") or (name.startswith("candidate-") and "-native-" not in name):
        assert all(t[3] for t in r["units"]) and not r["full"] and not r["stock_links"]
old_roster, new_roster = reports["parent-native-2"], reports["candidate-native-1"]
assert len(old_roster["old_linkable"]) == len(new_roster["full"]) == 11
assert sorted(new_roster["stock_links"]) == sorted(k.removesuffix(".rlink-cache.json") for k in old_roster["old_linkable"])
def keyed(r):
    return {(name, tuple(kind), test): [fresh_, digest] for name, kind, test, fresh_, digest in r["units"]}
a, b, repeat = map(keyed, (old_roster, new_roster, reports["candidate-native-2"]))
assert len(a) == 12 and set(a) == set(b) == set(repeat)
assert sum(not value[0] for value in b.values()) == 11 and all(repeat[k] == [True, b[k][1]] for k in a)
difference = [(k, a[k][1], b[k][1]) for k in a if a[k][1] != b[k][1]]
assert len(difference) == 1 and difference[0][0] == ("only_bin_ex", ("example",), True)
assert binding["strict_mismatches"] == [[["only_bin_ex", ["example"], True], *difference[0][1:]]]
w = read("example-width-replay.json")
assert w["previous_elf_sha"] == difference[0][1] and w["incoming_elf_sha"] == difference[0][2]
assert w["training_status"] == 1 and w["full_argv_identical"] and w["only_known_bytes"]
assert set(w["reconstructed"]) == set(difference[0][1:]) and set(w["rows"]) == {"1","2","3","4"}
for width, row in w["rows"].items():
    assert row["exit"] == 0 and row["elf"] == difference[0][2 if width == "1" else 1]
    link, = row["stock_links"]
    assert link["sha"] == wild and link["width_flags"] == ["--threads=" + width]
    assert row["runtime"] == w["rows"]["1"]["runtime"] and all(s["rc"] == 0 for s in row["runtime"].values())
assert w["size"] == 1073672 and w["fields"]["rodata_entsize"]["old"] == "0100000000000000"
assert w["fields"]["rodata_entsize"]["new"] == "0000000000000000" and w["fields"]["build_id"]["bytes"] == 32
ordered = sorted(w["fields"].values(), key=lambda r:r["offset"])
ranges = w["unchanged_ranges"]
assert len(ranges) == 3 and ranges[0]["start"] == 0 and ranges[-1]["end"] == w["size"]
for i, field in enumerate(ordered):
    assert ranges[i]["end"] == field["offset"] and ranges[i+1]["start"] == field["offset"] + field["bytes"]
if args.elf_pair:
    bodies = [p.read_bytes() for p in args.elf_pair]
    assert [sha(x) for x in bodies] == [w["previous_elf_sha"], w["incoming_elf_sha"]]
    assert all(len(x) == w["size"] for x in bodies)
    for p in ranges:
        parts = [x[p["start"]:p["end"]] for x in bodies]
        assert parts[0] == parts[1] and sha(parts[0]) == p["equal_sha256"]
    for f in ordered:
        assert [x[f["offset"]:f["offset"] + f["bytes"]].hex() for x in bodies] == [f["old"], f["new"]]
print(f"{len(cases)} same-version upgrades, {primary} Cargo commands, 12 workspace commands, 11 one-time full links, 4 stock width replays; all receipt checks passed.")
