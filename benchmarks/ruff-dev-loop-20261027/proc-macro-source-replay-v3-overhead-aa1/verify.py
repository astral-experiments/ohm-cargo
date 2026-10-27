from pathlib import Path
import hashlib,json,math,statistics

p=Path(__file__).resolve().parent
def load(f):return json.loads((p/f).read_bytes())
def sha(f):return hashlib.sha256((p/f).read_bytes()).hexdigest()
mf={k:v for line in (p/"SHA256SUMS").read_text().splitlines() for v,k in [line.split("  ",1)]}
assert set(mf)=={f.relative_to(p).as_posix() for f in p.rglob("*") if f.is_file() and f.name!="SHA256SUMS"} and all(sha(k)==v for k,v in mf.items())
out=load("complete.json");plan=load("plan.json");rows=load("observations.json");assert out["fresh_product_scores"]==0 and len(rows)==32 and sha("observations.json")==out["sha256_observations"]
assert not plan["identical_inode"] and plan["sha256"]=="dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"
assert len({r["rmeta_sha256"] for r in rows})==1
by={i:[] for i in range(4)};blocks=[]
for i,order in enumerate(plan["blocks"]):
    src=rows[4*i:4*i+4];assert [r["label"] for r in src]==order
    pre=Path(f"block-{i:02d}");assert load(pre/"unclocked-prime"/"child.json")["wall_ns"] is None
    sec={}
    for j,r in enumerate(src):
        ch=r["child"];assert r["actual_sha"]==plan["sha256"] and r["position"]==j and ch["exit"]==0
        d=pre/f'{j}-{r["label"]}';assert ch==load(d/"child.json") and load(d/"result.json")["rmeta_sha256"]==r["rmeta_sha256"]
        assert set(load(d/"system-snapshots.json"))=={"before","after"} and ch["faults_major"]>=0
        sec.setdefault(r["label"],[]).append(math.log(ch["wall_ns"]));by[j].append(ch["wall_ns"])
    blocks.append(100*math.expm1(statistics.mean(sec["candidate"])-statistics.mean(sec["parent"])))
assert blocks==out["signed_geometric_batch_pct"] and statistics.median(blocks)==out["median_pct"] and out["position_median_ms"]=={str(k):statistics.median(v)/1e6 for k,v in by.items()}
assert out["abs_below_5pct"]==sum(abs(z)<5 for z in blocks)
print("Verified 32 code-identical control compiles, eight untimed retained primings and all raw timings, metadata and resource observations.")
