"""Verify the projected native functional observations and registered comparisons offline."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

if not __debug__:
    raise SystemExit("Run the verifier with Python assertions enabled")

BASE = Path(__file__).resolve().parent
ARMS = ("A", "B")
PHASES = ("original", "edit", "edit-followup", "restore", "final", "cold-edit")
EDITED = {"edit", "edit-followup", "cold-edit"}
TRANSITIONS = {"edit", "restore"}
SELECTORS = {"notebook::hover_past_end_of_cell", "notebook::inlay_hints_range_past_end_of_cell"}
ORIGINAL = "be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7"
EDIT = "d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8"
LISTING = "e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316"
HASH = re.compile(r"[a-f0-9]{64}")
HEX = re.compile(r"[a-f0-9]+")
def sha(blob):
    return hashlib.sha256(blob).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")

def comparison(records, left, right):
    a, b = records[left], records[right]
    assert a["source_sha256"] == b["source_sha256"]
    assert a["behavior"]["listing_sha256"] == b["behavior"]["listing_sha256"]
    aa = {p["path_sha256"]:p for p in a["products"]}
    bb = {p["path_sha256"]:p for p in b["products"]}
    keys = aa.keys() & bb.keys()
    assert len(keys) >= 50
    differences = []
    for k in sorted(keys, key=lambda k: aa[k]["file"]):
        x, y = aa[k], bb[k]
        assert x["file"] == y["file"]
        assert (x["size"], x["normalized"]) == (y["size"], y["normalized"])
        change = (x["build_id"], x["rodata_entsize"]) != (y["build_id"], y["rodata_entsize"])
        assert change == (x["sha256"] != y["sha256"])
        if change:
            differences.append({"file":x["file"],"a_sha256":x["sha256"],"b_sha256":y["sha256"],
                                "a_build_id":x["build_id"],"b_build_id":y["build_id"],
                                "a_rodata_entsize":x["rodata_entsize"],"b_rodata_entsize":y["rodata_entsize"]})
    return {"a":list(left),"b":list(right),"compared":len(keys),"byte_identical":len(keys)-len(differences),"differing_known_fields":differences}

def all_comparisons(records):
    cross = [comparison(records, ("A", q), ("B", q)) for q in PHASES]
    local = [(q, ref) for q, ref in (("edit", "cold-edit"),("edit-followup", "cold-edit"),
                                       ("final", "original"),("restore", "original"))]
    return cross + [comparison(records, (a, q), (a, ref)) for a in ARMS for q, ref in local]

def sealed_files():
    entries = {}
    for line in (BASE/"SHA256SUMS").read_text().splitlines():
        h, sep, name = line.partition("  ")
        p = Path(name)
        assert HASH.fullmatch(h) and sep and str(p)==name and not p.is_absolute() and ".." not in p.parts and name not in entries
        f=BASE/p
        assert f.is_file() and not f.is_symlink() and sha(f.read_bytes())==h,name
        entries[name] = h
    real={p.relative_to(BASE).as_posix() for p in BASE.rglob("*") if p.is_file() and p.name!="SHA256SUMS"}
    assert entries.keys()==real
    return entries

def phase_checked(arm, phase, r, idx):
    assert (r["arm"],r["phase"],r["exit"],r["units"]) == (arm,phase,0,619)
    assert idx["result_sha256"] == r["result_sha256"] and idx["raw_sha256"] == r["raw_sha256"]
    assert HASH.fullmatch(r["result_sha256"]) and all(HASH.fullmatch(v) for v in r["raw_sha256"].values())
    assert set(r["raw_sha256"]) == {"cargo.stdout","cargo.stderr","execs.json","image-contract.json"}
    behavior = r["behavior"]
    assert behavior["listed"] == 200 and behavior["listing_sha256"] == LISTING
    assert behavior["sha256"] == (EDIT if phase in EDITED else ORIGINAL)
    assert behavior["state"] == ("notebook" if phase in EDITED else "original")
    assert behavior["tests"].keys() == SELECTORS
    for row in behavior["tests"].values():
        assert row["exit"] == (101 if phase in EDITED else 0)
        assert all(HASH.fullmatch(row[k]) for k in ("stdout_sha256","stderr_sha256"))
    cold = phase == "cold-edit"
    cohort = "cold" if cold else "transition" if phase in TRANSITIONS else "repeat"
    assert r["cohort"] == cohort and r["fresh"] == {"cold":0,"transition":559,"repeat":563}[cohort]
    native = {"cold":188,"transition":52,"repeat":50}[cohort]
    expected = {"cargo":1,"stock-wild":native,"gcc":783 if cold else native,"collect2":250 if cold else native,
                "rustc-full":{"cold":623,"transition":12,"repeat":1}[cohort]}
    if cold: expected["rustc-query"] = 36
    else: expected["rustc-link-only"] = 43 if phase in TRANSITIONS else 50
    assert r["counts"] == expected
    assert sum(r["full_targets"].values()) == expected["rustc-full"]
    assert cohort != "repeat" or r["full_targets"] == {"ron":1}
    assert r["compiler_args"]["count"] == expected["rustc-full"]+expected.get("rustc-link-only",0)
    assert HASH.fullmatch(r["compiler_args"]["sha256"])
    if cohort == "repeat":
        assert r["native_args"]["count"] == 150 and HASH.fullmatch(r["native_args"]["sha256"])
    else:
        assert r["native_args"] is None
    ps = r["products"]
    assert len(ps)==len({p["path_sha256"] for p in ps})==len({p["file"] for p in ps})==(50 if cohort=="repeat" else 52)
    for p in ps:
        assert Path(p["file"]).name == p["file"] and p["size"]>0
        assert all(HASH.fullmatch(p[k]) for k in ("path_sha256","normalized","sha256"))
        assert HEX.fullmatch(p["build_id"]) and 16<=len(p["build_id"])<=128 and len(p["build_id"])%2==0
        assert p["rodata_entsize"] in (0,1,2,4,8,16,32,64,128,256)
    selected,=[p for p in ps if p["file"]==behavior["file"]]
    assert selected["sha256"]==behavior["sha256"]
    wild_names = Counter(r["wild_output_names"])
    assert wild_names.total()==native
    for p in ps: assert wild_names[p["file"]]==1
    if not cold: assert {p["file"] for p in ps}==set(wild_names)

def check_cold(arm, record):
    r=read(BASE/"cold-native"/(arm+".json"))
    assert r["arm"]==arm and r["raw_execs_sha256"]==record["raw_sha256"]["execs.json"]
    assert r["source_result_sha256"]==record["result_sha256"]
    rows=r["wild_outputs"]
    assert len(rows)==188 and Counter(x["file"] for x in rows)==Counter(record["wild_output_names"])
    assert [x["event"] for x in rows]==list(range(188))
    assert len({x["pid"] for x in rows})==188
    products={p["path_sha256"]:p for p in record["products"]}
    found=set()
    for x in rows:
        assert HASH.fullmatch(x["argv_sha256"]) and HASH.fullmatch(x["path_sha256"]) and x["exit"]==0
        assert Path(x["file"]).name==x["file"]
        if x["status"]=="retained":
            assert x["size"]>0 and HASH.fullmatch(x["sha256"])
        else:
            assert x["status"] in ("removed-before-readback","shared-name","outside-stores","nonregular-at-readback")
            assert "sha256" not in x and "size" not in x
        if x["path_sha256"] in products:
            p=products[x["path_sha256"]]
            assert (x["status"],x["size"],x["sha256"])==("retained",p["size"],p["sha256"])
            found.add(x["path_sha256"])
    assert found==products.keys() and r["statuses"]==dict(Counter(x["status"] for x in rows))
    return r["statuses"]

def main():
    import runpy
    sealed_files()
    assert runpy.run_path(str(BASE/"elf.py"))["selftest"]()["different_text_rejected"]
    meta=read(BASE/"provenance.json")
    raw_admission = BASE/"original-admission.json"
    assert meta["native_qualification_sha256"]==sha(raw_admission.read_bytes())
    original=read(raw_admission)
    assert original["eligible"] is True
    assert original["images"] == {k:meta["tools"][k] for k in ARMS}
    assert original["binding_sha256"]==meta["build_receipts"]
    assert original["worker_sha256"]==meta["worker_sha256"] and original["lane_sha256"]==meta["lane_sha256"]
    assert original["plan_sha256"]==meta["plan_sha256"] and meta["elf_reader_sha256"]==sha((BASE/"elf.py").read_bytes())
    assert original["receipts"]=={"gate-v4-"+a+"-"+q:meta["receipts"][a][q]["result_sha256"] for a in ARMS for q in PHASES}
    records={}
    for arm in ARMS:
        for phase in PHASES:
            r=read(BASE/"phases"/(arm+"-"+phase+".json"));phase_checked(arm,phase,r,meta["receipts"][arm][phase]);records[arm,phase]=r
    for ph in PHASES:
        if ph!="cold-edit":assert records["A",ph]["compiler_args"]==records["B",ph]["compiler_args"]
    assert records["A","original"]["native_args"]==records["B","original"]["native_args"]
    assert {v["source_sha256"] for k,v in records.items() if k[1] in EDITED}=={meta["sources"]["edited_sha256"]}
    assert {v["source_sha256"] for k,v in records.items() if k[1] not in EDITED}=={meta["sources"]["original_sha256"]}
    comparisons=all_comparisons(records)
    for c in original["comparisons"]:
        c["differing_known_fields"].sort(key=lambda x:x["file"])
    assert comparisons==read(BASE/"comparisons.json")==original["comparisons"]
    assert len(comparisons)==14 and sum(len(r["products"]) for r in records.values())==612
    assert meta["comparison_projection_sha256"]==sha(canonical(comparisons))
    print("12 functional commands, 612 enrolled ELF observations, 14 reconstructed comparisons, 24 notebook verdicts")
    summary=read(BASE/"summary.json")
    assert [summary[k] for k in ("functional_commands","registered_elf_observations","registered_comparisons","listing_processes","notebook_selector_processes")]==[12,612,14,12,24]
    assert summary["comparison_totals"]=={"product_comparisons":sum(c["compared"] for c in comparisons),"raw_equal":sum(c["byte_identical"] for c in comparisons),"raw_different":sum(len(c["differing_known_fields"]) for c in comparisons)}
    for arm in ARMS:
        statuses=check_cold(arm,records[arm,"cold-edit"])
        assert summary["additional_cold_readbacks"][arm]==statuses
        print("188 physical cold native commands",arm,statuses)
    print("Raw identity by comparison",[(c["byte_identical"],c["compared"]) for c in comparisons])
if __name__=="__main__":
    main()
