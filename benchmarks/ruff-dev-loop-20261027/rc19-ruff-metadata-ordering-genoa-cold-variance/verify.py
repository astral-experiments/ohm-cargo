"""Check the release identities, all cold products, credentials and reader verdicts."""
import collections,gzip,hashlib,json,re
from pathlib import Path

base=Path(__file__).resolve().parent
def load(n):return json.loads((base/n).read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lines=(base/"SHA256SUMS").read_text().splitlines()
for line in lines:
    digest,name=line.split("  ",1)
    assert sha(base/name)==digest
assert set(n.split("  ",1)[1] for n in lines)=={p.name for p in base.iterdir() if p.is_file() and p.name!="SHA256SUMS"}
history=load("four-empty-builds.json")
for k,row in history.items():
    assert row["typed_units"]==row["typed_dirty"]==510
    assert row["settled_rustcs"]==[["ty_python_semantic"],["ty_python_semantic"]]
    assert row["lock"]=="34e5c62a1d7c45679fc0113e8a8814452e67d9969dd1079adb234bd7803ddc6d" and row["source"]=="2d6ce561250a464e1fa231ef30e54d0f029f76a4"
assert len({r["output_roster"] for r in history.values()})==1 and len({r["typed_complete_roster"] for r in history.values()})==1
assert history["A1"]["metadata"]!=history["A2"]["metadata"]==history["B1"]["metadata"]==history["B2"]["metadata"]
assert history["A1"]["actual_cargo"]==history["A2"]["actual_cargo"]!=history["B1"]["actual_cargo"]==history["B2"]["actual_cargo"]
files=json.loads(gzip.decompress((base/"products.json.gz").read_bytes()))
assert len(files["A"])==597 and files["A"].keys()==files["B"].keys()
changed={p for p in files["A"] if files["A"][p]!=files["B"][p]}
assert collections.Counter(Path(p).suffix for p in changed)=={".rmeta":37,".so":1,".rlib":3}
hs=load("changed-credentials.json")
image=next(p for p in changed if p.endswith(".so"))
assert hs[image]["changed_dependencies"]=={"A":[],"B":[]} and hs[image]["A"]["private"]!=hs[image]["B"]["private"]
assert hs[image]["A"]["stable"]==hs[image]["B"]["stable"]=="208556596896080507"
for name in ("libruff_python_ast-","libruff_python_index-"):
    p=next(p for p in hs if Path(p).name.startswith(name))
    assert all(any("get_size_derive2" in dep for dep in hs[p]["changed_dependencies"][k]) for k in "AB")
macro=load("native-macro.json");assert macro["differing_sections"][".text"]["different"]==755
for arm in "AB":
    assert macro["ELF"][arm]["sha256"]==files[arm][image]["sha256"]==macro["observed"][arm]["image"]
    assert macro["observed"][arm]["status"]==1 and macro["observed"][arm]["source"]==sha(base/"clash.rs")
    assert len(macro["conflict_strings"][arm])==6
assert [m["message"] for m in macro["conflict_strings"]["A"]]!=[m["message"] for m in macro["conflict_strings"]["B"]]
assert macro["observed"]["A"]["diagnostics"]==["`size` conflicts with mutually exclusive `size_fn`"]
assert macro["observed"]["B"]["diagnostics"]==["`ignore` conflicts with mutually exclusive `size_fn`"]
s=load("source-proof.json")
for k in ("attribute-derive-macro","get-size-derive2"):assert s[k]["excerpt_sha256"]==sha(base/(k+"-excerpt.txt"))
print("Verified four genuine empty Ruff builds, 597 literal outputs, 41 differing bytestrings, both macro credentials and both native caller diagnostics.")
