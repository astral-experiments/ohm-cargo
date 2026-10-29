"""Export the native build and test-build series from qualified Cargo's per-command logs."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,sys
def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def project(root):
    subject=json.loads((root/"ops/subject.json").read_bytes())
    meta=json.loads((root/"reports/prepare/metadata.json").read_bytes())
    ws={p["name"] for p in meta["packages"] if p["id"] in meta["workspace_members"]}
    result={"source":{"old":subject["parent"],"new":subject["commit"],"lock":subject["lock_sha256"]},
            "workspace":sorted(ws),"all_default":set(meta["workspace_default_members"])==set(meta["workspace_members"]),
            "images":{k:v["sha256"] for k,v in json.loads((root/"reports/qualified-rc19/images.json").read_bytes())["images"].items()},"commands":{}}
    for mode in ("build","test"):
        series=result["commands"][mode]={}
        zone=root/"reports"/("qualified-native-"+mode)
        for tag in ("unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2","child-edit","child-unchanged-1","child-unchanged-2"):
            d=zone/tag
            report=json.loads((d/"summary.json").read_bytes())
            trace=json.loads((d/"native.json").read_bytes())
            rows=[json.loads(line) for line in (d/"cargo.jsonl").read_bytes().splitlines()]
            assert rows[-1]=={"reason":"build-finished","success":True}
            assert trace["root_exit"]==0 and set(trace["process_exit"].values())=={0}
            native=[]
            for x in trace["events"]:
                entry={k:x[k] for k in ("role","target","argv_sha256")}
                entry["out"]=Path(x["out"]).name if x["out"] else None
                if x["role"].startswith("rustc"):
                    a=x["argv"]
                    entry["crate_types"]=[a[i+1] for i,y in enumerate(a[:-1]) if y=="--crate-type"]
                    entry["emit"]=[y.removeprefix("--emit=") for y in a if y.startswith("--emit=")]
                    entry["test_harness"]="--test" in a
                native.append(entry)
            typed=[]
            for a in rows:
                if a["reason"]!="compiler-artifact":continue
                t=a["target"]; manifest=Path(a["manifest_path"]); package=manifest.parent.name
                own=manifest.parent.parent.name=="crates" and package in ws
                typed.append({"package":package if own else a["package_id"].rsplit("#",1)[-1],"workspace":own,
                    "target":t["name"],"kind":t["kind"],"tested":t["test"],"doctest":t["doctest"],"profile_test":a["profile"]["test"],
                    "fresh":a["fresh"],"outputs":[Path(p).name for p in a["filenames"]],
                    "executable":Path(a["executable"]).name if a["executable"] else None})
            assert len(typed)==report["typed_units"] and sum(not a["fresh"] for a in typed)==report["dirty"]
            assert Counter(n["role"] for n in native)==report["roles"]
            reader=report["reader"]
            if mode=="test":
                reader=dict(reader,e2e_names=(d/"e2e-test-list").read_text().splitlines(keepends=True))
            else:
                for key in ("valid","dirty"):
                    diagnostics=json.loads((d/(key+".stdout")).read_bytes())
                    assert [(x["code"],x["location"]) for x in diagnostics]==[tuple(x) for x in next(y[2] for y in reader["ruff"] if y[0]==key)]
            series[tag]={"source":report["source"],"git_admin_unchanged":not report["gitdir_changed"],
                         "typed":typed,"native":native,"reader":reader,
                         "original_log_sha256":{n:sha(d/n) for n in ("cargo.jsonl","stderr","native.json","summary.json","status.json")}}
    return result
if __name__=="__main__":
    out=project(Path(sys.argv[1]))
    dst=Path(sys.argv[2])/"observations.json.gz"
    data=json.dumps(out,sort_keys=True,separators=(",",":")).encode()
    with dst.open("xb") as f:
        f.write(gzip.compress(data,compresslevel=9,mtime=0))
