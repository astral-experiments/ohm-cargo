"""Verify the shared formatter evidence, rederive all statistics and reject damaged controls."""
from collections import Counter
import copy
import gzip
import hashlib
import json
from fractions import Fraction
from math import comb, isclose, log
from statistics import median
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from analyze import analyze
from disk_scope import collect as check_disk_scope
HEX=re.compile(r"[0-9a-f]{64}")
COMMAND_STAGES=["empty-A","first-B","return-A","return-B","unchanged-B"]
NATIVE_STAGES=["empty-B","first-A","return-B-native","return-A-native","invalid-A","recovered-A","unchanged-A"]
TRUE_TESTS=["tests::basic","tests::string_processing","comments::tests::parenthesized_expression"]
def check_native(n):
    comp=Counter();tool=Counter();roles=[]
    for image,krate,types,zflags,argc,digest in n["physical_execs"]:
        assert HEX.fullmatch(digest) and argc>0 and "/" not in image
        if image=="rustc":
            assert krate and re.fullmatch(r"[A-Za-z_][\w]*",krate) and all(f.split("=")[0]=="link-only" for f in zflags)
            assert all(re.fullmatch(r"[A-Za-z0-9,_-]+",t) for t in types)
            cached=any(f not in ("link-only=no","link-only=false","link-only=off") for f in zflags)
            comp["cached" if cached else "full",krate]+=1;role="cached-rustc" if cached else "full-rustc"
        else:
            assert not krate and not types and not zflags
            if image in ("ld.bfd","ld","wild"):role="wild"
            elif image=="collect2":role="collect2"
            else:assert image in ("cc","gcc") or re.match(r".*-gcc(?:-\d+)?$",image);role="cc_or_gcc"
            tool[role]+=1
        roles.append([role,digest])
    for typ in ["full","cached"]:
        assert dict((k,v) for (t,k),v in comp.items() if t==typ)==n[typ]
    assert dict(tool)==n["tools"] and sorted(roles)==n["argv"] and n["threads"]>0 and HEX.fullmatch(n["raw_trace_sha256"])
    if n["created_object_opens"] is None:
        assert n["cgus_opened_for_creation"] is None
    else:
        ids=set()
        for name,digest,write,create,fd in n["created_object_opens"]:
            assert name.endswith(".rcgu.o") and "/" not in name and HEX.fullmatch(digest) and digest not in ids
            assert write in ("O_RDWR","O_WRONLY") and create=="O_CREAT" and fd>=0
            ids.add(digest)
        assert len(ids)==n["cgus_opened_for_creation"]

