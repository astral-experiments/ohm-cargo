"""Recompute all prospective measurements from fast basic-block/thread ledgers and ordinary Rust outputs."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import subprocess
import sys

p=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
digest=lambda b:hashlib.sha256(b).hexdigest()
load=lambda f:json.loads(f.read_bytes())
sums={name:h for line in (p/"SHA256SUMS").read_text().splitlines() for h,name in [line.split("  ",1)]}
assert set(sums)=={f.relative_to(p).as_posix() for f in p.rglob("*") if f.is_file() and f.name!="SHA256SUMS"}
assert all(sha(p/name)==expected for name,expected in sums.items())
plan=load(p/"plan.json");assert sha(p/"plan.json")=="b24902705786b61a4bd693db0de6fd54c88fab1b480f7c7a6ee09acc0c61c7a2"
assert sha(p/"analyze.py")==plan["analyzer"]
assert sha(p/"admission.json")=="347197c47998921e0b33164d3f4eef3e406113be6224e0f7f115354afc6b1508"
adm=load(p/"admission.json");assert adm["input_sha"]==sha(p/"inputs.json")
inp=load(p/"inputs.json");assert len(inp["externs"])==16 and inp["frontend"]==plan["frontend_sha256"]
records=load(p/"observations.json");done=load(p/"complete.json");assert done["complete_pairs_per_history"]==12 and done["observations"]==sha(p/"observations.json")
assert done["registration"]==sha(p/"plan.json") and done["admission"]==sha(p/"admission.json")
prefix=(p/"collector-stderr-prefix").read_bytes();seen_native={}
for n,row in enumerate(records):
    arm,ep,i = row["arm"],row["endpoint"],row["pair"]
    d=p/"records"/f"{i:02d}-{ep}-{arm}"; o=p/"ordinary"/arm/ep;gold=load(o/"result.json")
    assert load(d/"outcome.json")=={k:v for k,v in row.items() if k not in {"pair","endpoint"}}
    assert (d/"stdout").read_bytes()==(o/"stdout").read_bytes()
    assert (d/"stderr").read_bytes()==prefix+(o/"stderr").read_bytes()
    assert row["collector_stderr_prefix"]==digest(prefix) and row["compiler_stderr"]==sha(o/"stderr") and row["compiler_stdout"]==sha(o/"stdout")
    assert (d/"launcher.stderr").read_bytes()==(o/"launcher.stderr").read_bytes()
    assert (d/"metadata.root").read_bytes()==(o/"metadata.root").read_bytes()
    assert row["rmeta_sha256"]==row["archive_rmeta_sha256"]==gold["rmeta_sha256"]
    assert row["header"]==gold["header"] and row["actual_driver_sha256"]==plan["arms"][arm]["driver_sha256"]
    child=load(d/"child.json")
    assert child==row["child"] and child["exit"]==0 and child["wall_ns"] is None and child["affinity"]==list(range(24))
    assert child["argv"][2:]==inp["argv"][1:]
    assert child["actual_count_command"][6].endswith("/rustup/toolchains/ohm/bin/rustc") and child["actual_count_command"][7:]==inp["argv"][1:]
    m=load(d/"mappings.json")
    assert sha(d/"mappings.json")==row["mapping_receipt"] and m["complete"] and not m["timed_out"]
    assert set(m["expected"])==set(m["captured"])=={"frontend","driver","derive","runtime","client"}
    for k,rec in m["captured"].items():
        assert [rec["device"],rec["inode"]]==m["expected"][k]
    counts=[];started=Counter();ended=Counter();pids=set();types=Counter();signals=[]
    for line in (d/"counter.txt").read_text().splitlines():
        code,pid,t,value=line.split();pids.add(int(pid));types[code]+=1
        if code=="T":started[t]+=1
        if code=="F":ended[t]+=1;counts.append(int(value))
        if code=="S":signals.append(int(value))
    assert len(pids)==1 and {v["pid"] for v in m["captured"].values()}==pids
    assert dict(types)==row["events"] and types["B"]==types["P"]==1 and not types["E"] and all(v==10 for v in signals)
    assert signals==row["signal_values"] and started==ended and all(v==1 for v in started.values())
    assert sum(counts)==row["instructions"] and len(counts)==row["thread_count"] and sha(d/"counter.txt")==row["raw_counter"]
    ar=load(d/"native-archive.json");assert sha(d/"native-archive.json")==row["ordered_archive"]
    assert ar["exact_object_payloads"] and ar["native"]==ar["instruction_counted"] and ar["native_names"]==ar["instruction_counted_names"]
    assert len(ar["native"]["rows"])==row["archive_member_count"]==gold["archive_member_count"]
    assert ar["native"]["symbol_count"]==row["gnu_symbols"] and len(ar["native_names"]["stable_member_names"])==row["archive_member_count"]-2
    identity=(ar["native"],ar["native_names"])
    if (arm,ep) in seen_native:assert seen_native[arm,ep]==identity
    seen_native[arm,ep]=identity
assert len(records)==48 and len(seen_native)==4
calculated=subprocess.check_output([sys.executable,"-B",str(p/"analyze.py"),str(p/"observations.json"),str(p/"plan.json")])
assert json.loads(calculated)==load(p/"statistics.json")
print("Reconstructed 48 complete compiler processes, every per-thread count and mapping, four ordinary archive baselines and both prospective upper bounds.")
