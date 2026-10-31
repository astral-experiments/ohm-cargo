"""Recalculate the direct GNU branch-return result from six verified host receipts."""
import json
import sys
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from statistics import median

RUN = 41222947202
REV = "23685581114abfed1227fb7514bbc0ad934a1ecd"
PLAN = "e110fd5e73b3f6a8f102a9837229d8bd2644693c39aa2b6a0c75ca7de2f778d8"
ARMS = ("Foff", "Fon", "Kon")
PHASES = ("cold-A","first-B","return-A","return-B","unchanged-B","invalid","repair")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main(path):
    src = json.loads(path.read_bytes())
    require((src["run"],src["head"],src["plan"])==(RUN,REV,PLAN),"different original study")
    positions = [f"{i:02d}" for i in range(1,7)]
    require(set(src["hosts"])==set(src["artifacts"])==set(positions),"six paired hosts are required")
    hosts = [src["hosts"][i] for i in positions]
    require({tuple(h["order"]) for h in hosts}==set(permutations(ARMS)),"missing counterbalanced order")
    boots = {h["boot"] for h in hosts}
    require(len(boots)==6 and boots.isdisjoint(src["excluded_boots"]),"reused host")
    for key in ("id","job","sha256"):
        require(len({m[key] for m in src["artifacts"].values()})==6,"reused "+key)
    for host in hosts:
        require(set(host["arms"])==set(ARMS),"missing compiler or cache setting")
        for visits in host["arms"].values():
            require(set(visits)==set(PHASES),"incomplete build history")
            for row in visits.values():
                require(all(type(row[k]) is int and row[k]>0 for k in
                    ("instructions","enabled","running","unmetered_allocated")),"invalid counter or disk reading")
                require(995*row["enabled"]<=1000*row["running"]<=1000*row["enabled"],"counter coverage")

    def total(arm, labels):
        return [sum(h["arms"][arm][p]["instructions"] for p in labels) for h in hosts]

    def paired(num,den):
        return [Fraction(x,y) for x,y in zip(num,den,strict=True)]

    labels = [*[(p,(p,)) for p in PHASES], ("Both returns",("return-A","return-B")),
              ("Empty through both returns",PHASES[:4]),("All seven commands",PHASES)]
    print("| Build | F off, billion | F on, billion | K on, billion | F off / F on | K on / F on |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, visits in labels:
        off,on,packed = (total(a,visits) for a in ARMS)
        show = [f"{median(v)/10**9:,.2f}" for v in (off,on,packed)]
        print(f"| {name} | "+" | ".join(show)+f" | {float(median(paired(off,on))):.4f}× | {float(median(paired(packed,on))):.4f}× |")
    ratios = paired(total("Foff",("return-A","return-B")),total("Fon",("return-A","return-B")))
    p = src["primary"]
    require(all(r>2 for r in ratios) and p["all_six_strictly_above_two"] and
            p["one_sided_exact_sign_probability_at_2"]==1/64,"registered twofold gate")
    require([float(min(ratios)),float(max(ratios))]==p["exact_96_875_percent_interval"],"interval mismatch")
    print(f"\nF off / F on for both returns: {float(median(ratios)):.5f}× "
          f"(exact 96.875% interval {float(min(ratios)):.5f}–{float(max(ratios)):.5f}×).")
    print("\n| Visit end | F on minus F off | K on minus F off | K on minus F on |")
    print("| --- | ---: | ---: | ---: |")
    for v in PHASES:
        sums=[[h["arms"][a][v]["unmetered_allocated"] for h in hosts] for a in ARMS]
        diffs=[median(q-p for p,q in zip(sums[i],sums[j],strict=True))/2**20 for i,j in ((0,1),(0,2),(1,2))]
        print(f"| {v} | "+" | ".join(f"{x:+,.1f} MiB" for x in diffs)+" |")


if __name__=="__main__":
    main(Path(sys.argv[1]))
