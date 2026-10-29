"""Reconstruct the portable Milan packet from the frozen private terminal tar."""
import argparse
import collections
import gzip
import hashlib
import json
import math
import re
import tarfile
from pathlib import Path, PurePosixPath

ARCHIVE = "3cc9112b7b9081e69ca753f676faa48dac7e0b5a8a02f05bcc5070dc9fee7514"
PLAN = "5ef08a85860887a0eb92c12bf51174a6264ab806989f807e2fb9c2f78bfb274e"
CARGOS = {"A": "3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7",
          "B": "51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9"}
REVISIONS = {"parent": "716260bf10d7ae1d965ed9b22653e57fbc960582",
             "child": "2d6ce561250a464e1fa231ef30e54d0f029f76a4"}
PROBES = ("ruff_python_ast", "ruff_python_index")
PHASES = ("preflight", "edit", "repeat", "after")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def encode(name, value):
    plain = (compact(value) + "\n").encode()
    return gzip.compress(plain, compresslevel=9, mtime=0) if name.endswith(".gz") else plain


def path_safe(name):
    p = PurePosixPath(name)
    return bool(name) and name == str(p) and not p.is_absolute() and ".." not in p.parts


def portable_fields(fields):
    ident = fields[0]
    if ident.startswith("path+file:///"):
        assert ident.count("/crates/") == 1
        ident = "workspace:crates/" + ident.split("/crates/")[1]
    else:
        assert ident.startswith(("registry+https://github.com/rust-lang/crates.io-index#",
                                 "git+https://github.com/astral-sh/lsp-types.git?",
                                 "git+https://github.com/salsa-rs/salsa.git?"))
    return [ident, *fields[1:]]


