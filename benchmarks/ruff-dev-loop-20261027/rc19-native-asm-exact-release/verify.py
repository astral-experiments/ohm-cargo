"""Verify the published field-level gates, including the observed assembler failure."""
from pathlib import Path
from hashlib import file_digest
import json
import sys

root = Path(__file__).resolve().parent
def load(name):
    return json.loads((root/name).read_bytes())

def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()

listed = {}
for line in (root/"SHA256SUMS").read_text().splitlines():
    expected, name = line.split("  ", 1)
    assert name not in listed and Path(name).name == name
    listed[name] = expected
assert set(listed) == {f.name for f in root.iterdir() if f.is_file() and f.name != "SHA256SUMS"}
assert all(digest(root/name) == expected for name,expected in listed.items())
s = load("subjects.json")
assert s["source"] == "ca780121cea38bb9b0538d020d4bcce76ca30cbc"
assert s["tree"] == "400fa38b36fca7d84c58331d188df2d725e0b419"
assert s["cargo_gitlink"] == s["cargo"]["commit"] == "2447f7f4eacb4fdf499899929f08d0de19abb4d0"
assert s["cargo"]["tree"] == "b9496c0cbd39e102be38433f9eb193e343fb4fe9"
compiler = s["compiler"]
assert len(compiler["target_files"]) == 53 and {"core","alloc","std"} <= set(compiler["actual_stage1_crates"])
assert compiler["wild_built"] == compiler["pgo"] == compiler["bolt"] == False
assert s["bootstrap"]["exit"] == 0 and s["bootstrap"]["stage"] == 1
assert s["bootstrap"]["first_postbuild_verifier_exit"] == 1
joined=s["bootstrap"]["joined_original_execs"]
assert "core" in joined["missing_initially"] and joined["all_library_files_verified"]==53
core, = [e for e in joined["accounted_source_records"] if e["crate"]=="core"]
assert (core["pid"],core["start_line"],core["completion_line"]) == (352891,11135,11137)
assert s["source"] in compiler["version"] and s["cargo"]["commit"] in s["rustup_routing"]["cargo"]
assert s["cargo"]["binary_sha256"] == s["rustup_routing"]["cargo_sha256"] == "e9d797db90e051284931870fa2be6648e09e6878f1a2b5176f4848889e6c4fae"
assert s["wild"] == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
d = load("diagnostics.json")
for provider in d["providers"].values():
    assert provider["verdict"] == "correct" and provider["compiler_invocations"] > 0
    assert all(provider["physical_checks"].values()) and len(provider["phases"]) == 7
    ps = {r["phase"]:r for r in provider["phases"]}
    edited = [ps[k] for k in ("edited","edited-repeat","edited-clean")]
    assert all(not r["finished"]["success"] for r in edited)
    assert all(r["errors"] == edited[0]["errors"] for r in edited)
    error, = edited[0]["errors"]
    assert (error["crate"], error["code"], error["span"]) == ("client","E0034",3)
    for k in ("original","original-repeat","restore","restore-repeat"):
        assert ps[k]["finished"]["success"] and not ps[k]["errors"]
f = d["failed_then_reverted"]
assert f["first_success"] == "reverted" and f["value"] == 1
assert f["phases"]["forced-failure"]["exit"] == 101
assert not f["phases"]["reverted"]["errors"] and f["phases"]["reverted"]["exit"] == 0
i = d["genuine_interruption"]
assert i["interrupted-provider"]["rc"] == 101
assert all(i[k]["program_stdout"].strip() == "17" for k in ("seed","unchanged","revert","revert-again","clean-revert"))
assert i["revert"]["elf"] == i["clean-revert"]["elf"]
assert i["independent-valid-change"]["program_stdout"].strip() == "29"
assert all(f["passed"] and f["rc"]==101 and f["parent_eisdir"] and not f["deadline"] and f["writer_processes"]==0 for f in d["fifo"].values())
assert len(d["checked_in_conditional"]["tests"]) == 3 and set(d["checked_in_conditional"]["tests"].values()) == {"ok"}
n = load("native.json"); stages=n["stages"]
assert len(stages) == 9 and stages["01-first"]["value"] == stages["02-unchanged"]["value"] == stages["09-remove-and-recover"]["value"] == 17
assert not stages["02-unchanged"]["processes"]
triple = [stages[k] for k in ("03-real-edit","04-same-state-forced","05-independent-empty-valid")]
assert all(r["value"] == 29 and r["status"] == 0 and r["elf"] == triple[0]["elf"] for r in triple)
for k in ("03-real-edit","06-real-restore-malformed"):
    p = stages[k]["processes"]
    assert any(v.get("crate") == "reader" and v["link_only"] and v["exe"] == compiler["frontend"] for v in p)
    assert any(v["type"] == "linker" and v["exe"] == s["wild"] for v in p)
for k in ("06-real-restore-malformed","07-same-state-forced-malformed","08-independent-empty-malformed"):
    assert stages[k]["status"] == 101 and stages[k]["native_error"]
checks=n["metadata_check"];assert len(checks)==7 and not any(r["linkers"] for r in checks.values())
assert checks["public-api"]["diagnostics"] == checks["empty-public-api"]["diagnostics"] == ["E0061"]
assert not checks["initial-unchanged"]["compiler_units"] and not checks["private-body-unchanged"]["compiler_units"]
assert n["checked_in"]["exit"] == 0 and sorted(n["checked_in"]["tests"]) == sorted(n["checked_in"]["expected"])
assert len(n["rust_run_make"]) == 2 and all(r["exit"] == 0 and r["compiler_under_test"] == compiler["frontend"] for r in n["rust_run_make"].values())

asm = load("assembler.json")
for role,a in asm.items():
    assert not a["incremental"] and a["relationship"] == "unused-public"
    assert a["defaults_off"] == (role=="defaults-off")
    assert a["semantic_exit"]==int(role=="default") and all(v == (role=="defaults-off") for v in a["semantic_check"]["checks"].values())
    p=a["records"];assert len(p)==9 and p["01-cold"]["native"] == p["10-recovered"]["native"] == 17
    assert not p["02-unchanged"]["processes"]
    assert p["04-independent-clean"]["native"] == p["05-forced-full-keep-incremental"]["native"] == 29
    assert p["08-independent-missing"]["status"] == p["09-forced-same-missing"]["status"] == 101
    for key in ("04-independent-clean","05-forced-full-keep-incremental"):
        assert any(o["nearest_compiler"] == "reader" and o["open_successful"] for o in p[key]["asset_opens"])
    edit=p["03-edit-and-new-asset"]; missing=p["07-source-restore-missing-asset"]
    if role=="default":
        assert edit["native"] == 17 and not edit["asset_opens"] and not missing["status"] and missing["native"] == 29
        assert not missing["asset_opens"]
        assert all(any(v.get("unit")=="reader" and v["link_only"] and v["exe"]==compiler["frontend"] for v in z["processes"]) for z in (edit,missing))
        assert all(any(v["type"]=="linker" and v["exe"]==s["wild"] for v in z["processes"]) for z in (edit,missing))
    else:
        assert edit["native"] == 29 and missing["status"] == 101
        assert any(o["nearest_compiler"] == "reader" and o["open_successful"] for o in edit["asset_opens"])
        assert any(o["nearest_compiler"] == "reader" and o["missing"] for o in missing["asset_opens"])
print("Verified ca780/2447 on Linux, 53 standard-library files, controlled diagnostics and recovery, nine native and seven check-only commands. The two-nine-command assembler control rejects release safety.")
