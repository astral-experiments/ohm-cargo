"""Check the recorded function positions, compiler inputs, native diagnostics, and wire controls."""
import hashlib
import json
from pathlib import Path
import tarfile

here = Path(__file__).resolve().parent
archive = here/"wire-and-frontend-evidence.tar.gz"
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(archive.read_bytes()) == "60db25585294697d4abd5e2daec8bbecf35c697412cc9c36cd308d2cb3c8464b"
with tarfile.open(archive) as t:
    files = {m.name.removeprefix("./"):t.extractfile(m).read() for m in t if m.isfile()}
assert len(files)==75
assert json.loads(files.pop("SHA256.json")) == {k:sha(v) for k,v in files.items()}
read = lambda name: json.loads(files[name+".json"])
assert read("focused-233/subjects")["driver"]=="dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"
source = read("focused-233/source")
assert source["head"]=="93526150df078af7dd8fc4226cdcc469539d2001" and source["patch"]=="523d83c941cbae9b7c8a10739c839a8eeda3245d"
nbytes, nlines = source["raw_deleted_bytes"],source["raw_deleted_newlines"]
assert (nbytes,nlines)==(323,11)
v=read("focused-233/results")
assert all(v[k]["hash"]==v["original"]["hash"] for k in ("markdown-only","geometry-fixed","body-only","restored"))
assert len({v[k]["hash"] for k in ("original","historical","line-only","byte-only")})==4
assert len({x["global"] for x in v.values()})==1 and not v["markdown-only"]["dirty"]
items=read("focused-233/item-changes")
assert items["global_equal"] and len(items["changed_definitions"])==10 and items["retained_definition_count"]==429
assert "ruff_python_stdlib::typing::is_mutable_return_type" not in items["changed_definitions"]
a,b,c=read("foreign-diagnostics/receipt")
assert all(x["caller_error"]=="E0061" for x in (a,b,c)) and a["producer_spans"]==c["producer_spans"]
for [old],[new] in zip(a["producer_spans"],b["producer_spans"],strict=True):
    assert [pos-nbytes for pos in old["bytes"]]==new["bytes"]
    assert [line-nlines for line in old["lines"]]==new["lines"]
    assert old["text"]==new["text"] and old["cols"]==new["cols"]
rec=read("private-deprecation/graph-facts")["uses_moved"]["direct_children"]
meta, cgu = [next(v for k,v in rec.items() if k.startswith(key+":")) for key in ("Metadata","CompileCodegenUnit")]
assert meta["total_children"]==227 and {x[0] for x in meta["red_or_missing_children"]}=={"public_api_hash","crate_hash"}
assert cgu["total_children"]==51 and not cgu["red_or_missing_children"]
wire=read("wire-rebind-facts")
assert all(r["matches"] == (r["current_sha"]==r["rebound_sha"]) for fam in wire.values() for r in fam.values())
assert [sum(r["matches"] for r in wire[k].values()) for k in ("incremental-graph-bridges","private-refs-byteexact","private-deprecation")]==[2,4,2]
diag=read("private-deprecation/diagnostic-evidence")
assert not diag["initial"] and diag["updated"][0][1]=="warning" and diag["denied"][0][1]=="error" and diag["deny_returncode"]==101
for r in read("incremental-graph-bridges/callers"):
    stale=r["tag"]=="old-bridge-new-producer"
    assert r["ok"] != stale and r["errors"]==(["E0460"] if stale else [])
for case in ("warn","deny"):
    r=read("mixed/"+case+"/upstream-deprecation")
    assert r["original_leaf"]!=r["changed_leaf"]
    warm,clean=r["warm"],r["clean"]
    assert warm["diagnostics"]==clean["diagnostics"] and warm["diagnostics"]
    assert warm["bundle_rustc"]==clean["bundle_rustc"]==1 and not warm["checked_option"]
    if case=="warn":
        assert warm["ELF"]==clean["ELF"] and warm["diagnostics"][0]["code"]=="deprecated"
    else:
        assert warm["returncode"]==clean["returncode"]==101
ident=read("mixed/prior-fifo-safe/identity")
assert ident["cargo"]=="dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1"
rs={r["phase"]:r for r in read("mixed/prior-fifo-safe/results")}
assert all(not r["checked_option"] for r in rs.values())
assert rs["clean"]["ELF"]==rs["edited-again"]["ELF"] and not rs["fresh"]["dirty"]
print("Verified 74 payloads, three diagnostic positions, direct incremental inputs, stale callers and both upstream deprecation controls.")
