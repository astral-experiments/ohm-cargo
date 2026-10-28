"""Offline cross-check of the ordinary builds, native syscalls, cross-release map, and public source survey."""
import gzip
import json
import re
from pathlib import Path

D=Path(__file__).resolve().parent
def read(n):
    p=D/n
    if p.is_file():return json.loads(p.read_bytes())
    return json.loads(gzip.decompress(p.with_suffix(p.suffix+".gz").read_bytes()))
cases={"seed":b"7\n","deny":b"untrusted compile-time inputs\n","macro":b"local procedural-macro outputs require trust at import time\n","depinfo":b"untracked Cargo output path in compiled code\n"}
pub="02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
fixed="a19d515cc301c05ad345ad0d657508905c28a2c900e01963632724cfd3b7289a"
for prefix,arm in [("",pub),("corrected-",fixed)]:
    j=read(prefix+"five-writers.json")
    proc=read(prefix+"processes.json")
    assert j["cargo_sha256"]==arm and j["rustc_sha256"]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
    assert set(j["cases"])==set(cases)|{"script"} and len(j["builds"])==8 and all(b["rc"]==0 for b in j["builds"])
    roles={}
    for b,p in zip(j["builds"],proc,strict=True):
        assert b["name"]==p["name"] and b["trace_sha256"]==p["trace_sha256"]
        roles[b["name"]]=[e["role"]for e in p["all_execs"]]
    for case,entry in j["cases"].items():
        before,after=entry["victim_before"],entry["victim_after"]
        assert (before["mode"]==after["mode"]) and (str(Path(entry["marker"]).parts[0])=="target")
        content=bytes.fromhex(entry["final_marker_hex"])
        if case=="script":assert re.fullmatch(rb"[0-9a-f]{64}\n",content)
        else:assert content==cases[case]
        if arm==pub:
            assert before["inode"]!=after["inode"] and before["hex"]!=after["hex"]==entry["final_marker_hex"] and entry["final_marker_is_link"]
        else:assert before==after and not entry["final_marker_is_link"]
        label=({"script":"actual-script-rerun","depinfo":"post-script-depinfo"}.get(case) or "ordinary-fresh-"+case)
        b=next(b for b in j["builds"]if b["name"]==label)
        if case in ("seed","deny","macro"):
            assert all(f for _,f in b["artifacts"]) and roles[label]==["cargo","cargo"]
        if case in ("depinfo","script"):
            assert roles[label]==["cargo","cargo","build_script_build","rustc-crate"]
        if arm==pub:
            selected=b["relevant_syscalls"]
            v="/victims/"+case+".txt"
            assert any("readlink(" in s and v in s and entry["marker"] in s for s in selected)
            assert any(("renameat(" in s or "rename(" in s) and v+'") = 0' in s for s in selected)
            if case=="depinfo":assert any("symlink(" in s and v in s and entry["marker"] in s for s in selected)
orig=read("five-writers.json");c=read("corrected-five-writers.json")
assert {k:x["final_marker_hex"]for k,x in orig["cases"].items()}=={k:x["final_marker_hex"]for k,x in c["cases"].items()}
reg=read("actual-with-fresh.json")
assert reg["initial"]==reg["after_disabled"] and reg["after_default"]["bytes_hex"]=="370a"
assert reg["runs"][-1]["rc"]==0 and reg["runs"][-1]["artifacts"]==[{"name":"marker_fixture","fresh":True}]
assert reg["marker_inode"]==reg["link_at_end"]["inode"] and reg["link_at_end"]["symlink"]
assert reg["before_same_default"]["inode"]!=reg["after_same_default"]["inode"] and reg["after_same_default"]["bytes_hex"]=="370a"
r=read("user-manifest-result.json");assert [u["cargo"]for u in r]==[pub,fixed]
assert all(u["symlink_retained"] and u["same_link_inode"] and u["rc"]==0 for u in r)
assert r[0]["final_manifest"]==r[1]["final_manifest"] and "../localdep" in r[0]["final_manifest"]
m=read("release-map.json");rs=sorted(m["releases"],key=lambda x:x["published_at"])
assert len(rs)==55 and all(x["cargo"] and x["manifest_sha256"] for x in rs)
first=next(x for x in rs if x["writers"])
assert (first["tag"],first["cargo"])==("ohm-1.98.0-6","bbf4a22e66d6d134b07b5c39bfde2c65c0f8e95f")
assert len([x for x in rs if not x["writers"]])==26 and all(x["writers"] for x in rs[26:])
def policy(x):
    return x["writers"].get("record_worktree_seed_policy",{})
assert next(x["tag"]for x in rs if policy(x).get("direct_writes")==3)=="ohm-1.98.0-8"
assert next(x["tag"]for x in rs if policy(x).get("seed_version")=="7")=="ohm-1.98.0-10"
assert [x["cargo"]for x in rs[-2:]]==["a0c7d08c898d3fdff992f2f431dec57d2486add2","7caf39914da1e28a67744ecbc963a5f26361474d"]
for x in rs:
    f={k:v for p,oid in m["source_path_blobs"][x["cargo"]].items()for k,v in m["writer_blobs"][oid].items()}
    assert f==x["writers"]
one,two=[read(n+"branch-audit.json")for n in ("","legacy-")]
assert one["branches"]==two["branches"] and one["pull_requests"]==two["pull_requests"]
assert len(one["branches"])==282 and len(one["pull_requests"])==227 and len(one["head_blobs"])==286
seen=[]
for sha in one["head_blobs"]:
    for s in (one,two):
        roles=[s["blob_details"].get(s["head_blobs"][sha][path])for path in s["paths"]]
        if roles[0]:
            assert len(roles)==4 and all(roles) and roles[0]["marker_write_count"] in (2,3)
            assert roles[1]["marker_write_count"]==roles[2]["marker_write_count"]==1 and roles[3]["direct_final_readlink"]
            seen.append(sha)
assert len(seen)==len(set(seen))==169
print("PASS: 16 ordinary builds on original/fixed, all five original victim overwrites and corrected regular markers, independent physical exec/rename evidence, disabled-seeds and user-manifest controls, 55 release manifests, 286 live branch/PR heads.")
i=read("release17-stage.json");s17=read("released17.json")
assert i["source_sha256"]=="163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572" and i["bytes"]==359683716
assert (s17["cargo"],s17["rustc"],s17["driver"])==(i["cargo"],i["rustc"],i["driver"])
assert s17["release"]==17 and len(s17["runs"])==4 and all(b["rc"]==0 for b in s17["runs"])
b=s17["runs"][-1]
assert b["fresh"] and b["execs"]==["cargo","cargo"] and s17["victim_after"]=="370a" and s17["victim_before"]!=s17["victim_after"]
assert s17["final_is_link"] and s17["inode_before"]!=s17["inode_after"]
assert any("readlink(" in c and "victims/owned.txt" in c for c in b["relevant_syscalls"])
assert any("renameat(" in c and "victims/owned.txt" in c for c in b["relevant_syscalls"])
assert read("first-17-bootstrap.json")["marker_observations"]==0
print("PASS: verified published -17 archive and all three image hashes, four real Cargo builds including a fresh zero-compiler/zero-link overwrite.")
