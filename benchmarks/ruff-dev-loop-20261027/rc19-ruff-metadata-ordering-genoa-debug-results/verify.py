from pathlib import Path
import collections,gzip,hashlib,json,re
p=Path(__file__).resolve().parent
for line in (p/"SHA256SUMS").read_text().splitlines():
 h,n=line.split("  ");assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
def get(n):
 b=(p/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
r=get("commands.json");ev=get("observed-typed-processes.json.gz");g=get("visibility-and-body.json.gz");s=get("subject.json")
assert len(s["member_ids"])==47 and len(set(s["member_ids"]))==47 and s["total_registry_crates"]==494 and len(s["git_commits"])==2
assert len(r)==len(ev)==14 and r.keys()==ev.keys()
expect={"A/parent":[51,12,1],"A/child":[51,24,1],"B/parent":[56,1,1],"B/child":[56,1,1]}
ident={}
for name,summary in r.items():
 unit=ev[name]["typed"];proc=ev[name]["native"];assert len(unit)==510 and sum(not u["fresh"] for u in unit)==summary["typed_dirty"]
 assert collections.Counter(a["role"] for a in proc)==summary["roles"] and all(a["exit"]==0 for a in proc)
 key=(summary["source"],name[0]);shape=sorted(json.dumps({k:v for k,v in u.items() if k!="fresh"},sort_keys=True) for u in unit)
 if key in ident:assert ident[key]==shape
 ident[key]=shape
 assert len(proc)==len({a["pid"] for a in proc}) and all(len(a["argv_sha256"])==64 for a in proc)
 for out in [n["output"] for n in proc if n["role"]=="stock-wild"]:
  assert out.startswith("libruff_macros-") and out in [x for u in unit if not u["fresh"] and u["name"]=="ruff_macros" for x in u["outputs"]]
 assert summary["diff_ast_minus_index_ns"]==summary["files"]["ruff_python_ast"]["mtime_ns"]-summary["files"]["ruff_python_index"]["mtime_ns"]
for key,ns in expect.items():
 v=[r[key+"-"+f] for f in ("edit","repeat1","repeat2")]
 assert [i["roles"]["rustc-full"] for i in v]==ns
 assert [i["roles"].get("stock-wild",0) for i in v]==[1,0,0]
 if key.startswith("A"):assert v[0]["diff_ast_minus_index_ns"]>0 and v[0]["diff_ast_minus_index_ns"] in v[1]["reported_ast_index_newer_ns"]
 else:assert v[0]["diff_ast_minus_index_ns"]<0 and not v[1]["reported_ast_index_newer_ns"]
for rev in (s["source"],s["parent"]):assert ident[rev,"A"]==ident[rev,"B"]
for u in ("ruff_python_ast","ruff_python_index"):assert len({v["files"][u]["sha256"] for v in r.values()})==1
assert g["empty"]["diagnostics"]==g["warm"]["diagnostics"] and len(g["warm"]["diagnostics"])==1 and g["warm"]["diagnostics"][0]["code"]["code"]=="E0624"
assert g["warm"]["diagnostic_sha256"]==g["empty"]["diagnostic_sha256"] and g["empty-restored"]["valid"]
assert all(g[a]["selected"]==510 and g[a]["roles"]["rustc-full"]==v for a,v in (("private-body",34),("private-repeat",1),("private-restored",34),("private-restored-repeat",1)))
deny=re.compile(rb"(?:openai[.](?:org|com|internal)|artifactory[.]|authorization: bearer|github_pat_|ghp_[A-Za-z0-9]{16}|/home/dev-user|charlie-ohm-)",re.I)
for f in p.iterdir():
 if f.is_file() and f.suffix in (".gz",".json",".md"):
  b=f.read_bytes();assert not deny.search(gzip.decompress(b) if f.suffix==".gz" else b),f.name
print("Verified 14 native workspace commands, 7,140 typed artifacts, all compiler and linker exits, both exact .rmeta files and the real warm/empty E0624.")
