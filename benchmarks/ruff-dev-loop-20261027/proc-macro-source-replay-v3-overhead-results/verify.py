from pathlib import Path
import hashlib,json,subprocess,sys

p=Path(__file__).resolve().parent;d=p/"heldout"
def load(q):return json.loads(q.read_bytes())
def sha(q):return hashlib.sha256(q.read_bytes()).hexdigest()
mf={k:v for line in (p/"SHA256SUMS").read_text().splitlines() for v,k in [line.split("  ",1)]}
assert set(mf)=={x.relative_to(p).as_posix() for x in p.rglob("*") if x.is_file() and x.name!="SHA256SUMS"} and all(sha(p/k)==v for k,v in mf.items())
plan=load(p/"parser-overhead-v3-plan.json");assert sha(p/"parser-overhead-v3-plan.json")=="e2597bf5456850cce0e95302ad1e341c258fd93b9d64c02fa8b45e3cfce9a680" and sha(p/"parser-overhead-v3.py")==plan["runner_sha256"]
cert=load(p/"admission.json");complete=load(d/"complete.json")
assert complete["certificate"]==sha(p/"admission.json")=="84092c13895343d85bb7417ee44a7f3a5bf937e11cc91896e5ebff013c825fb6" and complete["observations"]==sha(d/"observations.json")
rr=load(d/"observations.json");assert len(rr)==64
for row in rr:
    a=row["arm"];e=row["endpoint"];sub=d/f"{row['pair']:02}-{e}-{a}";x=load(sub/"result.json");assert x=={k:v for k,v in row.items() if k not in {"pair","endpoint"}}
    c=x["child"];ref=cert["oracles"][a][e]
    assert x["rmeta_sha256"]==x["archive_rmeta_sha256"]==ref["rmeta_sha256"] and x["header"]==ref["header"]
    assert c==load(sub/"child.json") and c["exit"]==0 and c["wall_ns"]>0 and c["affinity"]==list(range(24))
    assert x["actual_driver_sha256"]==plan["arms"][a]["driver_sha256"] and x["archive_member_count"]==ref["archive_member_count"]
    assert (sub/"metadata.root").is_file() and len(x["rlib_sha256"])==64
aud=load(d/"physical-audits.json");assert len(aud)==8
for k,v in aud.items():
    x=load(d/k/"result.json");assert x["native_audit_sha256"]==v["raw_trace_sha256"] and x["child"]["wall_ns"] is None
    ev=v["successful_exec_and_key_opens"];assert any(e.get("exec","").endswith("/rustup/toolchains/ohm/bin/rustc") for e in ev)
    assert any("librustc_driver" in e.get("opened","") for e in ev) and any("libget_size_derive2" in e.get("opened","") for e in ev)
actual=json.loads(subprocess.check_output([sys.executable,"-B",str(p/"analyze-parser-overhead.py"),str(d/"observations.json"),str(p/"parser-overhead-v3-plan.json")]))
assert actual==load(d/"stats.json")
assert actual["pass_both"] is False and actual["results"]["empty"]["noninferiority"] is False and actual["results"]["retained"]["noninferiority"] is True
assert json.loads(subprocess.check_output([sys.executable,"-B",str(p/"order.py")]))==load(p/"order.json")
print("64 uninstrumented native observations, 8 independent tool/metadata gates, 2 endpoint statistics and order diagnostics verified. The joint 3% noninferiority criterion failed.")
