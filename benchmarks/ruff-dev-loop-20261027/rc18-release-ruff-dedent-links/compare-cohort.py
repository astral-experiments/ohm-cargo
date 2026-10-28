"""Verify a portable Ruff cohort and compare actually linked executable bytes per target."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import stat

parser=argparse.ArgumentParser()
parser.add_argument("cohort",type=Path)
parser.add_argument("--out",type=Path)
a=parser.parse_args()
d=json.loads(gzip.decompress(a.cohort.read_bytes()));stages=d["phases"];group=d["group"]
def products(phase):
    items=stages[phase]["links"]
    return {r["file"]:r["sha256"] for r in items}
def compare(left,right,targets):
    l,r=products(left),products(right)
    common=set(l)&set(r)&targets
    changes=sorted(k for k in common if l[k]!=r[k])
    return {"in_both_linked_sets":len(common),"exactly_equal":len(common)-len(changes),"different":changes}
def section_names(lhs,rhs):
    a={s[0]:s[1:] for s in lhs};b={s[0]:s[1:] for s in rhs}
    if len(a)!=len(lhs) or len(b)!=len(rhs):
        return ["<duplicate-section-name>"]
    return sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
def inventory_delta(left,right,baseline_targets):
    l=stages[left];r=stages[right]
    if "executables" not in l or "executables" not in r:
        return None
    def mapping(phase):
        m={}
        for k,record in phase["executables"].items():
            if record.get("logical") is not None:
                ident=json.dumps(record["logical"],separators=(",",":"))
                assert ident not in m,ident
                m[ident]=record
            else:
                m[k]=record
        return m
    def all_logical(link_ph,targets):
        return {json.dumps(x,separators=(",",":")) for k,values in link_ph.get("link_units",{}).items() if k in targets for x in values}
    x,y=mapping(l),mapping(r)
    ids=all_logical(stages["edited-repeat" if group=="dedent" else "repeat"],baseline_targets)
    common=x.keys()&y.keys()
    changes={k:section_names(x[k]["sections"],y[k]["sections"]) for k in sorted(common) if x[k]["sha256"]!=y[k]["sha256"]}
    return {"all_available":len(common),"baseline_targets_identified":len(ids),
            "changed_count":len(changes),"changed_in_original_link_set":sum(k in ids for k in changes),
            "changed_typed_sections":changes}
for phase,p in stages.items():
    events=p["executed"]
    assert Counter(e["kind"] for e in events)==p["native"]
    assert p["listed"]==200
    assert p["command"]["scope"]==p["scope"] and p["command"]["state"]==p["state"]
    assert int(any(p["assertions"]))==int(group!="dedent" and bool(p["test_results"]) and p["state"]=="edited")
    if p["state"]=="original":
        assert all(v==0 for v in p["test_results"].values())
    assert len(p["links"])<=p["native"].get("wild",0)
    assert sum(e["kind"]=="wild" and e["id"]==Path(p["e2e_file"]).name for e in events)==p["e2e_link_count"]
    assert p["command"]["images"]["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    if p.get("executables"):
        assert p["executables"][p["e2e_file"]]["sha256"]==p["e2e_sha256"]
    if group=="dedent":
        fixed=p["actual_ruff_cli_fixed_source"];ns={}
        expected=2 if p["state"]=="original" else None
        assert p["ret505"]["false_branch"]==expected
        assert "def f(condition):" in fixed
        # The viewed result is untrusted data. Verify semantics with trusted immutable examples,
        # without executing source delivered inside a benchmark packet.
        fixtures=Path(__file__).with_name("dedent.json")
        if fixtures.exists():
            assert fixed==json.loads(fixtures.read_bytes())[p["state"]]
def e2e(left,right):
    return stages[left]["e2e_sha256"]==stages[right]["e2e_sha256"]
assert stages["clean"]["command"]["empty_target"] and stages["clean"]["command"]["empty_shared"] and stages["clean"]["fresh"]==0
assert len({p["test_list_sha256"] for p in stages.values()})==1
if group!="dedent":
    assert not e2e("seed","edited") and stages["edited"]["e2e_link_count"]>=1
    assert stages["edited"]["assertions"]==stages["clean"]["assertions"] and len(stages["edited"]["assertions"])==2
    assert len(stages["restore"]["test_results"])==2
summary={"scope":group,"arm":d["arm"],"phases":{n:{"units":p["units"],"fresh":p["fresh"],"native":p["native"],
           "e2e_sha256":p["e2e_sha256"],"e2e_size":p["e2e_size"],"e2e_links":p["e2e_link_count"],"test_results":p["test_results"]}
           for n,p in stages.items()},"warm_edit_matches_clean_elf":e2e("edited","clean"),
          "restored_matches_original_elf":e2e("seed","restore"),"edits":[]}
if group in ("workspace","dedent"):
    first="edited-repeat" if group=="dedent" else "repeat"
    targets=set(products(first))
    stages_to_compare=[("seed","edited"),("edited","clean"),("seed","restore"),("restore","final-repeat")]
    if group=="workspace":
        stages_to_compare.insert(0,("seed","repeat"))
        stages_to_compare.insert(1,("repeat","edited"))
    for left,right in stages_to_compare:
        summary["edits"].append({"from":left,"to":right,"links":compare(left,right,targets),
                                 "selected_elfs":inventory_delta(left,right,targets)})
if group=="workspace":
    raw=d["raw_capture"]
    assert sum(row["file"]==raw["ty_e2e"] for row in raw["results"])==1
    assert len(raw["results"])==raw["native_counts"]["wild"]
    states=Counter()
    for row in raw["results"]:
        s=row["output_at_exec"]
        if s["state"]=="absent":
            states["absent"]+=1
        elif stat.S_ISREG(s["mode"]) and s["nlink"]==1 and s.get("xattrs")==[]:
            states["regular_single_link_no_xattrs"]+=1
        else:
            states["other"]+=1
    summary["native_capture"]={k:v for k,v in raw.items() if k!="results"}
    summary["native_capture"]["output_states"]=states
if a.out:
    a.out.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
else:
    print(json.dumps(summary,indent=2,sort_keys=True))