def check(data,cfg,mat):
    ords=cfg["pairs"];seed=cfg["seed"]
    ranking=sorted(range(1,13),key=lambda i:hashlib.sha256(f"{seed}\n{i}".encode()).digest())
    assert len(ords)==12 and ords==[["P","Q"] if i in ranking[:6] else ["Q","P"] for i in range(1,13)]
    run=[f"n{i:02d}-{a}" for i,ab in enumerate(ords,1) for a in ab]
    assert cfg["order"]==["admit-P","admit-Q",*run,"post-Q","post-P"]
    assert set(run)==set(data["slots"]) and set(data["controls"])=={"admit-P","admit-Q","post-P","post-Q"}
    assert set(data["slot_receipts"])==set(cfg["order"])
    assert data["protocol_manifest"]=="8644de8014088c0bed294eaf900c89ab25d0f4bb36a784728647c7526e4165fd"
    assert data["root_sources"]=={a:cfg[a] for a in "AB"} and len(data["listed_tests"])==len(set(data["listed_tests"]))==53
    assert set(TRUE_TESTS)<=set(data["listed_tests"])
    table=data["ordered_typed_inventory"];assert len(table)==216
    assert len({json.dumps(x) for x in table})==216
    p,q=[mat["paired_rust_products"][a]["rust_payload_files"] for a in "PQ"]
    assert len(p)==len(q)==55 and p.keys()==q.keys() and sorted(k for k in p if p[k]!=q[k])==mat["changed_rust_files"]
    assert len(mat["changed_rust_files"])==1 and "/librustc_driver" in mat["changed_rust_files"][0]
    assert data["drivers"]==dict(P=p[mat["changed_rust_files"][0]],Q=q[mat["changed_rust_files"][0]])
    assert data["cargo"]=="1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add" and data["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    assert all(data["elf_cas"][r]["bytes"]>0 and HEX.fullmatch(data["elf_cas"][r]["sha256"]) for r in "AB")
    allcounts=Counter();cold=set();physical={}
    for family in ["slots","controls"]:
        for slot,rows in data[family].items():
            arm=slot[-1];control=family=="controls"
            assert set(rows)==set(NATIVE_STAGES if control else COMMAND_STAGES)
            subject=data["slot_receipts"][slot];assert subject["driver"]==data["drivers"][arm]
            assert subject["product"]==mat["paired_rust_products"][arm]["source_receipt"]
            for name,x in rows.items():
                allcounts["cargo"]+=1
                for k in ["cargo_stdout","cargo_stderr","row_sha256"]:assert HEX.fullmatch(x[k])
                assert x["wall_ns"]>0 and x["user_s"]>=0 and x["system_s"]>=0
                assert x["exit"]==(101 if name=="invalid-A" else 0)
                for k in ["usage_before","usage_after"]:
                    v=x[k];assert all(v[t]>f*2**30 for t,f in [("memory",52),("home",140),("scratch",133)])
                    assert v["private"]>650*1024**2
                assert control==("native" in x)
                if control:
                    check_native(x["native"]);allcounts["physically_traced"]+=1
                if name=="invalid-A":
                    assert x["diagnostics"]==[["E0308","mismatched types",[["crates/ruff_python_formatter/src/lib.rs",410,45]]]]
                    allcounts["invalid"]+=1
                    continue
                if name.endswith("-native"):
                    n=x["native"];assert n["full"]=={v:1 for v in ["ruff_db","ruff_python_ast","ruff_python_formatter","ruff_python_parser"]} and n["cached"]=={} and n["tools"]=={"cc_or_gcc":1,"collect2":1,"wild":1}
                    physical[slot+" "+name]=n["cgus_opened_for_creation"]
                rev=x["revision"];assert x["elf"]==data["elf_cas"][rev]["sha256"]
                assert rev==("B" if name in ["empty-B","first-B","return-B","return-B-native","unchanged-B"] else "A")
                assert (x["git_ns"]>0)==(name in ["first-A","first-B","return-A","return-B","return-A-native","return-B-native"])
                dirty=x["dirty"];assert dirty==sorted(set(dirty)) and set(dirty)<=set(range(216))
                if name.startswith("return-"):assert sorted(table[k][1] for k in dirty)==["ruff_db","ruff_python_ast","ruff_python_formatter","ruff_python_parser"]
                if name.startswith("unchanged-"):assert not dirty
                if name.startswith("empty-"):
                    assert len(dirty)==216 and x["complete_suite"]==[51,0,2]
                    allcounts["empty_full_suites"]+=1;cold.add((arm,rev,x["elf"]))
                else:assert x["complete_suite"] is None
                assert set(x["representative_tests"])==set(TRUE_TESTS) and all(HEX.fullmatch(o) for v in x["representative_tests"].values() for o in v)
                allcounts["individual_test_passes"]+=3
                for size,t in x["size_oracle"].items():
                    good=int(size)==(64 if rev=="A" else 56);assert t["exit"]==(0 if good else 1)
                    assert ("E0308" in t["diagnostic_codes"])== (not good)
                    allcounts["size_accepted" if good else "size_rejected_E0308"]+=1
                assert set(x["size_oracle"])=={"64","56"}
                hist=x["physical_block_histogram"]
                assert len({tuple(v[:3]) for v in hist})==len(hist) and all(a>=0 and a%512==0 and m>0 and k>0 and c>0 for a,m,k,c in hist)
                assert sum(a*c for a,m,k,c in hist)==x["incremental_allocated_bytes"]>0
                assert sum(k*c for a,m,k,c in hist)==x["storage_paths"] and sum(c for a,m,k,c in hist)==x["storage_inodes"]
                assert HEX.fullmatch(x["storage_ledger_sha256"]) and HEX.fullmatch(x["test_inventory"])
    assert allcounts==dict(cargo=148,physically_traced=28,invalid=4,empty_full_suites=28,individual_test_passes=432,size_accepted=144,size_rejected_E0308=144)
    assert len(cold)==4 and all((a,r,data["elf_cas"][r]["sha256"]) in cold for a in "PQ" for r in "AB")
    assert len(physical)==8
    return allcounts,physical

def check_maths(data, cfg, report):
    # Use bit masks, log(x/y) and exact sign probabilities independently of analyze.py.
    orders=cfg["pairs"];n=len(orders)
    masks=[x for x in range(1<<n) if x.bit_count()==6]
    assert len(masks)==924
    for phase,metrics in report["phase_metrics"].items():
        for metric,result in metrics.items():
            def value(slot):
                r=data["slots"][slot][phase]
                if metric=="wall_s":return r["wall_ns"]/1e9
                if metric=="cpu_s":return r["user_s"]+r["system_s"]
                if metric=="git_s":return r["git_ns"]/1e9
                if metric=="with_git_s":return (r["wall_ns"]+r["git_ns"])/1e9
                assert metric=="incremental_allocated_bytes"
                return r["incremental_allocated_bytes"]
            p=[value(f"n{i:02d}-P") for i in range(1,13)]
            q=[value(f"n{i:02d}-Q") for i in range(1,13)]
            assert result["parent"]==p and result["candidate"]==q and result["parent_median"]==median(p) and result["candidate_median"]==median(q)
            paired=[a/b for a,b in zip(p,q)];ordered=sorted(paired)
            assert result["paired_ratios"]==paired and result["median_ratio"]==median(paired)
            for field,k in [("marginal95",3),("simultaneous_two_endpoints",2)]:
                it=result[field]
                assert it["range"]==[ordered[k-1], ordered[-k]] and it["marginal_coverage"]==float(1-Fraction(2*sum(comb(n,i) for i in range(k)),2**n))
            pos=sum(x>2 for x in paired);assert pos==result["above_two"]
            one=Fraction(sum(comb(n,i) for i in range(min(pos,n-pos)+1)),2**n)
            assert result["paired_sign_p_against_two"]==min(1,float(2*one))
            v=[log(r) if order[0]=="P" else -log(r) for order,r in zip(orders,paired)]
            actual=sum(1<<i for i,o in enumerate(orders) if o[0]=="P")
            score=lambda mask:abs(sum(d if mask>>i&1 else -d for i,d in enumerate(v)))
            observed=score(actual)
            extreme=sum(score(m)>=observed-1e-12 for m in masks)
            assert result["randomization_extreme"]==extreme and result["balanced_randomization_p"]==extreme/924
            for a in ["P","Q"]:assert result["by_order_median_ratio"][a+"-first"]==median(z for z,o in zip(paired,orders) if o[0]==a)
    qualified=all(report["phase_metrics"][p]["wall_s"]["simultaneous_two_endpoints"]["range"][0]>2
                  and report["phase_metrics"][p]["wall_s"]["balanced_randomization_p"]<.05
                  and report["phase_metrics"][p]["wall_s"]["paired_sign_p_against_two"]<.05 for p in ["return-A","return-B"])
    assert qualified==report["both_wall_endpoints_exceed_two"]

def scanner(path,body):
    banned=tuple(b"".join(p) for p in [
        (b"/home/",b"dev-",b"user"), (b"/mnt/",b"dev",b"box"), (b"/run/",b"user/"),
        (b"char",b"lie-",b"ohm-"), (b"github_",b"pat_"), (b"BEGIN ",b"PRIVATE KEY"), (b"gh",b"p_"),
        (b"/root/",b".cache"),(b"/Users/",b"char",b"lie")])
    for marker in banned:
        assert marker not in body,(path.name,marker)

def main():
    declared={}
    for line in (HERE/"SHA256SUMS").read_text().splitlines():
        expected,name=line.split("  ");file=HERE/name;assert file.is_file() and not file.is_symlink() and name not in declared
        body=file.read_bytes();assert hashlib.sha256(body).hexdigest()==expected,name
        scanner(file,gzip.decompress(body) if name.endswith(".gz") else body);declared[name]=expected
    actual={str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="SHA256SUMS"}
    assert actual==set(declared)
    load=lambda n:json.loads((HERE/n).read_bytes())
    cfg=load("schedule.json");mat=load("materials.json")
    raw=gzip.decompress((HERE/"observations.json.gz").read_bytes());data=json.loads(raw)
    for key,file in [("protocol_manifest","registration-members.sha256"),("analyzer_sha256","analyze.py"),("schedule_sha256","schedule.json")]:
        assert data[key]==declared[file]
    historical={line.split("  ")[1]:line.split("  ")[0] for line in (HERE/"registration-members.sha256").read_text().splitlines()}
    assert historical["PLAN.md"]==declared["registration.md"] and historical["analyze.py"]==declared["analyze.py"] and historical["schedule.json"]==declared["schedule.json"]
    counts,physics=check(data,cfg,mat)
    assert check_disk_scope(data)==load("disk-scope.json")
    derived=json.loads(json.dumps(analyze(data,cfg)));derived["observations_sha256"]=hashlib.sha256(raw).hexdigest()
    assert derived==load("statistics.json")
    check_maths(data,cfg,derived)
    for label in ["clock","missing-slot","wild","allocated","error","source"]:
        bad=copy.deepcopy(data)
        if label=="clock":bad["slots"]["n01-P"]["return-A"]["wall_ns"]+=1048575
        if label=="missing-slot":del bad["slots"]["n02-Q"]
        if label=="wild":bad["controls"]["admit-P"]["return-B-native"]["native"]["tools"]["wild"]=0
        if label=="allocated":bad["slots"]["n03-Q"]["first-B"]["incremental_allocated_bytes"]+=512
        if label=="error":bad["controls"]["post-Q"]["invalid-A"]["diagnostics"][0][0]="E9999"
        if label=="source":bad["slots"]["n10-P"]["return-B"]["elf"]=bad["elf_cas"]["A"]["sha256"]
        try:
            check(bad,cfg,mat)
            new=json.loads(json.dumps(analyze(bad,cfg)));new["observations_sha256"]=derived["observations_sha256"]
            assert new==derived
        except (AssertionError,KeyError):continue
        raise ValueError("corruption accepted: "+label)
    print(json.dumps({"valid":True,"counts":counts,"cgu_paths":physics,"two_return_directions_over_two":derived["both_wall_endpoints_exceed_two"],"mutation_rejections":6},sort_keys=True))
if __name__=="__main__":main()
