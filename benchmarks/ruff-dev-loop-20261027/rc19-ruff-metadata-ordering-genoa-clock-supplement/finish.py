from pathlib import Path
import json,runpy,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"admin-pgo-ops"))
from admin_ctl import *
r=R/"genoa-supplement-scored";o=json.loads((R/"protocol-v1/genoa.json").read_text());assert len(o)==32
a=[]
for p in o:
    pair_control=json.loads((r/f"pair-{p['pair']:02d}.accepted.json").read_bytes());assert pair_control["pair"]==p["pair"] and len(pair_control["visits"])==2
    row=dict(p)
    for j,k in enumerate(p["order"]):
        d=r/f"pair-{p['pair']:02d}-visit-{j}-{k}"
        t=json.loads((d/"terminal.json").read_text())
        assert t["ok"] and not (d/"failure.json").exists() and t["arm"]==k and t["pair"]==p["pair"]
        assert pair_control["visits"][d.name]["reader_and_products"]==sha(d/"post-pair/accepted.json")
        exe=json.loads((d/"executions.json").read_text())
        assert t["executions_sha"]==sha(d/"executions.json") and [x["step"] for x in exe]==["edit","repeat"]
        assert all(x["exit"]==0 and x["ns"]>0 for x in exe)
        row[k]=[w["ns"] for w in exe]
    a.append(row)
u=runpy.run_path(str(R/"protocol-v1/paired.py"))
save(r/"pairs.json",a);save(r/"analysis.json",u["analyze"]("genoa",a))
save(r/"complete.json",{"pairs":32,"commands":128,"analysis_sha256":sha(r/"analysis.json"),"pairs_sha256":sha(r/"pairs.json"),"gate_sha256":sha(R/"genoa-supplement-admission.json"),"grant_sha256":sha(R/"genoa-supplement-clock-release.json"),"plan":sha(R/"protocol-v1/SHA256SUMS")})
