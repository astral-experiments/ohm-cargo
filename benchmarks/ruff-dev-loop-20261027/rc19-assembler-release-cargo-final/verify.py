"""Check the independently recorded Cargo diagnostics and native results."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
def read(name):
    return json.loads((root / name).read_bytes())
def digest(bytes_):
    return hashlib.sha256(bytes_).hexdigest()
def is_sha(s):
    return bool(re.fullmatch("[0-9a-f]{64}",s))
subjects=read("subjects.json")
final=subjects["final"]
assert final["commit"]=="a8f0c9aa0412aa259c686416a48aa8d2cf92da72"
assert final["binary_sha256"]=="ad893345f66ade1c886309b0fc2f98ec5b225d206c176e356531f0e3467eff81"
assert "commit-hash: "+final["commit"] in final["version"].splitlines()
assert (final["ordered_externs"], final["linker_inputs"], final["rlibs"])==(239,335,326)
assert subjects["ci"]=={"run":40841955598,"head":final["commit"],"applicable_passed":8,"conditional_skipped":1}
parent=subjects["parent"]
assert len(parent["load_segments"])==4 and parent["historical_binary"]!=parent["reconstructed_binary"]
assert parent["symbol_names_changed"]==232 and parent["symbol_count"]==69007
assert parent["verified_ordered_externs"]==239
assert parent["verified_linker_inputs"]==335
phases=["initial","poison","poison-confirm","first-after-upgrade","repeat-after-upgrade","opposite-edit-after-upgrade","repeat-opposite","restored-after-upgrade"]
for name, binding in subjects["bindings"].items():
    arm=read(name+"-upgrade.json")
    source=arm["verified"]
    assert binding["cargo"]==source["new_cargo"]==final["binary_sha256"] and binding["rustc"]==source["rustc"]
    assert source["old_cargo"]=="789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1"
    assert binding["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    check=arm["check"]
    assert [v["success"] for v in check]==[True]*4+[False]*4
    assert all(v["errors"]==check[4]["errors"] for v in check[4:])
    assert [(e["target"],e["code"],e["primary"]) for e in check[4]["errors"]]==[("client","E0034",[["main.rs",3,30]])]
    assert all(is_sha(v["stdout_sha"]) and is_sha(v["stderr_sha"]) for v in check)
    assert arm["build"]["first_success"]=="reverted" and arm["build"]["stdout_sha256"]==digest(b"1\n") and arm["build"]["value"]==1
    for poison,expected in {"valid":[17,17,17,29,29,101,101,17],"malformed":[17,17,17,101,101,29,29,17]}.items():
        records=arm["native"][poison]
        assert records["unchanged_target_and_source_snapshot"]==source["native"][poison]["snapshot"]
        assert records["unchanged_target_and_source_snapshot"]["files"]>200
        rows=records["rows"];assert [r["phase"] for r in rows]==phases
        assert [r["cargo"] or r["value"] for r in rows]==source["native"][poison]["verdicts"]==expected
        for r in rows:
            if r["cargo"]:
                assert r["cargo"]==101 and r["link_error"] and r["wild"]>0
            else:
                assert r["native_exit"]==0
                if r["phase"] in {"repeat-after-upgrade","repeat-opposite"}:
                    assert r["fresh"] and r["wild"]==0 and not r["rustc"]
asm=read("assembler.json")
native=asm["used_integration_and_binary"]
assert [(r["cargo"],r["native"]) for r in native]==[(0,"1:65"),(0,"22:66"),(101,"22:66")]
for r in native:
    assert r["link"]==[] and {"reader","integration"}<=set(r["full"])
    assert r["payload_opens"].count("missing" if r["phase"]==2 else "present")>=2
    assert r["kernel_sha256"] and all(is_sha(x) for x in r["kernel_sha256"])
generic=asm["safe_cross_crate_bin"]
assert generic["cargo"]==final["binary_sha256"] and generic["rustc"]==subjects["bindings"]["sdk"]["rustc"]
rows=generic["rows"]
assert len(rows)==14
assert rows["default.edited"]["value"]==rows["default.empty-edited"]["value"]=="9:29"
assert rows["default.missing"]["status"]==rows["default.empty-missing"]["status"]==101
assert rows["explicit.edited"]["value"]==rows["explicit.repeat"]["value"]=="9:17" and rows["explicit.empty-edited"]["value"]=="9:29"
assert rows["explicit.missing"]["status"]==0 and rows["explicit.missing"]["value"]=="7:17" and rows["explicit.empty-missing"]["status"]==101
for name,want in (("default",False),("explicit",True)):
    r=rows[name+".edited"]
    assert [p["link_only"] for p in r["compiler"] if p["name"]=="app"]==[want]
    assert rows[name+".repeat"]["target_fresh"] and not rows[name+".repeat"]["compiler"]
    for p in (r,rows[name+".missing"]):
        assert is_sha(p["streams"]["stdout"]) and is_sha(p["streams"]["stderr"])
print("Verified both published-target upgrade series, real bin and test assembler opens, and 14 default and explicit Cargo builds.")
