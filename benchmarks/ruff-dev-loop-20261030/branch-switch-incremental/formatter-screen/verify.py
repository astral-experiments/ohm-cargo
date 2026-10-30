"""Verify the complete portable two-pair screen and exercise three bad-observation mutations."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import sys
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from project import main as project
def read(n):
    return json.loads((here/n).read_bytes())
def check(r,b):
    assert list(r["run_order"])==["admit-P","admit-Q","pair1-P","pair1-Q","pair2-Q","pair2-P"]
    assert r["protocol"]=="6c7029547d0a70724df5769d3e03dd5d37f40817566afd5ee581ebf1d8ec5e1b"
    assert b["counts"]==dict(traced=4,ordinary=30,representative_passes=96,size_accepted=32,size_rejected_E0308=32)
    assert all(x==[51,0,2] for x in b["empty_suites_pass_fail_ignore"].values())
    for arm in "PQ":
        assert b["diagnostics"][arm]==[["E0308","mismatched types",[["crates/ruff_python_formatter/src/lib.rs",410,45]]]]
        aa=r["installs"]["admit-"+arm]["rows"]
        for rev in "AB":
            c=aa["return-"+rev+"-native"]["native"]
            assert c["full"]=={s:1 for s in ["ruff_db","ruff_python_ast","ruff_python_formatter","ruff_python_parser"]} and not c["cached"]
            assert c["tools"]=={"cc_or_gcc":1,"collect2":1,"wild":1} and c["object_writes"]=={"P":310,"Q":1}[arm]
            for i in (1,2):
                rows=r["installs"][f"pair{i}-{arm}"]["rows"];q=rows["return-"+rev]
                assert q["matches_clean_elf"] and q["elf"]==(rows["empty-A"] if rev=="A" else aa["empty-B"])["elf"]
                assert len(q["dirty"])==4 and q["typed_count"]==216 and q["test_count"]==53 and q["real_elapsed_ns"]>0
    assert all(v["numerical_gate"] and v["all_elf_equal"] for v in r["visits"].values())
    for rev in "AB":
        for i,row in enumerate(r["visits"][rev]["pairs"],1):
            p,q=[r["installs"][f"pair{i}-{a}"]["rows"]["return-"+rev] for a in "PQ"]
            assert row["wall_ratio_P_over_Q"]==p["real_elapsed_ns"]/q["real_elapsed_ns"]
            assert row["whole_cpu_ratio_P_over_Q"]==(p["real_user_s"]+p["real_sys_s"])/(q["real_user_s"]+q["real_sys_s"])
def main():
    for line in (here/"SHA256SUMS").read_text().splitlines():
        h,name=line.split("  ");assert hashlib.sha256((here/name).read_bytes()).hexdigest()==h,name
    r=read("verified-raw.json");b=read("behavior.json");check(r,b)
    assert project(here/"verified-raw.json")==read("summary.json")
    for what in ("clock","native","error"):
        x,y=copy.deepcopy(r),copy.deepcopy(b)
        if what=="clock":x["installs"]["pair2-P"]["rows"]["return-B"]["real_elapsed_ns"]+=1
        if what=="native":x["installs"]["admit-Q"]["rows"]["return-A-native"]["native"]["tools"]["wild"]=0
        if what=="error":y["diagnostics"]["P"][0][0]="E0000"
        try:check(x,y)
        except AssertionError:continue
        raise ValueError("corruption accepted: "+what)
    print("34 Cargo visits and all three independent mutations verified")
if __name__=="__main__":main()
