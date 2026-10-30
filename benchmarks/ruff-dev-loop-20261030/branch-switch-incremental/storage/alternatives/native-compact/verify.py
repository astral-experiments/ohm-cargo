"""Verify both complete Ruff branch returns, including the physical compact tables."""
import gzip
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
PHASES=("empty-A","first-B","return-A","return-B","unchanged-B")
TARGETS=("return-A","return-B")
CRATES=["ruff_python_ast","ruff_python_parser"]


def load(path):
    blob=path.read_bytes()
    return json.loads(gzip.decompress(blob) if path.suffix==".gz" else blob)


def infer(ratios, orders):
    n=len(ratios)
    values=sorted(ratios)
    out={"paired_median":median(ratios),"ratios":ratios}
    if n<8:
        return out
    rank=max(k for k in range(1,n//2+1)
             if 2*sum(math.comb(n,j) for j in range(k))/2**n<=.05/2)
    out["simultaneous_95_interval"]=[values[rank-1],values[-rank]]
    above=sum(x>2 for x in values)
    out["one_sided_p_vs_2"]=sum(math.comb(n,k) for k in range(above,n+1))/2**n
    effects=[math.log(x)*(1 if seq=="PQ" else -1) for x,seq in zip(ratios,orders)]
    observed=abs(sum(map(math.log,ratios)))
    null=[abs(sum(v*(1 if i in idx else -1) for i,v in enumerate(effects)))
          for idx in combinations(range(n),n//2)]
    out["two_sided_p_vs_equal"]=sum(x+1e-10>=observed for x in null)/len(null)
    return out


def check(data, independent):
    plan=data["recipe"]
    n=plan["pairs"]
    assert n in (2,12) and plan["orders"].count("PQ")==plan["orders"].count("QP")==n//2
    assert plan["same_sdk"] and plan["enable"] and not plan["gate_only"] and plan["hold_sdk_identity"]
    assert data["parents"]=={"P":plan["commit"],"Q":plan["commit"]} and data["shared_sdk_members"]==55
    assert all(s["files"]==data["sdk_identities"][0]["files"] for s in data["sdk_identities"])
    assert len(data["sdk_identities"])==4+2*n
    assert sorted(data["samples"])==sorted(independent["rows"])
    refs=data["references"]
    assert refs==independent["references"] and refs["PA"]==refs["QA"] and refs["PB"]==refs["QB"] and refs["PA"]!=refs["PB"]
    for slot, sample in data["samples"].items():
        recovered=independent["rows"][slot]
        assert set(sample)==set(PHASES)
        role=slot[-1]
        for phase,item in sample.items():
            raw=recovered[phase]
            assert raw["cargo_exit"]==0 and raw["physical_bytes"]==sum(raw["du_bytes"])==item["bytes"]
            assert raw["native_verdict"]=="Expr="+("64" if phase[-1]=="A" else "56")+" valid=1 rejected"
            assert item["ELF"]==refs[role+phase[-1]]
            if phase in TARGETS:assert raw["dirty"]==CRATES
            if phase=="unchanged-B":assert raw["dirty"]==[]
            tables=raw["tables"]
            assert len(tables)==item["retained_sessions"] and item["incremental_crate_directories"]==2
            packed=sum(name.startswith("ohm-packed-") for t in tables.values() for name in t["files"])
            assert packed==item["packed_tables"]
            if role=="P" or phase=="empty-A":
                assert len(tables)==2 and packed==0 and item["older"]==0
            if role=="Q" and phase in TARGETS:
                assert len(tables)==4 and packed==8 and item["older"]==2
            if plan["instructions"] and phase in TARGETS:
                assert item["counts"]["wild_links"]==0
                assert {name:role_data["Ir"] for name,role_data in item["counts"]["crates"].items()}==item["compiler_Ir"]
                assert sorted(item["compiler_Ir"])==CRATES and min(item["compiler_Ir"].values())>0
        if slot.startswith("pair-01-"):
            err=recovered["error_repair"]
            assert err["invalid_exit"]==101 and err["E0308"] and err["repair_exit"]==0
            assert err["repair_verdict"]=="Expr=56 valid=1 rejected"
    calculations={}
    for phase in (*PHASES,"first-B+return-A"):
        fields=phase.split("+")
        def visit(i, arm):
            return [data["samples"][f"pair-{i:02}-{arm}"][key] for key in fields]
        observations=[(visit(i,"P"),visit(i,"Q")) for i in range(1,n+1)]
        counted=plan["instructions"] and phase in TARGETS
        def total(rows):
            return sum(sum(x["compiler_Ir"].values()) for x in rows) if counted else sum(x["wall"] for x in rows)
        ratios=[total(p)/total(q) for p,q in observations]
        summary=infer(ratios,plan["orders"])
        summary.update(parent_median=median(total(p) for p,q in observations),candidate_median=median(total(q) for p,q in observations))
        if len(fields)==1:
            sizes=[q[0]["bytes"]/p[0]["bytes"] for p,q in observations]
            summary.update(parent_bytes=median(p[0]["bytes"] for p,q in observations),
                           candidate_bytes=median(q[0]["bytes"] for p,q in observations),max_storage_ratio=max(sizes))
            assert sizes==data["summary"][phase]["bytes_ratio"]
            assert ratios==data["summary"][phase]["instruction_ratios" if counted else "ratios"]
        if plan["instructions"] and any(p in TARGETS for p in fields) and not counted:
            continue
        calculations[phase]=summary
    return calculations


if __name__=="__main__":
    compiler = load(HERE / "compiler.json")
    product = compiler["product"]
    eq = compiler["equivalence"]
    assert hashlib.sha256((HERE / "compiler.patch").read_bytes()).hexdigest() == compiler["patch_sha256"]
    assert eq["source"] == product["rust"] == compiler["patched_source"]
    assert eq["measured_source"] == compiler["measured_source"]
    assert eq["different_members"] == [] and eq["compared"] == len(product["native_files"]) == 55
    assert len(compiler["unit_tests"]["tests"]) == 7
    assert {k: v["invoked_rustcs"] for k, v in compiler["run_make"].items()} == {
        "ohm-packed-branch-cache": 8, "ohm-branch-cache-opt-out": 7, "ohm-relink-assembler-inputs": 12}
    paths = sorted(HERE.glob("sample-*.json.gz"))
    assert paths
    for p in paths:
        key=p.name[len("sample-"):]
        raw=gzip.decompress(p.read_bytes())
        reopened=load(HERE/("native-"+key))
        assert hashlib.sha256(raw).hexdigest()==reopened["verified_sha256"]
        data = json.loads(raw)
        assert data["recipe"]["commit"] == compiler["measured_source"]
        assert data["driver_sha256"] == product["native_files"][product["compiler_driver"]]
        summary=check(data,reopened)
        if (HERE/("summary-"+key.removesuffix(".gz"))).exists():
            assert summary==load(HERE/("summary-"+key.removesuffix(".gz")))
        print(key,[(phase,round(summary[phase]["paired_median"],3),round(summary[phase]["max_storage_ratio"],4)) for phase in TARGETS])