def collect(archive):
    assert sha(archive.read_bytes()) == ARCHIVE
    members, data, hashes, mtimes = [], {}, {}, {}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            name = member.name
            assert path_safe(name) and name not in mtimes and (member.isfile() or member.isdir())
            mtimes[name] = member.mtime
            row = [name, "dir" if member.isdir() else "file", member.size, member.mtime]
            if member.isfile():
                b = tar.extractfile(member).read()
                assert len(b) == member.size
                data[name] = b
                hashes[name] = sha(b)
                row.append(hashes[name])
            members.append(row)
    assert len(members) == 1234 and len(data) == 880
    js = lambda k: json.loads(data[k])
    roster = js("protocol/milan.json")
    gate = js("allow-clock.json")
    assert gate["images"] == CARGOS and gate["protocol"] == hashes["protocol/SHA256SUMS"] == PLAN
    for line in data["protocol/SHA256SUMS"].decode().splitlines():
        h, f = line.split()
        assert hashes["protocol/" + f] == h
    assert hashes["qualification/complete.json"] == gate["qualification"]
    assert hashes["physical-common/complete.json"] == gate["common"]
    physical = js("physical-common/complete.json")
    qualification = js("qualification/complete.json")
    bases = {}
    for arm in CARGOS:
        bases[arm] = {}
        for source in REVISIONS:
            d = js(f"accepted-common-{arm}/{source}.json")
            assert d["arm"] == arm and d["cargo"] == CARGOS[arm] and d["revision"] == REVISIONS[source]
            assert d["products597"] == physical["cross_arm_597"][arm + "-" + source]
            assert d["sha256"] == d["trained_on_identical_source_archive"] and d["bytes"] > 0
            assert d["archive"].endswith(f"/A-{source}.tar.zst") and len(d["source_times"]) == 30
            d["archive"] = f"common-A-{source}"
            bases[arm][source] = d
    for source in REVISIONS:
        a, b = [bases[arm][source] for arm in CARGOS]
        assert {k:v for k,v in a.items() if k not in ("arm","cargo")} == {k:v for k,v in b.items() if k not in ("arm","cargo")}
    for arm in CARGOS:
        for direction in ("child-to-parent","parent-to-child"):
            counts = [r["roles"]["rustc-full"] for r in qualification[arm][direction]]
            assert counts == gate["native"][f"{arm}:{direction}"]
    assert all(path_safe(x) for x in physical["within_A_changed"]) and len(physical["within_A_changed"]) == 41
    catalog = []
    index = {}
    line_catalog = []
    lines_by_hash = {}
    inventories = {}
    commands, visits, pairs = [], [], []
    previous_visit = 0
    for plan in roster:
        i, direction, order = [plan[k] for k in ("pair", "direction", "order")]
        before, after = direction.split("-to-")
        prefix = f"scored/pair-{i:02}"
        pair = js(prefix + "/pair.json")
        assert {k:pair[k] for k in plan} == plan and set(pair) == set(plan) | {"A","B"}
        for arm in order:
            sub = f"{prefix}/{arm}"
            visit = js(sub + "/visit.json")
            assert (visit["arm"], visit["cargo"], visit["order"]) == (arm, CARGOS[arm], direction)
            assert [visit["source_before"],visit["source_after"]] == [REVISIONS[before], REVISIONS[after]]
            assert visit["timing_ns"] == pair[arm] and min(pair[arm]) > 0 and visit["between_ns"] >= 0
            vm = mtimes[sub + "/visit.json"]
            assert previous_visit < vm
            previous_visit = vm
            visits.append({"pair":i, **visit})
            for phase in PHASES:
                folder = sub + "/" + phase
                donor = bases[arm][before if phase == "preflight" else after]
                rec = js(folder + "/receipt.json")
                assert rec["source"] == donor["revision"]
                assert rec["json"] == hashes[folder + "/cargo.jsonl"] and rec["stderr"] == hashes[folder + "/stderr"]
                receipt_commitment = hashes[folder + "/receipt.json"]
                b = data[folder + "/cargo.jsonl"]
                assert b.endswith(b"\n")
                graph, raw_typed, portable_typed, line_ids, picks, reasons, levels = [], [], [], [], {}, collections.Counter(), collections.Counter()
                for line in b.splitlines():
                    r = json.loads(line)
                    reason = r["reason"]
                    assert reason in ("compiler-artifact","compiler-message","build-script-executed","build-finished")
                    reasons[reason] += 1
                    line_hash = sha(line)
                    if line_hash not in lines_by_hash:
                        lines_by_hash[line_hash] = len(line_catalog)
                        line_catalog.append([line_hash,reason])
                    line_index = lines_by_hash[line_hash]
                    line_ids.append(line_index)
                    if reason == "compiler-message":
                        levels[r["message"]["level"]] += 1
                        if len(line_catalog[line_index]) == 2:
                            line_catalog[line_index].append(r["message"]["level"])
                        assert line_catalog[line_index][2] == r["message"]["level"]
                    if reason != "compiler-artifact":
                        continue
                    t = r["target"]
                    fields = [r["package_id"],t["name"],t["kind"],t["crate_types"],t["test"],t["doctest"],r["features"],r["profile"]]
                    orig, portable = compact(fields), portable_fields(fields)
                    norm = compact(portable)
                    raw_typed.append(orig)
                    portable_typed.append(norm)
                    if norm not in index:
                        index[norm]=len(catalog)
                        catalog.append({"unit":portable,"raw_typed_sha256":sha(orig.encode())})
                    j = index[norm]
                    assert catalog[j]["raw_typed_sha256"] == sha(orig.encode())
                    assert type(r["fresh"]) is bool
                    graph.append(j + 1 if r["fresh"] else -(j + 1))
                    if len(line_catalog[line_index]) == 2:
                        line_catalog[line_index].append(graph[-1])
                    assert line_catalog[line_index][2] == graph[-1]
                    if t["name"] in PROBES:
                        picks[t["name"]] = r
                assert r == {"reason":"build-finished","success":True} and reasons["build-finished"] == 1
                assert "error" not in levels and len(graph) == reasons["compiler-artifact"] == 510
                raw_inventory = sha("\n".join(sorted(raw_typed)).encode())
                portable_inventory = sha("\n".join(sorted(portable_typed)).encode())
                assert rec["inventory"] == raw_inventory == donor["identity"] and rec["dirty"] == sum(u<0 for u in graph)
                if raw_inventory not in inventories:
                    inventories[raw_inventory] = {"portable":portable_inventory,"nodes":sorted(map(abs,graph))}
                assert inventories[raw_inventory] == {"portable":portable_inventory,"nodes":sorted(map(abs,graph))}
                if phase in ("edit","repeat"):
                    assert rec["units"] == 510 and rec["wall_ns"] == pair[arm][phase == "repeat"]
                else:
                    assert rec["rc"] == 0 and rec["typed"] == 510 and rec["dirty"] == 12
                    assert rec["fresh"] == {n:picks[n]["fresh"] for n in PROBES} and all(rec["fresh"].values())
                    assert all(len(picks[n]["filenames"])==1 and picks[n]["filenames"][0].endswith(".rmeta") for n in PROBES)
                    assert rec["images"] == donor["images"]
                commands.append({"pair":i,"arm":arm,"phase":phase,"receipt":rec,"receipt_sha":receipt_commitment,
                                 "artifact_order":graph,"json_line_order":line_ids,"message_types":dict(reasons),"diagnostics":dict(levels)})
        pairs.append(pair)
    assert pairs == js("scored/observations.json")
    assert len(inventories)==2 and len(commands)==256 and len(visits)==64
    for x in physical["within_A_changed"]:
        assert not x.startswith("/") and "://" not in x
    return {
        "archive-members.json.gz":members,
        "bindings.json":{"archive":ARCHIVE,"archive_bytes":archive.stat().st_size,"protocol":PLAN,"grant":gate,
                         "physical":physical,"donors":bases,"qualification":qualification},
        "typed-units.json.gz":{"catalog":catalog,"inventories":inventories,"cargo_lines":line_catalog},
        "commands.json.gz":commands, "observations.json":pairs, "visits.json.gz":visits,
        "original-analysis.json":js("scored/analysis.json"),
    }, {k[9:]:v for k,v in data.items() if k.startswith("protocol/")}


if __name__ == "__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("archive",type=Path)
    cli.add_argument("destination",type=Path)
    cli.add_argument("--compare",action="store_true")
    args=cli.parse_args()
    ledger,protocol=collect(args.archive)
    files={k:encode(k,v) for k,v in ledger.items()} | {"protocol/"+k:v for k,v in protocol.items()}
    for name,contents in files.items():
        dest=args.destination/name
        if args.compare:
            assert dest.read_bytes() == contents,name
        else:
            dest.parent.mkdir(exist_ok=True,parents=True)
            assert not dest.exists(),name
            dest.write_bytes(contents)
    print("Validated 1,234 archive entries, 256 original Cargo stdout/stderr pairs and receipts, and all 32 ordered pairs.")

