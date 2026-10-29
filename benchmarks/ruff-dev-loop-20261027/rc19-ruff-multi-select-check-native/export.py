"""Project original Cargo JSON, native Linux exec receipts, and the fingerprint log into a portable file."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,re,sys
def sha(p):
 with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def projection(root):
 releases={"shipped18":root/"reports/passive-edit-replay","qualified19":root/"reports/qualified-rc19"}
 names=["unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2","child-edit","child-unchanged-1","child-unchanged-2"]
 subject=json.loads((root/"ops/subject.json").read_bytes()); out={"subject":{"old":subject["parent"],"new":subject["commit"],"lock":subject["lock_sha256"]},"tools":{},"series":{}}
 meta=json.loads((root/"reports/prepare/metadata.json").read_bytes()); ws={p["name"] for p in meta["packages"] if p["id"] in meta["workspace_members"]}
 out["workspace"]=sorted(ws);out["defaults_all"]=set(meta["workspace_members"])==set(meta["workspace_default_members"])
 for rev,d in releases.items():
  images=json.loads(((root/"reports/images.json") if rev=="shipped18" else (d/"images.json")).read_bytes())["images"]
  out["tools"][rev]={k:v["sha256"] for k,v in images.items()};out["series"][rev]={}
  for label in names:
   zone=d/label;summary=json.loads((zone/"summary.json").read_bytes());raw=json.loads((zone/"native.json").read_bytes())
   cargo=[json.loads(b) for b in (zone/"cargo.jsonl").read_bytes().splitlines()]
   assert raw["root_exit"]==0 and set(raw["process_exit"].values())=={0} and cargo[-1]=={"reason":"build-finished","success":True}
   native=[]
   for x in raw["events"]:
    evt={k:x[k] for k in ("role","argv_sha256","target")};evt["out"]=Path(x["out"]).name if x["out"] else None
    if x["role"].startswith("rustc"):
     a=x["argv"];evt["crate_types"]=[a[j+1] for j,y in enumerate(a[:-1]) if y=="--crate-type"]
     evt["emit"]=[y.removeprefix("--emit=") for y in a if y.startswith("--emit=")];evt["test_harness"]="--test" in a
    native.append(evt)
   artifacts=[]
   for row in cargo:
    if row["reason"]!="compiler-artifact":continue
    t=row["target"];source=Path(row["manifest_path"]);name=source.parent.name
    artifacts.append({"package":name if source.parent.parent.name=="crates" and name in ws else row["package_id"].rsplit("#",1)[-1],
      "workspace":source.parent.parent.name=="crates" and name in ws,"target":t["name"],"kind":t["kind"],"tested":t["test"],"doctest":t["doctest"],
      "profile_test":row["profile"]["test"],"fresh":row["fresh"],"outputs":[Path(p).name for p in row["filenames"]]})
   logs=(zone/"stderr").read_text();reasons=[]
   for ln in logs.splitlines():
    if "dirty: " not in ln:continue
    txt=ln.split("dirty: ",1)[1];m=re.search(r'package_id=([^ ]+).*?target="([^"]+)"',ln)
    reasons.append([m[1] if m else None,m[2] if m else None,re.match(r"[A-Za-z0-9_]+",txt).group(0)])
   out["series"][rev][label]={"source":summary["source"],"git_dir_unchanged":not summary["gitdir_changed"],"native":native,"artifacts":artifacts,"dirty_reasons":reasons,
    "native_log_sha256":sha(zone/"native.json"),"cargo_json_sha256":sha(zone/"cargo.jsonl"),"cargo_stderr_sha256":sha(zone/"stderr")}
 return out
if __name__=="__main__":
 val=projection(Path(sys.argv[1]));raw=json.dumps(val,sort_keys=True,separators=(",",":")).encode()
 dest=Path(__file__).resolve().parent/"observations.json.gz"
 with dest.open("xb") as f:f.write(gzip.compress(raw,compresslevel=9,mtime=0))
