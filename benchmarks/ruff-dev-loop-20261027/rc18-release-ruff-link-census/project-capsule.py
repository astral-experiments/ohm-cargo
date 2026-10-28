"""Project the separately sealed native handoff without publishing developer paths."""
from pathlib import Path
import gzip
import hashlib
import json
import re
import subprocess
import sys

root = Path(sys.argv[1]).resolve(strict=True)
sha = lambda b: hashlib.sha256(b).hexdigest()
manifest = (root / "SHA256SUMS").read_bytes()
assert sha(manifest) == "938bc72b5fd4b269e0c8a8573ab70323b825cf242b743d6b22bd3758b9ee276d"
for line in manifest.decode().splitlines():
    digest, name = line.split("  ", 1)
    assert not Path(name).is_absolute() and ".." not in Path(name).parts and sha((root/name).read_bytes()) == digest
subprocess.run([sys.executable, "-IB", root/"verify.py"], check=True, stdout=subprocess.DEVNULL)
sources = {}
def load(name):
    raw = (root/name).read_bytes()
    payload = gzip.decompress(raw) if name.endswith(".gz") else raw
    sources[name] = {"file_sha256":sha(raw), "decoded_sha256":sha(payload)}
    return json.loads(payload)

complete=load("complete.json.gz")
reviewed=load("reviewed.json.gz")
out={"component_manifest":sha(manifest), "complete_sha256":sources["complete.json.gz"]["decoded_sha256"],
     "original_seed_untouched":complete["root_seed_untouched"], "controlled_workspace_only": complete["controlled_full_workspace_only"],
     "training_sha256":reviewed["real_width_one_recipe"]["training_sha256"], "wild_sha256":reviewed["wild"],
     "preparer_stock_identity":{"device":reviewed["physical_stock_dev"], "inode":reviewed["physical_stock_ino"]},
     "reviewed_sha256":sources["reviewed.json.gz"]["decoded_sha256"], "target":Path(reviewed["target"]).name,
     "phases":[]}
for row in complete["phases"]:
    phase=row["phase"]; base="commands/"+phase+"/"
    detail=load(base+"result.json.gz")
    processes=load(base+"execs.json.gz")
    small=load(base+"smallest-result.json.gz")
    audit_file,=(root/base/"audit").glob("*.json")
    audit=load(audit_file.relative_to(root).as_posix())
    events=[{"pid":e["pid"], "role":e["role"], "out":Path(e["out"]).name if e.get("out") else None,
             "argv_sha256":e["argv_sha256"], "exit":processes["process_exit"][str(e["pid"])]} for e in processes["events"]]
    proofs={k:v for k,v in row.items() if k in ("phase","units","counts","e2e_after_sha256","e2e_before_sha256",
        "e2e_hit","e2e_list_count","e2e_listing_sha256","e2e_ran_stock","cargo_stderr_sha256","cargo_stdout_sha256",
        "native_result_sha256","process_receipt_sha256","source_full")}
    proofs["notebook_tests"]=detail["e2e_tests"]
    proofs["generator_exit"]=small["exit"]
    proofs["audit"]={k:audit[k] for k in ("pid","checker_code","workers","reason","decision","training_sha256","request_sha256")}
    stock_ids = set((e["dev"], e["ino"]) for e in processes["events"] if e["role"]=="stock-wild")
    assert len(stock_ids)==1
    proofs["observed_stock_identity"] = next(iter(stock_ids))
    proofs["events"]=events
    out["phases"].append(proofs)
rotation=load("post-restore-rlink.json.gz")
out["object_rotation"]={k:rotation[k] for k in ("e2e_sha256","literal_names_in_rlink","literal_names_in_rlink_cache")}
for key in ("original","after"):
    out["object_rotation"][key]={Path(f).name:{"size":v["size"],"sha256":v["sha256"]} for f,v in rotation[key].items()}
    assert len(out["object_rotation"][key])==len(rotation[key])
threads=load("unchanged-all-threads.json.gz")
out["thread_families"]=[{"role":r["role"],"pid":r["pid"],"exec_sha256":r["exec_sha256"],"unit_or_output":Path(r["unit_or_output"]).name,
    "threads":r["all_same_image_thread_creations"],"observed_clone_edges":len(r["thread_edges"]),
    "workers":r["stock_worker_count"]} for r in threads["rows"]]
out["sources"]=sources
print(json.dumps(out,indent=2,sort_keys=True))
