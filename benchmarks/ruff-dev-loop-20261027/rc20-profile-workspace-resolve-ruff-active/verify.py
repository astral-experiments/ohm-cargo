"""Verify stored native and Cargo output without a toolchain or access to the original filesystem."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import tomllib

HERE=Path(__file__).resolve().parent
P=runpy.run_path(str(HERE/"project.py"))
N=runpy.run_path(str(HERE/"native_execs.py"))
check=P["check"]
sha=P["sha"]
read=P["read"]
serialize=P["serialize"]
TAGS=["01-original","02-repeat","03-reverse","04-repeat","05-clean-edited","06-invalid","07-clean-invalid","08-restored","09-final"]
NAMES=["invalid_range_deserialization","range_serialization","size_serialization"]
ORIGINAL="fe73259b0f12928fcce37ab700ff2b52656b7a18c1c45f075c7b4272955f2dee"
EDITED="a2a35c107b1ea2ed5891cf759effdedeeac0b0d044cc762a70c3e1822b2ffe09"
HEX=re.compile(r"[a-f0-9]{64}")
A="967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9"
B="80356b8237d3089d3360b6de5abfc64a17e4b8d3f0ec1fb64e09254418b5c5e5"


def verify_projected_native(command,mode):
    row=command["row"]
    streams=command["streams"]
    events=N["native_execs"](streams["exec"])
    check(len(events)==len(row["events"]), "native event count")
    for projected,raw in zip(events,row["events"],strict=True):
        check(HEX.fullmatch(raw["argv_sha256"]), "raw command digest")
        check({k:v for k,v in projected.items() if k!="argv_sha256"}=={k:v for k,v in raw.items() if k!="argv_sha256"}, "successful exec roster and argv shape")
        start=streams["exec"].splitlines()[projected["lines"][0]-1]
        if projected["program"]=="ld.bfd":
            check('execve("<sdk>/'+P["WILD"]+'",' in start,"stock Wild path")
        if projected["program"]=="rustc":
            check('execve("<arena>/ru/toolchains/ohm/bin/rustc",' in start,"selected rustc")
    runargs=(["check","-p","ruff_text_size"] if mode=="check" else ["test","-p","ruff_text_size","--features","serde","--test","serde","--no-run"])
    runargs+=["--locked","--offline","--message-format=json"]
    check([e['cargo_args'] for e in events if e["program"]=="cargo"]==[["+ohm"]+runargs,runargs],"actual Cargo invocation")
    comp=sorted(e["crate"] for e in events if N["is_compile"](e))
    links=sorted(e["program"] for e in events if N["is_link"](e))
    check(comp==row["compiles"] and links==row["links"],"compiled/linked names")
    return events


def signature(output):
    return [v for v in map(json.loads,output.splitlines()) if v["reason"]=="compiler-message"]


def source():
    subjects=read(HERE/"subjects.json")
    original=gzip.decompress((HERE/"ruff-Cargo.toml.gz").read_bytes())
    lock=gzip.decompress((HERE/"ruff-Cargo.lock.gz").read_bytes())
    hunk=(HERE/"active-dev.hunk").read_bytes()
    check(original.count(hunk)==1 and b"[profile.dev]" in hunk,"complete six-line profile hunk")
    historical=(HERE/"active-dev.patch").read_text()
    check(("+[profile.dev]\n" in historical) and b"".join(v[1:] for v in historical.encode().splitlines(keepends=True) if v.startswith(b"+") and not v.startswith(b"+++"))==hunk,"patch")
    root=gzip.decompress((HERE/"ruff-Cargo.toml.gz").read_bytes())
    for key,entry in subjects["ruff"]["files"].items():
        f=HERE/entry["file"]
        body=gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes()
        check(len(body)==entry["bytes"] and sha(body)==entry["sha256"] and hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()==entry["git_blob"],key)
    check(len(tomllib.loads(lock.decode())["package"])==553,"complete pinned lock")
    check(subjects["physical_image_pairs_verified_as"]=={"A":A,"B":B} and subjects["literal_compiler_commands_equal"] and (subjects["ordered_external_inputs"],subjects["independent_native_files"])==(239,335),"matched PGO subjects")
    check(sha((HERE/"active-ruff-design.md").read_bytes())=="cfaf7b73dd58605ad37df83afcd59c0fead7e3feedd944934722d7079010e344","design")
    check(sha((HERE/"native_execs.py").read_bytes())=="6a2137f2fd5524af8ef9f2b771881a27571e707ae11d10bbaec1eb36b4367a68","complete exec parser")
    lib=(HERE/"ruff-lib.rs").read_bytes()
    return dict(original=sha(root),edited=sha(root.replace(hunk,b"")),lib=sha(lib),
                invalid=sha(lib+b"\nconst OHM_PROFILE_ERROR_CONTROL: () = 17;\n"),lock=sha(lock))


def expected_lookup(arm,mode,tag):
    if tag[:2] in ("01","05","07"):return (1,0)
    if tag[:2] in ("02","04","06","09"):return (0,1)
    if tag=="03-reverse" and mode=="check": return (1,1) if arm=="A" else (0,2)
    return (1,0) if arm=="A" else (0,1)


def typed_operand_multiset(arm,command):
    """Map only the two recorded compiler-output namespace fields, keeping every typed value."""
    namespace={"A":"v2-df4191604c6bcefb","B":"v2-8c567eab1dbde7aa"}[arm]
    def shape(path):
        return path.replace("/"+namespace+"/","/<image-namespace>/")
    result=[]
    for event in map(json.loads,command["streams"]["stdout"].splitlines()):
        if event["reason"]=="compiler-artifact":
            event["filenames"]=[shape(x) for x in event["filenames"]]
            if event.get("executable"):
                event["executable"]=shape(event["executable"])
        elif event["reason"]=="build-script-executed":
            event["out_dir"]=shape(event["out_dir"])
        result.append(json.dumps(event,sort_keys=True))
    return collections.Counter(result)


def compare_records(data,product_rows):
    recalculated=P["compare_products"](data)
    check(product_rows==recalculated,"bijective typed paths and whole-file raw SHA")
    for label,rows in product_rows.items():
        left,right=label.split(" :: ")
        mismatch=[r for r in rows if not r["exact_bytes"]]
        if left.split("/")[1].startswith("test"):
            check(len(rows)==24,"24 physical test artifacts")
            expected=set()
            if left[0]!=right[0]:
                expected={(n,ext) for n in ("ruff_text_size","serde_core","serde","serde_test") for ext in (".rlib",".rmeta")}
            elif ("05-clean-edited" in right and "03-reverse" in left) or ("08-restored" in right and "01-original" in left):
                expected={("ruff_text_size",".rlib")}
            check({(r["id"][1],r["id"][3]) for r in mismatch}==expected,"exact reported intermediate differences")
        else:
            check(not mismatch,"same-hash check products")
    return len(product_rows)


def verify(data,index,comparisons,policy,mutated=False):
    term=read(HERE/"complete.json")
    check(sha((HERE/"complete.json").read_bytes())=="f8caff67655b0bda1d2ac32ff29b567dffe31b7b15880feb1b625ce9567fb40a","original terminal")
    check(index["v1"]=={} and data["v1"]=={"A":{"commands":{}}},"unwritten v1 output")
    v2=data["v2"]["A"]
    check(set(v2["commands"])=={"check-01-original","check-02-repeat","check-03-reverse","test-01-original","test-02-repeat"} and "AssertionError: ('check', '03-reverse'" in v2["worker_stderr"],"unscored v2")
    old=v2["commands"]["check-03-reverse"]
    check(old["row"]["exit"]==0 and old["row"]["hit"] is True and P["markers"](old["streams"]["stderr"])==([1],[1108]),"v2 original predicate")
    for label,cmd in v2["commands"].items():
        verify_projected_native(cmd,label.split("-")[0])
    expected={mode+"-"+tag for tag in TAGS for mode in ["check","test"] if mode!="test" or "invalid" not in tag}
    all_diagnostics=[]
    result={}
    for arm,terminal,cargo in zip("AB",term["arms"],[A,B],strict=True):
        commands=data["v3"][arm]["commands"]
        check(set(commands)==set(terminal["rows"])==expected and terminal["arm"]==arm and terminal["cargo"]==cargo,"complete command set")
        totals=collections.Counter()
        for name in sorted(commands):
            cmd=commands[name]
            row=cmd["row"]
            streams=cmd["streams"]
            mode,tag=name.split("-",1)
            invalid="invalid" in tag
            edited=tag[:2] in ("03","04","05","06","07")
            fresh=tag[:2] in ("02","04","09")
            check((row["manifest"],row["lib"],row["lock"])==(policy["edited" if edited else "original"],policy["invalid" if invalid else "lib"],policy["lock"]), "actual source and unchanged lock")
            full,hits=P["markers"](streams["stderr"])
            check((len(full),len(hits))==expected_lookup(arm,mode,tag) and (full,hits)==(cmd["full_lines"],cmd["hit_lines"]) and (len(full),len(hits),bool(hits and not full))==(row["full_workspace_resolutions"],row["cache_hits"],row["hit"]),"every full/hit event")
            events=verify_projected_native(cmd,mode)
            totals["successful_execs"]+=len(events)
            totals["split_completed_execs"]+=sum(e["lines"][0]!=e["lines"][1] for e in events)
            launches=collections.Counter(e["program"] for e in events)
            expected_links=(6 if not fresh and mode=="test" else 0)
            check([launches[x] for x in ("cc","collect2","ld.bfd")]==[expected_links]*3 and len(row["links"])==expected_links,"real driver/stock link chain")
            check(len(row["compiles"])==(0 if fresh else (1 if mode=="check" else 15)),"real source compile count")
            check(launches["build_script_build"]==(4 if mode=="test" and not fresh else 0),"build script invocations")
            totals.update({"commands":1,"compiles":len(row["compiles"]),"stock_wild":expected_links,"gcc":launches["cc"],"collect2":launches["collect2"],"rustc_processes":launches["rustc"],"build_scripts":launches["build_script_build"],"full_resolutions":len(full),"cache_lookups_hit":len(hits)})
            parsed=list(map(json.loads,streams["stdout"].splitlines()))
            artifacts=[r for r in parsed if r["reason"]=="compiler-artifact"]
            check(sorted([r["target"]["name"],r["fresh"]] for r in artifacts)==row["artifacts"], "all unit freshness")
            check(parsed[-1]=={"reason":"build-finished","success":not invalid} and row["exit"]==(101 if invalid else 0),"native status and JSON verdict")
            check(len(artifacts)==(0 if invalid else (15 if mode=="test" else 1)),"all artifacts")
            check(all(a["fresh"]==fresh for a in artifacts),"no-op vs dirty compile outputs")
            selected=[a for a in artifacts if a["target"]["name"]=="ruff_text_size" or a.get("executable")]
            for a in selected:
                check((a["profile"]["opt_level"],a["profile"]["debuginfo"])==("0" if edited else "1","line-tables-only"),"effective emitted optimization")
            check(sum(j["reason"]=="build-script-executed" for j in parsed)==(4 if mode=="test" else 0),"all typed build script outputs")
            diag=signature(streams["stdout"])
            if invalid:
                totals["expected_failures"]+=1
                check([x["message"]["level"] for x in diag]==["error","failure-note"],"error/failure note")
                m=diag[0]["message"]; s,=[span for span in m["spans"] if span["is_primary"]]
                check(m["code"]["code"]=="E0308" and m["message"]=="mismatched types" and (s["line_start"],s["line_end"],s["byte_start"],s["byte_end"],s["column_start"],s["column_end"])==(38,38,1344,1346,39,41) and s["file_name"]=="crates/ruff_text_size/src/lib.rs" and s["is_primary"],"negative source location")
                all_diagnostics.append((diag,[line for line in streams["stderr"].splitlines() if not re.match(r"^\s*\d+\.\d+s DEBUG ",line)]))
                check(row["compiles"]==["ruff_text_size"] and len(P["typed_products"](cmd))==0,"real dirty type error")
            else:
                check(not diag and not row["errors"],"success has no diagnostics")
            if mode=="test":
                tests=[r for r in artifacts if r.get("executable")]
                check(len(tests)==1 and tests[0]["target"]["name"]=="serde" and tests[0]["target"]["kind"]==["test"],"selected real serde integration executable")
                raw=row["products"][tests[0]["executable"].removeprefix("<arena>/")]
                check(raw==row["exe"]==(EDITED if edited else ORIGINAL),"original/edited/clean whole executable")
                check(row["names"]==NAMES and row["verdict"]=="passed" and streams["test-list"]=="".join(n+": test\n" for n in NAMES)+"\n3 tests, 0 benchmarks\n","complete inventory")
                check(re.fullmatch(r"\nrunning 3 tests\n"+"".join("test "+n+r" \.\.\. ok\n" for n in NAMES)+r"\ntest result: ok\. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in [\d.]+s\n\n",streams["test-verdict"]),"actual three executed tests")
                totals.update({"harnesses":1,"test_cases_passed":3})
            if not mutated:
                check(sha(serialize(row))==terminal["rows"][name]==index["v3"][arm+"/"+name+"/row.json"]["sha256"],"unchanged raw row bytes")
                for k in ("stdout","stderr","exec"):
                    check(index["v3"][arm+"/"+name+"/"+k]["sha256"]==row["trace" if k=="exec" else k],"raw stream digests")
                if mode=="test":
                    for k in ("test-list","test-verdict"):
                        check(sha(streams[k].encode())==index["v3"][arm+"/"+name+"/"+k]["sha256"],"native result streams")
        result[arm]=dict(totals)
    check(len(all_diagnostics)==4 and all(x==all_diagnostics[0] for x in all_diagnostics),"entire rendered diagnostic and stderr differ")
    check(all(x["compiles"]==66 and x["stock_wild"]==24 and x["expected_failures"]==2 for x in result.values()),"matched native workload")
    for name in expected:
        a,b=[data["v3"][arm]["commands"][name] for arm in "AB"]
        check(typed_operand_multiset("A",a)==typed_operand_multiset("B",b),"all JSON source/profile/build-script/diagnostic fields")
        check(all(a["row"].get(k)==b["row"].get(k) for k in ("manifest","lib","lock","exit","compiles","links","artifacts","errors","names","exe","verdict")),"cross-arm inputs and outcomes")
    return {"arm_totals":result,"complete_typed_multisets_matched":len(expected),"full_product_comparisons":compare_records(data,comparisons),"exact_diagnostics_including_rendering":4,
            "original_test_elf_sha256":ORIGINAL,"edited_test_elf_sha256":EDITED,
            "unsuccessful_setup":{"v1_recorded_cargo_study_commands":0,"v1_returned_stderr_retained_as_file":False,"v2_recorded_cargo_study_commands":5,"v2_last_full_and_cached_lines":[1,1108]},
            "recorded_raw_files":{k:len(index[k]) for k in ["v1","v2","v3"]}}


def run():
    index=read(HERE/"raw-file-index.json.gz")
    data=read(HERE/"streams.json.gz")
    comparisons=read(HERE/"product-comparisons.json.gz")
    policy=source()
    result=verify(data,index,comparisons,policy)
    def alter(name,where,field,change):
        old=where[field]
        where[field]=change(old)
        try:
            verify(data,index,comparisons,policy,mutated=True)
        except (ValueError,KeyError) as err:
            result["rejected_mutations"][name]=str(err)
        else:
            raise ValueError("unexpected acceptance: "+name)
        finally:
            where[field]=old
    result["rejected_mutations"]={}
    a=data["v3"]["A"]["commands"]
    b=data["v3"]["B"]["commands"]
    alter("earlier full resolution hidden behind a later cache hit",a["check-03-reverse"]["streams"],"stderr",lambda s:s.replace(P["FULL"],"removed_full_entry:",1))
    alter("cold ELF substituted for the observed edited product",a["test-05-clean-edited"]["row"],"exe",lambda _:ORIGINAL)
    alter("one successful stock process removed",b["test-08-restored"]["row"],"events",lambda v:[r for i,r in enumerate(v) if i!=next(j for j,q in enumerate(v) if q["program"]=="ld.bfd")])
    alter("negative span moved",a["check-07-clean-invalid"]["streams"],"stdout",lambda s:s.replace('"column_start":39','"column_start":38',1))
    alter("test run falsely passed with one missing name",b["test-04-repeat"]["streams"],"test-verdict",lambda s:s.replace("test size_serialization ... ok\n",""))
    key="A/test-03-reverse :: A/test-05-clean-edited"
    alter("raw intermediate mismatch normalized",comparisons,key,
          lambda vals:[dict(r,exact_bytes=True) if not r["exact_bytes"] else r for r in vals])
    alter("discarded a source stage",data["v3"]["A"],"commands",lambda v:{k:q for k,q in v.items() if k!="check-06-invalid"})
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write",action="store_true")
    args=parser.parse_args()
    result=run()
    if args.write:
        P["write"](HERE/"verification.json",result)
    else:
        check(result==read(HERE/"verification.json"),"sealed verifier result")
    print(json.dumps(result,indent=2,sort_keys=True))
