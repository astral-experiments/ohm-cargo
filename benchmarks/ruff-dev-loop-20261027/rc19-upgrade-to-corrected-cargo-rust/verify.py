from pathlib import Path
from collections import Counter
import hashlib
import json
import re

root=Path(__file__).resolve().parent
images=json.loads((root/"images.json").read_bytes())
data=json.loads((root/"histories.json").read_bytes())
release=images["release"]
assert release["archive"]=="ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812"
assert release["release"] == "ohm-1.99.0-19"
assert "235f9228651b74c591e6f62cae4c9b761448dd2d" in release["versions"]["cargo"]
assert "eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53" in release["versions"]["rustc"]
old={k:release["images"][k] for k in ("cargo","rustc")}
new=images["candidate"]
assert old=={"cargo":"789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1","rustc":"5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511"}
assert new=={"cargo":"a9c1b18bbb02f541bcf089db9d4286c215ffc8036fa1ff443e59c9210e77771c","rustc":"fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"}
assert set(data)=={"same-release-control","full-release-upgrade","cargo-only-upgrade"}
errors=set(); totals=Counter()
for mode,run in data.items():
    changed=mode!="same-release-control"
    expected={"cargo":new["cargo"] if changed else old["cargo"],"rustc":new["rustc"] if mode=="full-release-upgrade" else old["rustc"]}
    for key,files in (("check",105),("build",41)):
        change=run[key]["upgrade"];assert change["before"]==old and change["after"]==expected
        assert change["state_files"]==files and re.fullmatch("[a-f0-9]{64}",change["state_identity_and_digest"])
    checks=run["check"]["phases"];assert len(checks)==10 and run["check"]["events"]==["hold-fd","release-fd"]
    for name,entry in checks.items():
        invalid=name in ("edited-clean","independent-after-upgrade") or changed and name in ("first-after-upgrade","second-after-upgrade")
        assert entry["success"] is (not invalid)
        if invalid:
            err,=entry["errors"];assert err[:3]==["client","E0034","multiple applicable items in scope"]
            errors.add(err[3])
        else:assert entry["errors"]==[]
        assert all(re.fullmatch("[0-9a-f]{64}",entry[k]) for k in ("stdout","stderr"))
    previous=checks["edited-repeat"]["artifacts"];after=checks["first-after-upgrade"]["artifacts"]
    assert set(previous)=={"api","reader","client","provider"} and all(i["fresh"] for i in previous.values())
    if changed:
        assert set(after)=={"api","reader","provider"} and not any(i["fresh"] for i in after.values())
        assert all(after[k]["files"]!=previous[k]["files"] for k in after)
        assert all(i["fresh"] for i in checks["second-after-upgrade"]["artifacts"].values())
    else:assert after==previous
    bp=run["build"]["result"];assert bp["value"]==1 and bp["mode"]=="default" and bp["cargo_sha256"]==expected["cargo"] and bp["rustc_sha256"]==expected["rustc"]
    phases=bp["phases"];assert phases["forced-failure"]["exit"]==101
    assert phases["prime-program"]["files"]["stdout"]==phases["final-program"]["files"]["stdout"]==hashlib.sha256(b"1\n").hexdigest()
    first=phases["reverted"]
    if changed:
        assert bp["first_success"]=="reverted" and first["exit"]==0 and first["errors"]==[] and "untouched-1" not in phases
        assert first["rustcs"]==[["dep","lib"],["app","lib"],["app","bin"]]
    else:
        assert bp["first_success"]=="untouched-1" and first["exit"]==101 and first["errors"]==["E0460"]
        assert first["rustcs"]==[["dep","lib"],["app","bin"]] and phases["untouched-1"]["exit"]==0
    totals["checks"]+=len(checks);totals["builds"]+=len(phases)-2
assert totals=={"checks":30,"builds":13} and len(errors)==1
if (root/"SHA256SUMS").exists():
    for row in (root/"SHA256SUMS").read_text().splitlines():
        h,n=row.split("  ",1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h
print("Verified three preserved-cache toolchain transitions, 30 checks, 13 builds and all six native program executions.")
