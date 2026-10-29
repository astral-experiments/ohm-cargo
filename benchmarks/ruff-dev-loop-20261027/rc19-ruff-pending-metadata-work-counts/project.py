"""Reduce H3 metadata captures and Ruff native controls to reproducible, path-free records."""
from pathlib import Path
from decimal import Decimal
from collections import Counter
import gzip,hashlib,json,re,sys
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def alias(p):
    n=Path(p).name
    if n.startswith("libruff_python_ast-"):return "ast"
    if n.startswith("libruff_python_index-"):return "index"
    raise ValueError(n)
def project(root):
    out={"observers":{},"census":{},"api":{}}
    for method,dirname in (("plain","rmeta-plain-v1"),("inotify","rmeta-inotify-v1")):
        phases=out["observers"][method]={};r=root/dirname
        for f in sorted(r.glob("*/state.json")):
            v=json.loads(f.read_bytes());d=f.parent
            stages={k:{alias(n):x for n,x in v[k].items()} for k in ("before","after","old_fd_after")}
            events=[{"uses":[alias(n) for n in e["names"]],"received_monotonic_ns":e["received_monotonic_ns"],"mask":e["mask"],"view":{alias(n):s for n,s in e["view"].items()}} for e in v["events"]]
            stale=[]
            for line in v["notices"]:
                m=re.search(r'dependency on \x60ruff_python_ast\x60 is newer than we are ([0-9.]+)s > ([0-9.]+)s "[^"]*/crates/ruff_python_index"',line)
                if m:stale.append([int(Decimal(m[1])*10**9),int(Decimal(m[2])*10**9)])
            phases[d.name]={"source":v["rev"],"typed":v["units"],"dirty":v["dirty_units"],"fresh":dict(v["target_units"]),"metadata":stages,"events":events,"index_stale":stale,
                            "logs":{n:sha(d/n) for n in ("state.json","cargo.jsonl","stderr","status.json")}}
    traced=out["observers"]["syscall"]={}
    for f in sorted((root/"rmeta-chronology-v1").glob("*/stats.json")):
        d=f.parent;v=json.loads(f.read_bytes())
        before={k:[a["mtime"],a["sha256"]] for k,a in v["before"].items()}
        after={k:[a["mtime"],a["sha256"]] for k,a in v["after"].items()}
        msgs=[json.loads(line) for line in (d/"cargo.jsonl").read_bytes().splitlines()];assert msgs[-1]=={"reason":"build-finished","success":True}
        traced[d.name]={"before":before,"after":after,"fresh":{a["target"]["name"]:a["fresh"] for a in msgs if a["reason"]=="compiler-artifact" and a["target"]["name"] in before},
                        "logs":{n:sha(d/n) for n in ("syscalls","rmeta-events","stats.json","cargo.jsonl","stderr")}}
    r=root/"debug-census-local"
    for arm in ("A","B"):
        sc=out["census"][arm]={}
        for f in sorted((r/arm).glob("*/summary.json")):
            z=f.parent;s=json.loads(f.read_bytes());n=json.loads((z/"native.json").read_bytes());assert n["root_exit"]==0 and set(n["process_exit"].values())=={0}
            events=[{"role":a["role"],"target":a["target"],"argv_sha256":a["argv_sha256"],"out":Path(a["out"]).name if a["out"] else None} for a in n["events"]]
            assert Counter(e["role"] for e in events)==s["roles"]
            atoms=[json.loads(line) for line in (z/"cargo.jsonl").read_bytes().splitlines()]
            assert atoms[-1]=={"reason":"build-finished","success":True}
            units=[a for a in atoms if a["reason"]=="compiler-artifact"];assert len(units)==s["units"]==510
            identity=sorted(json.dumps([a["target"]["name"],a["target"]["kind"],a["target"]["test"],a["target"]["doctest"],a["features"],a["profile"]],sort_keys=True) for a in units)
            sc[z.name]={"source":s["source"],"typed":len(units),"dirty":sum(not a["fresh"] for a in units),"selected":hashlib.sha256("\n".join(identity).encode()).hexdigest(),"events":events,
                        "logs":{n:sha(z/n) for n in ("native.json","cargo.jsonl","stderr","status.json")}}
        api=out["api"][arm]={};base=r/"ruff-api-control-v1"/arm
        for f in sorted(base.glob("*/summary.json")):
            d=f.parent;v=json.loads(f.read_bytes());v["logs"]={n:sha(d/n) for n in ("cargo.jsonl","stderr","status.json")};api[d.name]=v
    out["debug_image_sha256"]=json.loads((r/"candidate-debug.json").read_bytes())["candidate"]
    return out
if __name__=="__main__":
    d=project(Path(sys.argv[1]))
    target=Path(sys.argv[2])/"records.json.gz"
    with target.open("xb") as f:f.write(gzip.compress(json.dumps(d,sort_keys=True,separators=(",",":")).encode(),compresslevel=9,mtime=0))
