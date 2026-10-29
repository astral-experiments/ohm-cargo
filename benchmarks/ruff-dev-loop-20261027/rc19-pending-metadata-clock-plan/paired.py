"""Portable plan and paired analysis; only complete predefined host series can be scored."""
from itertools import product
from pathlib import Path
from statistics import mean,median
import argparse,hashlib,json,math,random
SEEDS={"milan":16468,"genoa":84348}
def roster(host):
    r=random.Random(SEEDS[host]);out=[]
    for block in range(8):
        items=list(product(("child-to-parent","parent-to-child"),("AB","BA")));r.shuffle(items)
        for direction,order in items:out.append({"block":block,"pair":len(out),"direction":direction,"order":order})
    return out
def quantile(v,q):
    u=sorted(v);n=q*(len(u)-1);i=math.floor(n);return u[i]+(n-i)*(u[min(i+1,len(u)-1)]-u[i])
def metric(pairs,indices):
    rows=[]
    for p in pairs:
        a=sum(p["A"][i] for i in indices);b=sum(p["B"][i] for i in indices)
        assert all(isinstance(n,int) and n>0 for n in p["A"]+p["B"]) and len(p["A"])==len(p["B"])==2
        rows.append((1-b/a, math.log(a/b)))
    blocks=[rows[i:i+4] for i in range(0,len(rows),4)]
    assert len(blocks)==8 and all(len(s)==4 for s in blocks)
    observed=median(x[0] for x in rows);rng=random.Random(209112)
    boots=[median(x[0] for _ in blocks for x in rng.choice(blocks)) for n in range(20000)]
    block_means=[mean(x[1] for x in s) for s in blocks]
    loc=abs(sum(block_means))
    pvalue=sum(abs(sum(sign*x for sign,x in zip(signs,block_means)))+1.e-15>=loc for signs in product((-1,1),repeat=8))/256
    return {"median_saving":observed,"ci95":[quantile(boots,0.025),quantile(boots,0.975)],"block_signflip_p":pvalue,
            "pairs_positive":sum(x[0]>0 for x in rows),"n":len(rows)}
def analyze(host,pairs):
    assert [{k:p[k] for k in ("block","pair","direction","order")} for p in pairs]==roster(host)
    scores={k:metric(pairs,what) for k,what in [("loop",(0,1)),("edit",(0,)),("repeat",(1,))]}
    x=scores["loop"];e=scores["edit"]
    scores["pass_primary"]=x["median_saving"]>=0.01 and x["ci95"][0]>0 and x["block_signflip_p"]<.05
    scores["edited_slowdown_gate"]=e["median_saving"]<-.03 and e["ci95"][1]<0
    return scores
if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("host",choices=SEEDS);cli.add_argument("file",nargs="?");a=cli.parse_args()
    if a.file:result=analyze(a.host,json.loads(Path(a.file).read_bytes()))
    else:result=roster(a.host)
    print(json.dumps(result,indent=2))
