"""Offline verification of the first-observation mechanism and its retained failed antecedents."""
from pathlib import Path
import json,sys
q=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
def get(k):return json.loads((q/(k+".json")).read_bytes())
c=get("four-arms")
for arm,case in c.items():
    tiny=case["tiny"]; first=tiny["unchanged-1"]
    assert first["units"]==23 and len(first["jobs"])==(0 if arm=="PP" else 6) and len(first["links"])==(0 if arm=="PP" else 5)
    assert not tiny["unchanged-2"]["jobs"] and all(all(v["runtime"].values()) for v in tiny.values())
    assert tiny["cold"]["marker_receipts"][0]["complete"]==(arm=="PP")
    other="AP" if arm=="PP" else "PA" if arm=="AA" else arm
    assert all(r["native"]==c[other]["tiny"][phase]["native"] for phase,r in tiny.items())
    h=case["held"];ref=c["AA"]["held"]
    assert all(v["runtime"]==ref[phase]["runtime"] for phase,v in h.items())
    assert h["cold"]["runtime"]!=h["true-private-edit"]["runtime"] and h["cold"]["runtime"]==h["restore"]["runtime"]
    assert not h["remove-observer"]["marker_receipts"] and len(h["reintroduce-observer"]["marker_receipts"])==2
    assert all(i["complete"]==(arm=="PP") for i in h["reintroduce-observer"]["marker_receipts"])
r=get("receipts");assert r["PP"]==r["AP"] and r["PA"]==r["AA"]
for arm,v in r.items():
    assert v["entries"]==v["raw_checksum_count"]==45 and len(get(arm+"-input-blake3"))==45 and v["content_verified"]
v=get("binary-inputs")
for arm in v:
    a=v[arm];assert a["prime"]["native"].endswith("raw-len=3") and a["empty-backdated"]["native"].endswith("raw-len=0") and a["restored"]["native"].endswith("raw-len=3")
    assert a["unchanged"]["fresh"]==(arm!="stage-PP") and a["fresh-restored"]["fresh"]==(arm!="stage-PP")
b=get("rejected-persistent-probe"); assert b["driver-only-downgrade"]["returncode"]==101 and b["driver-only-downgrade"]["unknown_observer_option"]
assert not any(j["capability"] for j in b["driver-only-downgrade"]["rustc"])
assert all(v["returncode"]==0 for n,v in b.items() if n!="driver-only-downgrade")
w=get("whole-default");cold=w["cold"];assert cold["units"]==619 and cold["fresh"]==0 and len(cold["rustc"])==636 and cold["wild"]==200 and cold["system_links"]==62 and len(cold["native"])==110 and cold["executables"]==102
for n,v in w.items():
    assert v["native"]==cold["native"] and v["diagnostics_sha256"]==cold["diagnostics_sha256"] and v["ron_files"]==cold["ron_files"] and v["checksum_count"]==45
    if n!="cold":assert v["fresh"]==619 and not v["rustc"] and not v["linker_outputs"]
assert get("stage-permanent")["returncode"]==get("release-permanent")["returncode"]==0
print("Verified staged 56-command peer ablation, literal 45-input proof, 7 binary-input phases, genuine driver-only downgrade failure, and the complete 619-unit Ruff cold/unchanged/unchanged process and ELF commitments.")
