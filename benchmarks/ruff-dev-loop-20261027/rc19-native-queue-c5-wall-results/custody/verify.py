"""Verify the complete original and two-copy digests for the 12-pair edit section."""
from pathlib import Path
import hashlib
import json
import re
import sys
p=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def load(f):return json.loads((p/f).read_bytes())
roles={"capture.json":"original-capture","scratch.json":"first-copy-reread","secondary.json":"second-host-reread","original-final.json":"original-reread"}
def check():
 seal=load("receipt.json")
 assert sha((p/"receipt.json").read_bytes())=="6d35c9171d461611090c81a3ebc1f47d89d0e797761ba1ff4d12f97619050ffc"
 assert seal["copies"]==2 and seal["files"]==226 and seal["bytes"]==82660757
 assert all(seal[k] is True for k in ("original_inodes_all_same","original_type_mode_uid_gid_nlink_size_atime_mtime_ctime_all_same","first_copy_separate_filesystem","independent_host_reopened_every_regular_file"))
 for f in roles:
    assert sha((p/f).read_bytes())==seal["manifests"][f]
 manifests=[load(f) for f in roles]
 assert [m["role"] for m in manifests]==list(roles.values())
 rows=manifests[0]["files"]
 assert all(m["files"]==rows and m["total_bytes"]==82660757 and m["file_count"]==226 for m in manifests)
 expected={"clock/"+f for f in ["binding.json","host-after.json","host-before.json","pairs.json",*[f"p{n:02}.json" for n in range(1,13)]]}
 expected|={"launcher/stdout","launcher/stderr","launcher/exit","release/section.json"}
 for a in "AB":
    for phase in ["prepare","warm-1","warm-2","trace-before","trace-after",*[f"p{n:02}-{w}" for n in range(1,13) for w in ("edit","repeat")]]:
        fs=["cargo.stdout","cargo.stderr","result.json"]
        if phase.startswith("trace-"):fs+=["execs.json","image-contract.json"]
        if phase.endswith("-repeat"):fs.append("behavior.json")
        expected.update(f"runs/{phase}-{a}/{f}" for f in fs)
 assert set(rows)==expected and sum(x["bytes"] for x in rows.values())==seal["bytes"]
 assert all(set(x)=={"bytes","sha256"} and x["bytes"]>=0 and re.fullmatch("[0-9a-f]{64}",x["sha256"]) for x in rows.values())
 assert rows["clock/pairs.json"]["sha256"]=="341e03ac9de50b2a30315e28e944870583b14376135c461df6cf6c53f8fbe65d"
 for f,b in (("exit",b"0\n"),("stderr",b""),("stdout",b"Eligible work and two ordinary warmups verified in each arm.\nCompleted 8 of 12 pairs.\nAll declared pairs and post-run native work verified.\n")):
    assert rows["launcher/"+f]=={"sha256":sha(b),"bytes":len(b)}
if __name__=="__main__":check();print("226 originals, two independent copies, 82,660,757 bytes and the terminal role receipts verified.")
