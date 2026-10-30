#!/usr/bin/env python3
import argparse
import collections
import copy
import gzip
import hashlib
import json
from pathlib import Path

CASES={"inlay_hints::default_inlay_hints","notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"}
LIST="76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52"
def check(w,x,cust):
    assert w["rust_source"]=="ad005f99d0b51fd62b5c237bc13b31b371a1686e" and x["rust_source"]=="b9b4105463dd4a9a16f39509d868aa15d5f96e00"
    assert w["cargo"]==x["cargo"]=="96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5" and w["cargo_source"]==x["cargo_source"]=="84af87848a5a952ba61ae6a2cc5b22da24130200"
    assert w["wild"]==x["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    assert w["driver"]!=x["driver"] and w["full_sdk_receipt"]!=x["full_sdk_receipt"]
    changed={name for name,value in w["tools"].items() if value!=x["tools"][name]};assert len(changed)==1 and next(iter(changed)).startswith("librustc_driver")
    for key in ("source","historical_edit","source_hashes","command_binding","typed_digest","cpu","registry_sha","all_elf_bodies"):
        assert w[key]==x[key],key
    assert w["source"]=="93526150df078af7dd8fc4226cdcc469539d2001" and w["historical_edit"]=="1b9310471b7d1178633e58ee63808522609db887"
    assert cust["physical_arms_readonly"] and cust["outer_mount_tmpfs"]
    assert [cust[k]["raw_regulars"] for k in ("W","X")]==[19844,19590]
    n=collections.Counter();trace_count=0
    for key,j in (("W",w),("X",x)):
        assert cust[key]["terminal"]==j["terminal"] and j["ordinary_empty_cmp"]
        gold=cust["bodies"]["original"]["sha256"];edit=cust["bodies"]["edited"]["sha256"];valid=cust["bodies"]["provider"]["sha256"]
        assert len({gold,edit,valid})==3 and j["all_elf_bodies"]=={v["sha256"]:v["bytes"] for v in cust["bodies"].values()}
        assert len(j["visits"])==15
        for label,v in j["visits"].items():
            trace_count+=v["raw"]["per_thread_files"];assert v["raw"]["per_thread_files"] and len(v["raw"]["per_thread_manifest"])==64 and v["link_only"]==0
            if label in ("06-invalid","11-malformed","13-forced-malformed"):
                assert v["cargo"]==101 and v["runtime"] is None and v["e2e_wild"]==(0 if label=="06-invalid" else 1)
                assert v["e0308_22"]==(label=="06-invalid");n["expected_cargo_errors"]+=1
                continue
            assert v["cargo"]==0 and v["typed"]==300 and v["e2e_wild"]==1
            if label in ("09-valid","10-forced-valid"):
                assert v["runtime"]==83 and v["elf"]==valid;n["runtime83"]+=1
            else:
                assert v["runtime"]==0 and v["listing"]==LIST and set(v["checked_cases"])==CASES and len(v["coherent_reader_rmeta"])==64;n["healthy"]+=1
                edited="edited" in label or label=="07-recovery";assert v["elf"]==(edit if edited else gold) and v["selected_source"]==(["edited"] if edited else ["original"])
            if label in ("01-original-empty","15-edited-independent-empty"):
                assert (v["fresh"],v["full"],v["wild"])==(0,303,48);n["complete_empty"]+=1
        for case in ("02-unchanged","03-unchanged"):
            r=j["visits"][case];assert (r["full"],r["fresh"],r["wild"],r["e2e_wild"])==((4,277,2,1) if key=="W" else (3,283,2,1))
            nam={n:k for n,k in r["physical_compiler_names"]};assert nam==({"build_script_build":1,"e2e":1,"unicode_names2":1}|({"portable_atomic":1} if key=="W" else {}))
    assert dict(n)=={"healthy":20,"complete_empty":4,"expected_cargo_errors":6,"runtime83":4}
    return {"commands":30,"per_thread_trace_files":trace_count,"control_unchanged":[4,0,2],"candidate_unchanged":[3,0,2],"expected_cargo_errors":6,"checked_healthy_elfs":20,"valid_provider_runtime83":4,"complete_empty":4,"same_full_elf_bytes":cust["bodies"]["edited"]["bytes"],"full_edited_sha256":cust["bodies"]["edited"]["sha256"]}

def main():
    ap=argparse.ArgumentParser(description="Verify the two 15-command, source-qualified H8 Ruff native histories.");ap.add_argument("--self-test",action="store_true");a=ap.parse_args();p=Path(__file__).resolve().parent
    names=set()
    for line in (p/"SHA256SUMS").read_text().splitlines():
        v,n=line.split("  ");assert n not in names and "/" not in n and hashlib.sha256((p/n).read_bytes()).hexdigest()==v;names.add(n)
    assert names|{"SHA256SUMS"}=={q.name for q in p.iterdir() if q.is_file()}
    c=json.loads((p/"custody.json").read_bytes());data={}
    for arm in ("W","X"):
        raw=gzip.decompress((p/(arm+".json.gz")).read_bytes());j=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==c[arm]["projection"]
        ro=json.loads((p/(arm+"-protection.json")).read_bytes());assert ro["verified_projection"]==c[arm]["projection"] and ro["actual_terminal"]==c[arm]["terminal"] and ro["superblock_readonly"] and ro["writer_or_mapping_references"]==ro["metadata_denials"]==0
        data[arm]=j
    report=check(data["W"],data["X"],c)
    if a.self_test:
        for k in ("lost-full","credit-skipped-link","missed-provider","false-success","wrong-clean","wrong-control"):
            w=copy.deepcopy(data["W"]);x=copy.deepcopy(data["X"])
            if k=="lost-full":x["visits"]["02-unchanged"]["full"]=2
            if k=="credit-skipped-link":x["visits"]["03-unchanged"]["e2e_wild"]=0
            if k=="missed-provider":x["visits"]["09-valid"]["runtime"]=0
            if k=="false-success":x["visits"]["11-malformed"]["cargo"]=0
            if k=="wrong-clean":x["visits"]["15-edited-independent-empty"]["elf"]="0"*64
            if k=="wrong-control":w["cargo"]=x["driver"]
            try:check(w,x,c)
            except AssertionError:continue
            raise AssertionError("accepted "+k)
        report["mutations_rejected"]=6
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
