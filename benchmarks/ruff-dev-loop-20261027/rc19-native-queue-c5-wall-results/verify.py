"""Reopen the C5 complete ordinary-pair ledger and apply the two registered scoring programs."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()
for name, wanted in {
    "observations.json.gz": "bd0baab41eb039b19e1cf5e845968c7d26777cd7ed542143047451c4ee468940",
    "analysis.py": "b76ab9cf870c25b7ddbe20efe8dbe6ba09b34fe4e6e6e95777d441228816ebdf",
    "order.json": "db9a7dff6e92e03349af00832b6693e7d1d6d844a750d709f79ebe0925186ed4",
}.items():
    assert digest(here/name) == wanted
data = json.loads(gzip.decompress((here/"observations.json.gz").read_bytes()))
order = json.loads((here/"order.json").read_bytes())["primary"]
ledger = data["sections"]
assert set(data["terminals"]) == set(ledger) == {"batch1", "batch2", "plain", "edit"}
assert data["release"]["source"] == {"A":"235f9228651b74c591e6f62cae4c9b761448dd2d","B":"4b0751af97bfa22204a013d0d1f0707382b0df52"}
assert data["release"]["eligible"] and data["release"]["order_sha256"] == data["order_sha256"]
assert data["release"]["images"] == {"A":"6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac","B":"419200f1010d167502103a3f1964c937eec8c22ade26a021309718b854363f94"}
listed = "e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316"
expected_tests = {"notebook::hover_past_end_of_cell", "notebook::inlay_hints_range_past_end_of_cell"}
programs = {"original":"be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7",
            "notebook":"d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8"}
formats=Counter()
native=[]
def outcome(value, typed, fresh=None):
    assert value["exit"] == 0 and value["wall_ns"] > 0
    assert all(len(value[k+"_sha256"]) == 64 for k in ("stdout","stderr"))
    if typed:
        assert (value["units"],value["fresh"]) == (619,fresh)
    else:
        assert "units" not in value
    formats["typed" if typed else "plain"] += 1
def oracle(value, exact):
    assert value["listed"] == 200 and value["listing_sha256"] == listed
    assert set(value["tests"]) == expected_tests
    assert all(r["exit"] == (0 if value["state"] == "original" else 101) for r in value["tests"].values())
    if exact:
        assert value["sha256"] == programs[value["state"]]
def quiet(before,after):
    assert before["affinity"] == after["affinity"] == list(range(32))
    assert not before["other_builds"] and not after["other_builds"]
    assert before["oom_kill"] == after["oom_kill"]
for section,block in ledger.items():
    pairs=block["pairs"]
    expected_order=(order["batches"][int(section[-1])-1] if section.startswith("batch")
                    else order["edit_and_repeat" if section == "edit" else "plain"])
    assert [p["order"] for p in pairs] == expected_order
    if section.startswith("batch"):
        assert all(Counter(expected_order[i:i+8])=={"AB":4,"BA":4} for i in range(0,48,8))
    assert len(pairs) == len(block["per_pair"]) and data["terminals"][section]["exit"] == hashlib.sha256(b"0\n").hexdigest()
    assert data["terminals"][section]["stderr"] == hashlib.sha256(b"").hexdigest()
    quiet(*block["overall_host"])
    for idx,(pair,host) in enumerate(zip(pairs,block["per_pair"],strict=True)):
        quiet(host["before"],host["after"])
        assert host["same_declared_roster"] and host["rosters"]["A"] == host["rosters"]["B"]
        for arm in "AB":
            if section == "edit":
                assert pair["state"] == ("notebook" if idx % 2 == 0 else "original")
                assert pair[arm]["behavior"]["state"] == pair["state"]
                oracle(pair[arm]["behavior"],True)
                for phase,fresh in (("edit",559),("repeat",563)):
                    outcome(pair[arm][phase],True,fresh)
            else:
                outcome(pair[arm],section!="plain",563)
    for phase,arms in block["censuses"].items():
        a,b = [arms[arm] for arm in "AB"]
        for item in (a,b):
            assert item["full"] == ["ron"] and item["units"] == 619 and item["fresh"] == 563
            assert item["exit"] == 0 and item["counts"] == {
                "cargo": 1, "rustc-full": 1, "rustc-link-only": 50, "gcc": 50, "collect2": 50, "stock-wild": 50}
            assert len(item["compiler_args"]) == 51 and len(item["native_args"]) == 150 and len(item["products"]) == 50
            oracle(item["behavior"],False)
        assert a["compiler_args"] == b["compiler_args"] and a["products"].keys() == b["products"].keys()
        argsdiff = [(l["target"],l["tool"]) for l,r in zip(a["native_args"],b["native_args"],strict=True) if l != r]
        same = sum(a["products"][k]["sha256"] == b["products"][k]["sha256"] for k in a["products"])
        assert all(a["products"][k]["fields"]["normalized"] == b["products"][k]["fields"]["normalized"] and
                   a["products"][k]["fields"]["bytes"] == b["products"][k]["fields"]["bytes"] for k in a["products"])
        if section == "edit" and phase == "trace-after":
            assert len(argsdiff) == 21 and len({target for target,tool in argsdiff}) == 7 and same==48
        else:
            assert not argsdiff
            assert same==(49 if section=="edit" and phase=="trace-before" else 50)
        native.append({"section":section,"flank":phase,"raw_equal":same,"equal_except_qualified_fields":50,
                       "different_native_arguments":len(argsdiff),"max_pss_mib":{arm:item["memory"]["max_pss_bytes"]//1048576 for arm,item in arms.items()}})
assert formats == {"typed":240,"plain":32} and len(native)==8
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    for name,inp in (("primary",[ledger["batch1"]["pairs"],ledger["batch2"]["pairs"]]),("plain",ledger["plain"]["pairs"]),("edit",ledger["edit"]["pairs"])):
        (tmp/name).write_text(json.dumps(inp))
    cmd=[sys.executable,"-IB"]
    primary=json.loads(subprocess.check_output([*cmd,here/"analysis.py","primary",tmp/"primary"]))
    secondary=json.loads(subprocess.check_output([*cmd,here/"secondary.py","primary",here/"order.json",tmp/"plain","--edit-file",tmp/"edit"]))
result={"stationary":primary,"additional":secondary,"command_counts":dict(formats),"native_flanks":native}
if "--emit" in sys.argv:
    print(json.dumps(result,indent=2,sort_keys=True))
else:
    assert result == json.loads((here/"result.json").read_bytes())
    print("Verified 272 timed C5 commands, all 24 edited/restored native oracles, 16 flanking native builds, and the full registered inference.")
