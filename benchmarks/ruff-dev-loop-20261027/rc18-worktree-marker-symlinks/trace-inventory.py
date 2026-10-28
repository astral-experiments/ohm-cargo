"""Independently count every physical exec attempt in each retained trace, including split unfinished syscalls."""
from pathlib import Path
import ast
import hashlib
import json
import re
import sys
root=Path(sys.argv[1]);assert root.parent==Path("/dev/shm") and root.name.startswith("ohm-markers-all-")
j=json.loads((root/"ledger.json").read_bytes()); rows=[]
for b in j["builds"]:
    raw=(root/"logs"/(b["name"]+".trace")).read_bytes();assert hashlib.sha256(raw).hexdigest()==b["trace_sha256"]
    execs=[]
    for line in raw.splitlines():
        mm=re.match(rb'^\s*(\d+) execve\(("(?:[^"\\]|\\.)*"),',line)
        if not mm:continue
        path=ast.literal_eval(mm[2].decode());kind=Path(path).name
        if kind=="rustc":role="rustc-crate" if b'"--crate-name"' in line else "rustc-probe"
        elif kind.startswith("build_script_build-") or kind=="build-script-build":role="build-script"
        else:role=kind
        execs.append({"pid":int(mm[1]),"role":role,"argv_line_sha256":hashlib.sha256(line).hexdigest()})
    rows.append({"name":b["name"],"trace_sha256":b["trace_sha256"],"all_execs":execs})
print(json.dumps(rows,indent=2,sort_keys=True))
