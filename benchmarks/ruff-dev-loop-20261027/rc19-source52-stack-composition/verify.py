"""Check the independent Git readback against the tested merge and the native observations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
read=lambda name:json.loads((root/name).read_bytes())
snap=read("branches/branch-snapshot.json")
rows=read("branches/direct-children.json")
resolved=read("branches/resolved52.json")
native=read("native/source.json")
assert snap["open_pr_count"]==150 and len(snap["refs"])==15
old=[r for r in rows if r["scope"]=="unchanged-parent"]
proposed=[r for r in rows if r["scope"]=="proposed-parent"]
both=[r for r in rows if r["scope"]=="both-proposed"]
assert len(old)==len(proposed)==8 and len(both)==1 and all(r["clean"] for r in old)
for row in old+proposed:
    a,b=[snap["refs"][str(row[k])] for k in ("parent_pr","child_pr")]
    assert (a["head_repo"],a["head"])==(b["base_repo"],b["base"])
    assert row["child"]==b["head_sha"]
    if row["scope"]=="unchanged-parent":assert row["base"]==a["head_sha"]
conflict,=[r for r in proposed if not r["clean"]]
assert (conflict["parent_pr"],conflict["child_pr"])==(53,52)
assert conflict["conflicts"]==["src/compiler/fingerprint/mod.rs"]
assert (both[0]["parent_pr"],both[0]["child_pr"],both[0]["clean"],both[0]["ancestor"])==(101,103,True,True)
assert resolved["parents"]==[conflict["child"],conflict["base"]]==native["parents"]
assert resolved["proposed_52"]==native["fixed"]=="756f52243de60b645e132d5aca95944cca5ce030"
assert resolved["tree"]==native["tree"]=="903c2baf771803bf449357f7a369085ede89bcc0"
assert len(resolved["child_deltas"])==3
assert all(x["before"]==x["after"] and x["lines"][0]==x["lines"][1] for x in resolved["child_deltas"].values())
assert sum(x["lines"][0] for x in resolved["child_deltas"].values())==438
assert resolved["next_merges"].keys()=={"current-51","proposed-51"} and all(x["clean"] for x in resolved["next_merges"].values())
assert hashlib.sha256((root/"native/merge-versus-original-52.patch").read_bytes()).hexdigest()==resolved["patch_from_published_52"]
assert hashlib.sha256((root/"native/SHA256SUMS").read_bytes()).hexdigest()=="73cafbfa9990be1bf12449ec1719756e32bcbd4d2d3c7717e288e1e86f506fc2"
subprocess.run([sys.executable,"-IB","verify.py"],cwd=root/"native",check=True)
print("Verified all eight direct children, the resolved #52 source delta, both #51 merge trees and the native results.")
