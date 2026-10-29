"""Validate complete paired wall-time rows and product controls before computing estimates."""
from pathlib import Path
import collections, hashlib, json, math, random, statistics, sys
root=Path(sys.argv[1])
def sha(p):
    with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def ci(groups):
    r=random.Random(0x0e398aa5)
    estimates=[]
    for _ in range(20000):
        v=[x[r.randrange(len(x))] for x in groups for __ in range(len(x))]
        estimates.append(statistics.median(v))
    estimates.sort()
    return [estimates[int((len(estimates)-1)*k)] for k in (.025,.975)]
def metric(rows):
    delta=[100*(a-b)/a for a,b,_ in rows]
    counts=collections.Counter(1 if x>0 else -1 if x<0 else 0 for x in delta)
    n=counts[1]+counts[-1];s=min(counts[1],counts[-1])
    p=min(1,2*sum(math.comb(n,k) for k in range(s+1))/2**n)
    groups={}
    for value,(a,b,key) in zip(delta,rows):
        groups.setdefault(key,[]).append(value)
    assert set(map(len,groups.values()))=={8} and len(groups)==4
    return {"n":len(rows),"parent_median_ms":statistics.median(a for a,_,_ in rows)/1e6,
            "candidate_median_ms":statistics.median(b for _,b,_ in rows)/1e6,
            "paired_median_ms":statistics.median((a-b)/1e6 for a,b,_ in rows),
            "paired_reduction_pct":statistics.median(delta),"bootstrap95_pct":ci(list(groups.values())),
            "sign_test_p_two_sided":p,"faster_pairs":counts[1],
            "direction_medians_pct":{side:statistics.median(d for d,(_,_,k) in zip(delta,rows) if k[0]==side) for side in ("orig","edit")}}
def compute(md):
    d=root/("toml-"+md+"-v1")
    t=read(d/"terminal.json"); assert t["mode"]==md and len(t["events"])==128
    assert t["base"]=="967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9"
    assert t["lock"]=="c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
    enroll=[read(d/a/"enrollment.json") for a in "AB"]
    for k in ("version","orig","edit","lock","units","argv","env","plan","rust","wild"):
        assert enroll[0][k]==enroll[1][k],k
    assert [x["cargo"] for x in enroll]==[t["base"],t["candidate"]]
    common=None
    for a in "AB":
        for tag in ("01-edited","02-restored","03-settled","99-terminal"):
            control=read(d/a/(tag+".json"))
            assert not control["dirty"] and not any(e[1] or e[2] for e in control["exec"])
            current={k:control[k] for k in ("oracle","roster","files")}
            if common is not None: assert current==common,(a,tag)
            common=current
    assert common
    results={k:[] for k in ("edit","repeat","edit_plus_repeat")}
    for i in range(32):
        rows=t["events"][i*4:i*4+4]
        order=("AB","BA","BA","AB")[i%4]
        side=("edit","orig")[i%2]
        assert [(r["arm"],r["phase"]) for r in rows]==[(a,p)for a in order for p in ("edit","repeat")]
        values={}
        for r in rows:
            a,phase=r["arm"],r["phase"]; tag=f"{i:02}-{phase}"; native=read(d/a/(tag+".json"))
            assert (r["pair"],r["sequence"],r["source"])==(i,order,side)
            assert r["ns"]==native["ns"]>0 and native["exit"]==0 and sha(d/a/(tag+".stderr"))==native["stderr"]
            assert sha(d/a/(tag+".stdout"))==native["stdout"]==hashlib.sha256(b"").hexdigest()
            assert b"Finished" in (d/a/(tag+".stderr")).read_bytes()
            values[a,phase]=r["ns"]
        for phase in ("edit","repeat"):
            results[phase].append((values["A",phase],values["B",phase],(side,order)))
        results["edit_plus_repeat"].append((sum(values["A",s] for s in ("edit","repeat")),sum(values["B",s] for s in ("edit","repeat")),(side,order)))
    return {"workload":md,"declared_files":len(common["files"]),"artifacts":len(common["roster"]),"units_in_plan":enroll[0]["units"],
            "oracle":common["oracle"],"data_sha256":sha(d/"terminal.json"),"metrics":{k:metric(v) for k,v in results.items()}}
print(json.dumps([compute(md) for md in sys.argv[2:]],indent=2))

