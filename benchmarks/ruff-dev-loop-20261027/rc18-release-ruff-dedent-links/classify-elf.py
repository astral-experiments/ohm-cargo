"""Distinguish exact ELF, executable-code changes and metadata changes within the original 50 links."""
from pathlib import Path
from collections import Counter
import argparse
import gzip
import json

p=argparse.ArgumentParser()
p.add_argument("packet",type=Path)
p.add_argument("--output",type=Path)
args=p.parse_args()
root=json.loads(gzip.decompress(args.packet.read_bytes()))
stages=root["phases"]
first="edited-repeat" if root["group"]=="dedent" else "repeat"
claimed={json.dumps(v,separators=(",",":")) for memberships in stages[first]["link_units"].values() for v in memberships}
def units(phase):
    return {json.dumps(v["logical"],separators=(",",":")):v for v in stages[phase]["executables"].values()}
def compare(left,right):
    x,y=units(left),units(right);assert claimed<=x.keys()&y.keys()
    rows=[]
    for key in sorted(claimed):
        old=x[key];new=y[key]
        a={s[0]:s for s in old["sections"]};b={s[0]:s for s in new["sections"]}
        assert len(a)==len(old['sections']) and len(b)==len(new['sections'])
        observed={n for n in a.keys()|b.keys() if a.get(n)!=b.get(n)}
        payload={n for n in a.keys()&b.keys() if a[n][-1]!=b[n][-1]}
        alloc={n for n in payload if (a[n][2]&2 or b[n][2]&2) and n!=".note.gnu.build-id"}
        code=any((a[n][2]&4 or b[n][2]&4) for n in alloc)
        if old["sha256"]==new["sha256"]:kind="exact"
        elif code:kind="machine-code bytes changed"
        elif alloc:kind="other allocated section bytes changed"
        elif not observed-{".rodata",".note.gnu.build-id"}:kind="rodata header or build ID differs"
        else:kind="other ELF changes, identical allocated bytes except build ID"
        rows.append({"unit":json.loads(key),"kind":kind,"changed_sections":sorted(observed),"changed_allocated_payloads":sorted(alloc)})
    return {"left":left,"right":right,"counts":dict(Counter(r["kind"] for r in rows)),"rows":rows}
pairs=[("seed","edited"),("edited","clean"),("seed","restore"),("restore","final-repeat")]
if "repeat" in stages:pairs=[("seed","repeat"),("repeat","edited")]+pairs
data={"arm":root["arm"],"scope":root["group"],"original_targets_identified":len(claimed),"comparisons":[compare(*v) for v in pairs]}
if args.output:args.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
else:print(json.dumps({(v["left"]+" to "+v["right"]):v["counts"] for v in data["comparisons"]},indent=2))
