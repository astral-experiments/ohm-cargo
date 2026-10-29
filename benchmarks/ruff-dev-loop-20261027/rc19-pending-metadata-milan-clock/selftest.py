"""Check that plausible damage to one retained row fails the portable reader."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parent
def change_clock(obj): obj[0]["A"][0]+=1
def change_order(obj): obj[0]["order"]=obj[0]["order"][::-1]
def change_freshness(obj):
    row=next(r for r in obj if r["phase"]=="repeat")
    row["artifact_order"][0]*=-1
def change_flank(obj):
    row=next(r for r in obj if r["phase"]=="after")
    row["receipt"]["images"]["ruff_python_ast"]="0"*64
def change_source(obj): obj["ruff"]["files"]["Cargo.lock"]["child"]["bytes"]+=1

with tempfile.TemporaryDirectory() as top:
    dst=Path(top)/"packet"
    shutil.copytree(root,dst)
    for name,func in [("observations.json",change_clock),("observations.json",change_order),
                      ("commands.json.gz",change_freshness),("commands.json.gz",change_flank),
                      ("source-revisions.json",change_source)]:
        f=dst/name; orig=f.read_bytes(); obj=json.loads(gzip.decompress(orig) if name.endswith(".gz") else orig)
        func(obj); data=json.dumps(obj).encode(); f.write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)
        p=subprocess.run([sys.executable,"-IB",str(dst/"verify.py")],capture_output=True)
        assert p.returncode!=0 and b"AssertionError" in p.stderr,(func.__name__,p.returncode,p.stderr[-200:])
        f.write_bytes(orig)
print("Rejected isolated clock, arm-order, artifact freshness, flank metadata and source mutations.")

