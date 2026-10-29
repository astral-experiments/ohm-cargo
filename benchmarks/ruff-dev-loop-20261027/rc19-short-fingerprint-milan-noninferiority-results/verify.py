"""Check the complete Milan study from its portable records and re-run the fixed analysis."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import subprocess
import sys

root=Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def encoded(value): return json.dumps(value,sort_keys=True,separators=(",",":"))
def load(name):
    f=root/name; return json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())
manifest={line.split("  ",1)[1]:line.split("  ",1)[0] for line in (root/"SHA256SUMS").read_text().splitlines()}
assert set(manifest)=={f.name for f in root.iterdir() if f.is_file() and f.name!="SHA256SUMS"}
assert all(sha(root/file)==value for file,value in manifest.items())
assert manifest["order.json"]=="d1bcc2316ff6d46d230f009b6cd1e6fa6b1bb3a43066cd881a1c4d396f778337" and manifest["analysis.py"]=="5577d4150ba16ade8c9998bfd635ab2c3e71cdc965cfd9c9906185e16a72c03f"
assert load("order.json")==json.loads(subprocess.check_output([sys.executable,"-IB",root/"analysis.py"]))
subjects=load("subjects.json");p=load("literal-products.json.gz");visits=load("visits.json.gz");typed=load("typed-rosters.json.gz");descs=load("unit-descriptions.json.gz")
qual=load("qualification.json.gz");grant=load("release-grant.json");rows=load("observations.json");result=load("analysis.json")
assert subjects["images"]["B"]["binary"]=="51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9" and subjects["images"]["E"]["binary"]=="ce5b3031dcd3f31098fd9b16147b4c286dc640e1757e5362c9e1e4f05ec88cb3"
assert subjects["images"]["B"]["profile"]==subjects["images"]["E"]["profile"] and subjects["images"]["B"]["stamp"]==subjects["images"]["E"]["stamp"]
assert grant["go"] and grant["pairs"]==32 and grant["replacements"]==0 and grant["manifest"]=="d33916e8611d1365fb992eec89a94f2c4475e632efec5169e411769e89100911"
assert grant["published_commit"]=="19ef923d07c6e71e2af6080bdc29e46ca7ee444f" and manifest["raw-qualification-terminal.json"]==grant["qualification"]
for k,v in p.items():
    assert len(v)==597 and hashlib.sha256((json.dumps(v,indent=2,sort_keys=True)+"\n").encode()).hexdigest()==subjects["sources"][k]["products597"]
different=load("between-source-cohorts.json");both=set(p["parent"])&set(p["child"]);assert different=={
    "both":len(both),"same_bytes":sum(p["parent"][n]==p["child"][n] for n in both),
    "changed_at_same_name":{n:[p["parent"][n],p["child"][n]] for n in both if p["parent"][n]!=p["child"][n]},
    "only_in_parent":sorted(set(p["parent"])-both),"only_in_child":sorted(set(p["child"])-both)}
for key,rv in typed.items():
    assert hashlib.sha256(encoded(rv).encode()).hexdigest()==key and len(rv)==510 and sum(not fresh for sig,fresh in rv)==12 and all(sig in descs for sig,fresh in rv)
for key,d in descs.items():
    assert key==hashlib.sha256(encoded([d[0],d[-1]]).encode()).hexdigest()
def occupant(r,a,k):
    assert r["start_products_sha256"]==manifest[k+"-full-checked-ledger.json.gz"] and load(k+"-full-checked-ledger.json.gz")=={"files":p[k],"different":{}}
    assert r["affinity"]==list(range(8)) and r["uid_map"]==["0","0","4294967295"] and r["cargo_sha256"]==subjects["images"][a]["binary"]
    owners=r["owner_roles"]; assert owners["root"][0]==owners["home"][0]==0 and all(owners[n][0]==r["uid"]!=0 for n in ("work","cargo_home","state"))
    assert not set(r["environment_keys"]) & {"CARGO_LOG","RUSTFLAGS","RUSTC","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","LD_PRELOAD"}
def ordinary(q,k):
    assert q["raw_products_sha256"]==manifest[k+"-full-checked-ledger.json.gz"]
    assert q["units"]==510 and q["dirty"]==12 and q["status"]==0 and q["source_identity"]==subjects["sources"][k]["identity"]
    assert set(p[k])=={name for sig,_ in typed[q["typed"]] for name in descs[sig][-1]}
syscalls=load("short-file-events.json.gz")
for arm in "BE":
    for k in ("parent","child"):
        f=qual[arm+"-"+k];occupant(f,arm,k)
        for label in ("warmup","native","reads"):ordinary(f[label],k)
        assert Counter(n["role"] for n in f["job_events"])=={"rustc-full":1,"cargo":1}
        assert [n["target"] for n in f["job_events"] if n["role"]=="rustc-full"]==["ty_python_semantic"]
        i=f["fingerprints"];assert i["unique_hex16"]==len(i["files"]) and all(sum(v.get(key,0) for v in i["files"].values())==value for key,value in i["counts"].items())
        sc=syscalls[arm+"-"+k]; assert sc["raw_source"]==i["raw_sha256"] and sc["all_reader_threads_join_to_cargo"]
        cells={n:Counter() for n in i["files"]}
        for row in sc["events"]:
            if row[2]=="open": cells[row[1]]["opens"]+=1
            else:
                pid,name,request,got,payload=row;cells[name][f"read_{request}_returned_{got}"]+=1
                if payload is not None:
                    assert len(payload)==16 and int(payload,16)>=0 and got==16
                    cells[name]["exact_hex16"]+=1
        assert {n:dict(v) for n,v in cells.items()}==i["files"]
        if arm=="E": assert i["counts"]["read_16_returned_16"]>0 and i["counts"]["read_1_returned_0"]>0
    e=qual[arm+"-real-error"];occupant(e,arm,"child");ordinary(e["warmup"],"child")
    assert e["real-private-error"]["status"]==e["unchanged-error"]["status"]==101 and e["real-private-error"]["errors"]==e["unchanged-error"]["errors"]==qual["B-real-error"]["real-private-error"]["errors"]
    assert all(r[1]=="E0624" and "is_triple_quoted_string" in r[2] for r in e["real-private-error"]["errors"]) and e["recovered"]["status"]==0 and e["recovered"]["errors"]==[]
assert len(rows)==32 and len(visits)==64
for row in rows:
    for slot,arm in enumerate(row["order"]):
        q=visits[2*row["pair"]+slot];k=row["source"]
        assert q["position"]==slot and q["arm"]==arm and q["pair"]==row["pair"] and q["source"]==k
        occupant(q,arm,k);ordinary(q["warmup"],k);ordinary(q["check"],k)
        w=q["clock"];assert w["after_ns"]-w["before_ns"]==w["wall_ns"]==row["wall_ns"][arm] and w["status"]==0
assert result==json.loads(subprocess.check_output([sys.executable,"-IB",root/"analysis.py",root/"observations.json"]))
assert result["noninferior_3pct"]==(result["block_percentile_95"][1]<.03)
print("Verified 32 adjacent balanced pairs, 64 independent timed restores, 128 ordinary commands, two sets of 597 physical products, four native+read controls, and both real diagnostic controls.")
