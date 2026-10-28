"""Separate equal current explicit operands from current, process-local lookup and output evidence."""
from pathlib import Path
import json
import sys
root=Path.home()/".cache/ohm-18-ty-e2e-link-20261028"
old,new,label=sys.argv[1:]
def load_truth(name):
    folder=root/"reports"/name
    report=json.loads((folder/"result.json").read_bytes())
    union=json.loads((folder/"physical-inputs-private.json").read_bytes())
    result={}
    for row in report["results"]:
        q=json.loads((folder/"actual"/(str(row["pid"])+".json")).read_bytes())
        name=Path(q["out"]).relative_to(root).as_posix();assert name not in result
        transient=q["transient"]
        raw,=q["directories"]
        volatile={transient["symbols"]["path"]:"<symbols.o>","-plugin-opt=-fresolution="+transient["gcc-resolution"]["path"]:"<resolution>",
                  "-L"+raw:"<raw-dylibs>"}
        assert len(set(volatile)&set(q["argv"]))==3
        argv=[volatile.get(arg,arg) for arg in q["argv"]]
        explicit={p:union[p]["sha256"] for p in q["persistent_operands"]}
        result[name]={"argv":argv,"literal":q["argv"],"explicit":explicit,"raw":q["directories"][raw],
                      "symbols":transient["symbols"]["sha256"],"res":transient["gcc-resolution"]["sha256"],
                      "elf":row["sha256"],"role":row["scope"],"ty_e2e":row["file"]==report["ty_e2e"]}
    return result
a,b=load_truth(old),load_truth(new)
rows=[]
for k in sorted(a.keys()&b.keys()):
    x,y=a[k],b[k];same=x["explicit"].keys()&y["explicit"].keys()
    changed=sorted(Path(p).name for p in same if x["explicit"][p]!=y["explicit"][p])
    normalized_argv_equal=x["argv"]==y["argv"]
    roles_equal=all(x[s]==y[s] for s in ("raw","symbols","res"))
    delta=len(x["explicit"].keys()^y["explicit"].keys())
    observed=normalized_argv_equal and roles_equal and not changed and delta==0
    rows.append({"target":k,"e2e":x["ty_e2e"],"inputs_removed_or_added":delta,"changed_explicit_file_names":changed,
                 "normalized_argv_equal":normalized_argv_equal,"temporary_role_contents_equal":roles_equal,
                 "literal_arg_differences":sum(v!=w for v,w in zip(x["literal"],y["literal"])) if len(x["literal"])==len(y["literal"]) else None,
                 "all_observed_explicit_inputs_equal":observed,"actual_elf_equal":x["elf"]==y["elf"],"explicit_count":len(same)})
result={"old":old,"new":new,"old_native":len(a),"new_native":len(b),"shared_targets":len(rows),
        "with_same_observed_explicit_inputs":sum(r["all_observed_explicit_inputs_equal"] for r in rows),
        "with_equal_elf":sum(r["actual_elf_equal"] for r in rows),
        "same_observed_explicit_inputs_but_different_elf":sum(r["all_observed_explicit_inputs_equal"] and not r["actual_elf_equal"] for r in rows),
        "results":rows}
out=root/"reports"/label;out.mkdir()
(out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps({k:v for k,v in result.items() if k!="results"}))
