from pathlib import Path
from collections import Counter
import hashlib
import json

root=Path(__file__).resolve().parent
load=lambda n:json.loads((root/n).read_bytes())
old=load("workflow-manifest.json")
candidate=load("corrected-manifest.json")
fixed={"cargo":"34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31","rust":"5e3de497d41f4d4fa98fce3082ea43076779de5d"}
assert {k:old["sources"][k]["revision"] for k in fixed}=={"cargo":"235f9228651b74c591e6f62cae4c9b761448dd2d","rust":"eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53"}
for k,v in fixed.items():
    old["sources"][k]["revision"]=v
assert old==candidate
assert candidate["bundled_tools"]["wild"]=={"version":"0.11.0","sha256":"25012a78de164686f552b7703b5d0223adab4829c79cd1fb351108221d61c7d8"}
checks=load("hosted-checks.json")
for name,n in [("cargo-279",8),("cargo-280",8),("rust-254",3)]:
    entries=checks[name]["checks"]
    assert all(x["status"]=="COMPLETED" for x in entries)
    assert Counter(x["conclusion"] for x in entries)==({"SUCCESS":8,"SKIPPED":1} if n==8 else {"SUCCESS":3})
    assert checks[name]["head"]=={"cargo-279":"b3360c5eda186845b9a2ba6e5330a97c07d4acf2","cargo-280":fixed["cargo"],"rust-254":fixed["rust"]}[name]
t=load("authentic-cargo.json")
assert t["source"]==fixed["cargo"] and fixed["cargo"] in t["version"]
assert t["nonproduct_externs"]==239 and t["native_input_counts"]["independent_literal_linker_files"]==335
assert t["binary"]==t["files"]["cargo"]=="a9c1b18bbb02f541bcf089db9d4286c215ffc8036fa1ff443e59c9210e77771c"
run=load("run-at-audit.json")["defaultBranchRef"]["target"]
assert run["oid"]=="6d094beb0c256ca5ee9e2038cebeb023203f3b0a" and run["checkSuites"]["nodes"][0]["workflowRun"]["databaseId"]==40821545374
if (root/"SHA256SUMS").exists():
    for line in (root/"SHA256SUMS").read_text().splitlines():
        h,n=line.split("  ",1)
        assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h
print("Verified the affected workflow and corrected source pair, hosted checks, authentic release-PGO Cargo and unchanged linker.")
