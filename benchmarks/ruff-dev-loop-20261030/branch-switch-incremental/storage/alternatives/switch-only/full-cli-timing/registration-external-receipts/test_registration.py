#!/usr/bin/env python3
"""Recheck the original plan, exact route discontinuities, and frozen carrier derivation."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from receiver import GIB,MIB,check,digest
from select_route import choose

def load(p):return json.loads(p.read_bytes())
def main():
    ap=argparse.ArgumentParser();ap.add_argument("original",type=Path);ap.add_argument("--original-site",type=Path)
    x=ap.parse_args();p=load(HERE/"registration.json")
    check(digest(x.original/"SHA256SUMS")==p["original_manifest"],"original registration replaced")
    subprocess.run(["sha256sum","--quiet","-c","SHA256SUMS"],cwd=x.original,check=True)
    original=load(x.original/"plan.json")
    check(len(original["schedule"])==28 and [r["arm"] for r in original["schedule"][:4]]==["on","off","off","on"],
          "original pilot order or independent pair count")
    ca=p["external_strict_bytes"]
    check(ca["entry_scratch"]==140*GIB+8*MIB and ca["entry_home"]==140*GIB+384*MIB and
          ca["receiver_data_image"]==383*MIB and ca["within_image_failure_reserve"]==180*MIB and
          p["confirmation"]["simultaneous_coverage_lower_bound"]==1-2*(79+13)/4096,"bounds or family coverage")
    y=lambda s,h,m,pr=True:choose(s,h,m,predecessors=pr,ordinary_slots=0,original_release_exists=False)
    ms=ca["entry_mem"];hs=ca["entry_home"];ss=ca["entry_scratch"];orig=p["both_old_modes_require_strict_scratch_entry_bytes"]
    cases=[(orig+1,hs+1,ms+1,True,"original"),(orig+1,140*GIB+1,ms+1,True,"original"),
           (orig,hs+1,ms+1,True,"external-home"),(ss+1,hs+1,ms+1,True,"external-home"),
           (ss,hs+1,ms+1,True,"wait"),(ss+1,hs,ms+1,True,"wait"),(orig+1,hs+1,ms,True,"wait"),
           (orig+1,hs+1,ms+1,False,"wait")]
    for s,h,m,pr,expected in cases:check(y(s,h,m,pr)==expected,"resource rule boundary")
    for path in HERE.rglob("*.py"):ast.parse(path.read_text(),filename=str(path))
    for f in HERE.rglob("*.sh"):subprocess.run(["bash","-n",f],check=True)
    derived=None
    if x.original_site:
        check(digest(x.original_site/"SHA256SUMS")==p["original_physical_deployment"],"original site changed")
        subprocess.run(["sha256sum","--quiet","-c","SHA256SUMS"],cwd=x.original_site,check=True)
        spec=importlib.util.spec_from_file_location("source_carrier",HERE/"deployment/derive_carrier.py")
        gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
        with tempfile.TemporaryDirectory(prefix="registered-receipt-carrier-") as t:
            t=Path(t);gen.materialize(x.original_site,t,Path("/candidate-site/site"))
            for f in t.glob("*.py"):ast.parse(f.read_text(),filename=str(f))
            subprocess.run(["bash","-n",t/"carrier.sh"],check=True)
            for f in ["config.json","product.py","safe-worker.py"]:
                check((t/f).read_bytes()==(x.original_site/f).read_bytes(),"native SKU/bench/SDK changed")
            text=(t/"carrier.sh").read_text()
            check('umount "$external/receiver"' in text and 'trap hold EXIT' in text and
                  text.index('umount "$external/receiver"')<text.index("safe-worker.py"),"receiver remains visible")
            derived={f.name:digest(f) for f in sorted(t.iterdir())}
    print(json.dumps(dict(zero_scores=True,original_manifest=p["original_manifest"],independent_resource_boundaries=len(cases),
        original_order_retained=len(original["schedule"]),derived_source_display_with_placeholder_root=derived),sort_keys=True))

if __name__=="__main__":main()
