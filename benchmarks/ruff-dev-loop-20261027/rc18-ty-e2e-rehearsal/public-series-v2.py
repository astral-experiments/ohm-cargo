"""Export a credential-free projection binding Cargo, test, physical linker, and ELF evidence."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import re
import sys

root = Path.home() / ".cache/ohm-18-ty-e2e-link-20261028"
arm, group = sys.argv[1:3]
assert arm in ("rehearsal","release","candidate") and group in ("workspace","focused","dedent")
origin = root / "reports"
stages = ["seed","repeat","edited","clean","restore","final-repeat"]
if group == "dedent":
    stages = ["seed","edited","edited-repeat","clean","restore","final-repeat"]
output = origin / ("public-"+arm+"-"+group)
output.mkdir()
packet = {"arm":arm,"group":group,"phases":{}}
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    return hashlib.file_digest(path.open("rb"),"sha256").hexdigest()
def assertions(err):
    txt=err.read_text()
    result=[]
    if "panicked at crates/ty_server/tests/e2e/notebook.rs:628:9:" in txt:
        assert "expected no hover at Position" in txt and 'value: "Literal[1]"' in txt
        assert 'right: None' in txt
        result.append("notebook.rs:628:9 returned hover for Literal[1] after cell end")
    if "panicked at crates/ty_server/tests/e2e/notebook.rs:657:5:" in txt:
        assert "left: [InlayHint {" in txt and 'value: "int"' in txt and 'right: []' in txt
        result.append("notebook.rs:657:5 returned an int inlay hint after cell end")
    return result
def project(p):
    result=read(p/"result.json")
    assert result["arm"]==arm
    cmd=read(p/"command.json")
    assert cmd["images"]["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    events=read(p/"native.json")
    counts=dict(Counter(e["kind"] for e in events));assert counts==result["native"]
    arts=[json.loads(line) for line in (p/"cargo.stdout").read_bytes().splitlines()]
    assert arts[-1]=={"reason":"build-finished","success":True}
    arts=[r for r in arts if r["reason"]=="compiler-artifact"]
    assert len(arts)==result["units"] and sum(r["fresh"] for r in arts)==result["fresh"]
    links=read(p/"linked-products.json")
    out={k:v for k,v in result.items() if k not in ("traced_seconds","ron_before","ron_after")}
    out["command"]=cmd
    out["links"]=links
    out["executed"]=[{"kind":e["kind"],"id":Path(e["id"]).name,"argv_sha256":e["argv_sha256"]} for e in events]
    out["listed"]=len((p/"list.stdout").read_text().splitlines())
    assert out["test_list_sha256"]==sha(p/"list.stdout") and out["listed"]==200
    out["assertions"]=[x for f in sorted(p.glob("test-*.stderr")) for x in assertions(f)]
    if group!="dedent" and result["state"]=="edited" and out["test_results"]:
        assert len(out["assertions"])==2
    else:
        assert not out["assertions"]
    out["ron"]={side:read(p/(side+"-ron.json")) for side in ("before","after")}
    if (p/"elf-inventory.json").exists():
        inv=read(p/"elf-inventory.json");assert inv["units"]==out["units"]
        out["link_units"]=inv.get("link_units",{})
        out["executables"]={name:{k:v for k,v in item.items() if k!="package"} for name,item in inv["outputs"].items()}
    if (p/"ruff-ret505.json").exists():
        out["ret505"]=read(p/"ruff-ret505.json")
        out["actual_ruff_cli_fixed_source"]=(p/"ruff-ret505.stdout").read_text()
        out["upstream_edit"]=read(p/"upstream-edit.json")
    originals=[p/"result.json",p/"command.json",p/"cargo.stdout",p/"cargo.stderr",p/"native.json",p/"linked-products.json",
              p/"list.stdout",p/"before-ron.json",p/"after-ron.json"]
    originals.extend(sorted(p.glob("test-*.*")))
    if (p/"elf-inventory.json").exists(): originals.append(p/"elf-inventory.json")
    out["private_original_sha256"]={f.name:sha(f) for f in originals}
    return out
for stage in stages:
    packet["phases"][stage]=project(origin/(arm+"-"+group+"-"+stage))
if group=="workspace":
    raw=origin/(arm+"-workspace-raw")/"result.json"
    ro=read(raw)
    packet["raw_capture"]={k:v for k,v in ro.items() if k!="results"}
    packet["raw_capture"]["results"]=[{k:v for k,v in row.items() if k!="pid"} for row in ro["results"]]
    packet["raw_capture"]["private_original_sha256"]=sha(raw)
payload=json.dumps(packet,sort_keys=True,separators=(",",":")).encode()
assert not any(t in payload.lower() for t in (b"artifactory",b"openai.org",b"openai.com",b"github_pat_",b"ghp_",b"authorization: bearer"))
compressed=gzip.compress(payload,compresslevel=8,mtime=0)
assert len(compressed)<7_000_000,len(compressed)
(output/"cohort.json.gz").write_bytes(compressed)
print(json.dumps({"arm":arm,"scope":group,"compressed_bytes":len(compressed),"public_sha256":hashlib.sha256(compressed).hexdigest()}))
