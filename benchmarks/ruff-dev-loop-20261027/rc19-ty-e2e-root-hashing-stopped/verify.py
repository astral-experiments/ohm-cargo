"""Verify source, full raw-digest bindings, live job counts and the two independent generation rules."""
from pathlib import Path
import collections
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tempfile

D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(name):
    b=(D/name).read_bytes()
    return json.loads(gzip.decompress(b) if str(name).endswith(".gz") else b)
def verify():
    registered={}
    for l in (D/"SHA256SUMS").read_text().splitlines():
        h,n=l.split("  ",1);p=Path(n)
        assert n not in registered and not p.is_absolute() and ".." not in p.parts
        assert sha(D/p)==h
        registered[n]=h
    assert set(registered)=={str(f.relative_to(D)) for f in D.rglob("*") if f.is_file() and f.name!="SHA256SUMS"}
    rx=re.compile(rb"openai[.](org|com|internal)|artifactor[y][.]|authorizatio[n]: bear[e]r|github_pa[t]_|gh[p]_[A-Za-z0-9]{16}|/ho[m]e/dev-user|/mn[t]/devbox|charlie-oh[m]-",re.I)
    for f in registered:
        p=D/f;b=p.read_bytes();b=gzip.decompress(b) if p.suffix==".gz" else b
        assert not rx.search(b),f
        assert p.stat().st_size<8*1024*1024
    src=D/"ruff-source";record=obj("ruff-source/source-and-license.json")
    for k,v in record["source_sha256"].items():
        if k in ("original","edited","invalid"):assert sha(src/(k+".rs"))==v
    lic=record["license"];body=(src/"RUFF-LICENSE").read_bytes()
    assert hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()==lic["git_blob"]
    assert sha(src/"RUFF-LICENSE")==lic["sha256"] and len(body)==lic["length"]
    assert sha(src/"historical.patch")==record["historical_patch_sha256"]
    with tempfile.TemporaryDirectory() as t:
        path=Path(t)/record["sole_historical_git_path"];path.parent.mkdir(parents=True);shutil.copyfile(src/"original.rs",path)
        subprocess.run(["git","apply","--reverse",str(src/"historical.patch")],cwd=t,check=True)
        assert path.read_bytes()==(src/"edited.rs").read_bytes()
        subprocess.run(["git","apply",str(src/"historical.patch")],cwd=t,check=True)
        assert path.read_bytes()==(src/"original.rs").read_bytes()
    assert (src/"invalid.rs").read_text().splitlines()[record["invalid_line"]-1]==record["invalid_statement"]
    summary=obj("terminal.json");cmd=obj("commands.json.gz");assert len(cmd)==summary["reported_visits"]
    seen=set();refs={};cold={};num=collections.Counter()
    for r in cmd:
        spot=r["lane"],r["visit"];assert spot not in seen;seen.add(spot)
        if "native" in r:
            trace=obj("records/"+r["native"])
            assert trace["raw"]==r["physical_raw"]["native.json"]
            assert trace["roles"]==dict(collections.Counter(z["role"] for z in trace["events"]))
            assert trace["tools"]["stock-wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
            assert not any(z.get("link_only") for z in trace["events"])
        if not r.get("source"):continue
        assert r["exit"]==r["cargo_exit"]
        closure=obj("records/"+r["dependencies"]);assert len(closure["typed"])==553 and len(closure["scripts"])==30 and closure["private_source"]==r["physical_raw"]["dependencies.json"]
        rost=obj("records/"+r["roster"]);assert len(rost)==r["units"]
        if r["source"]=="invalid":
            assert r["units"]==r["fresh"]==299 and r["exit"]==101
            assert all(x["code"]=="E0308" and any(y[0].endswith("inlay_hints.rs") and y[1]==22 for y in x["primary"]) for x in r["diagnostics"])
            continue
        num["valid"]+=1;assert r["units"]==300 and r["exit"]==0 and not r["diagnostics"]
        verdicts=r["verdicts"];assert verdicts["list"]["status"]==verdicts["coherent"]["status"]["status"]==0
        for case in ["inlay_hints::default_inlay_hints","notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"]:assert verdicts[case]["status"]==0
        if "native_parser" in verdicts:assert verdicts["native_parser"]["compile"]["status"]==verdicts["native_parser"]["run"]["status"]==0
        assert verdicts["source_bytes"][r["source"]]>=0 and verdicts["source_bytes"]["edited" if r["source"]=="original" else "original"]==-1
        if not r["lane"].startswith("cold-"):
            h=closure["private_source"];assert refs.setdefault("paired_closure",h)==h
        else:
            cold[r["lane"]]=closure["private_source"];assert r["fresh"]==0
        if "bound_final_elf" in summary:
            assert r["e2e"]==summary["bound_final_elf"][r["source"]]
    assert num["valid"]==summary["successful_validated_visits"]
    assert summary["original_mount_rejection"]["cargo"]==0
    assert summary["prior_parser_study_admitted_pairs"]==0
    print(summary["status"],"—",num["valid"],"native-validated successful visits,",len(cold),"fully empty coherent graphs,",summary["primary_pairs"],"primary,",summary["wall_pairs"],"wall pairs")
if __name__=="__main__":
    verify()
    subprocess.run(["python3","-IB",str(D/"verify-diagnostic.py")],check=True)
