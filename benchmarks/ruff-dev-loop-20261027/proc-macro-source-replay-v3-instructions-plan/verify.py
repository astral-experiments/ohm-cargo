"""Verify the frozen protocol and all parent-only admission receipts, without compiler binaries."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import statistics
import subprocess
import sys

p=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
read=lambda f:json.loads(f.read_bytes())
manifest={name:h for line in (p/"SHA256SUMS").read_text().splitlines() for h,name in [line.split("  ",1)]}
assert set(manifest)=={f.relative_to(p).as_posix() for f in p.rglob("*") if f.is_file() and f!=p/"SHA256SUMS"}
assert all(sha(p/name)==h for name,h in manifest.items())
plan=read(p/"plan.json")
assert subprocess.check_output([sys.executable,"-B",str(p/"make-registration.py")])==(p/"plan.json").read_bytes()
assert sha(p/"native-worker.py")==plan["native_runner"] and sha(p/"native-plan.json")==plan["native_protocol"]
assert len(plan["blocks"])==12 and sum(b["endpoints"][0]=="empty" for b in plan["blocks"])==6
for ep in ("empty","retained"):
    assert sum(b[ep][0]=="parent" for b in plan["blocks"])==6
    assert all(set(b[ep])=={"candidate","parent"} and set(b["endpoints"])=={"empty","retained"} for b in plan["blocks"])
assert sum(math.comb(12,k) for k in range(10,13))==79
cal=p/"calibration/scoped-parser-instructions-aa1";rows=read(cal/"observations.json")
assert len(rows)==6 and read(cal/"complete.json")["rows"]==sha(cal/"observations.json")==plan["calibration_rows"]
sdk=p/"calibration/parser-counter-sdk-v1"
assert read(sdk/"collector-files.json")==plan["collector"]["actual_files"] and sha(sdk/"counter.c")==read(sdk/"collector-files.json")["counter.c"]
def evs(f):
    ev=[(s,int(pid),int(t),int(v)) for s,pid,t,v in (line.split() for line in f.read_text().splitlines())]
    assert len({pid for s,pid,t,v in ev}) == 1 and ev[0][0]=="B" and ev[-1][0]=="P"
    starts=Counter(t for s,pid,t,v in ev if s=="T");ends=Counter(t for s,pid,t,v in ev if s=="F")
    assert starts==ends and all(n==1 for n in ends.values())
    return sum(v for s,pid,t,v in ev if s=="F"),len(ends),[v for s,pid,t,v in ev if s=="S"],Counter(s for s,pid,t,v in ev)
assert evs(sdk/"toy.ir")[2]==[11] and evs(sdk/"toy-x.ir")[:3]==(3000052,1,[])
assert evs(sdk/"toy-t.ir")[:3]==(9000121,3,[])
native=read(p/"native-certificate.json")
assert sha(p/"native-certificate.json")==plan["native_certificate"] and native["primary_observations"]==0
for i,row in enumerate(rows):
    assert row["arm"]=="parent" and row["actual_driver_sha256"]==plan["arms"]["parent"]["driver_sha256"]
    h=row["history"];slot=cal/f"{i:02d}-{h}";total,threads,signals,counts=evs(slot/"counter.txt")
    assert (total,threads,signals,dict(counts))==(row["instructions"],83,[10],row["record_counts"])
    gold=native["oracles"]["parent"][h]
    assert row["rmeta_sha256"]==row["archive_rmeta_sha256"]==gold["rmeta_sha256"] and row["header"]==gold["header"]
    old=read(slot/"archive-oracle.json");assert old["equal"] and old["native"]==old["instrumented"]
    extra=read(p/"admission/six-native-oracles"/f"{i:02d}-{h}.json");assert extra["native"]==extra["instruction_counted"] and extra["native_names"]==extra["instruction_counted_names"]
adm=read(p/"admission/admission.json")
assert adm["parent_only"] and adm["new_candidate_counts"]==0 and adm["protocol"]==sha(p/"plan.json")
assert adm["input_sha"]==sha(p/"admission/inputs.json")
inp=read(p/"admission/inputs.json")
assert len(inp["externs"])==16 and inp["argv"][1:]==rows[0]["child"]["argv"][2:]
assert inp["frontend"]==plan["frontend_sha256"] and inp["cargo"]==plan["cargo_sha256"]
slot=p/"admission/map-calibration-parent"; row=read(slot/"outcome.json");m=read(slot/"mappings.json")
assert row==adm["calibration"]["map_control"] and row["arm"]=="parent" and row["history"]=="retained"
assert evs(slot/"counter.txt")[:2]==(row["instructions"],row["thread_count"])
assert sha(slot/"mappings.json")==row["mapping_receipt"] and sha(slot/"counter.txt")==row["raw_counter"]
assert m["complete"] and not m["timed_out"] and len({v["pid"] for v in m["captured"].values()})==1
assert set(m["captured"])=={"frontend","driver","derive","runtime","client"}
for k,v in m["captured"].items():assert [v["device"],v["inode"]]==m["expected"][k]
print("Verified six independent same-image counter runs, one mapped production parent, every native compiler archive and the 48 frozen candidate/control slots.")
