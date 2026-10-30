"""Check the pinned candidate's published source, compiler, runtime and collector outcomes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
E = "05efba7a06f5bb71d1efb4b86805800f8b810779"
O = "7277e6cdaba44c43294a07c0661fc8e69fd8e3e7"
def read(name):
    return json.loads((here/name).read_bytes())
def check(d):
    ty, suites, training, bad = (d[n] for n in ("ty","suites","training","invalid"))
    assert ty["rust"] == suites["subject"] == bad["subject"]["rust"] == E
    assert ty["cargo"] == bad["subject"]["cargo"] == O
    phases = [v for _,v in sorted(ty["phases"].items())]
    assert len(phases) == 15 and sum(v["raw_exec_files"] for v in phases) == 30186
    assert all(v["raw_exec_files"] > 0 and len(v["raw_exec_sha256"]) == 64 for v in phases)
    assert [v["cargo"] for v in phases] == [101 if i in (6,11,13) else 0 for i in range(1,16)]
    assert [v["e2e_wild"] for v in phases] == [int(i!=6) for i in range(1,16)]
    assert all(phases[i-1]["fresh"] == 0 and phases[i-1]["typed"]==300 for i in (1,15))
    assert all(v["cached_rustc"] == 0 for v in phases)
    for i in (1,2,3,4,5,7,8,12,14,15):
        assert phases[i-1]["list"] == phases[0]["list"] and phases[i-1]["case_passes"] == 3
    original, edited, provider = [phases[i-1]["elf"] for i in (1,4,9)]
    assert len({original,edited,provider}) == 3
    for expected, visits in [(original,(2,3,8,12,14)),(edited,(5,7,15)),(provider,(10,))]:
        assert all(phases[i-1]["elf"] == expected for i in visits)
    programs = {x["visit"]:x for x in ty["programs"]}
    assert set(programs) == {4,9,12,15}
    assert all(p["sha256"] == phases[i-1]["elf"] and p["list_exit"] == (83 if i==9 else 0) for i,p in programs.items())
    assert programs[4]["bytes"] == programs[15]["bytes"] == 214113280
    expected = {"ohm-checked-dep-info":17,"ohm-relink-assembler-inputs":7,"rdr-public-hash-proc-macro-utf8-subspan":3,"separate-link":8,"ohm-relink-incremental-objects":3}
    assert {s["test"]:s["actual_compilers"] for s in suites["receipts"]} == expected
    assert all(s["exit"]==0 and len(s["trace"])==64 and s["source"] for s in suites["receipts"])
    assert set(training) == {"Debug","Opt"}
    for name, data in training.items():
        assert data["native_exit"]==0 and data["compiler"]==E and data["mode"] == name+"-training-off"
        assert data["wrapped_roots"]==data["actual_roots"]==len(data["archives"])==4
        assert len(data["real_root_argv_sha256"])==4 and data["preparation_dependency_crates"]==306
        assert data["dependency_checked_relink"]==data["dependency_public_api_hash"]==0
        assert all(x["size"]>1_000_000 and len(x["sha256"])==64 for x in data["archives"])
        assert data["images_sha256"]==bad["subject"]["images_sha256"]
    assert bad["verified"] and bad["invalid"]["collector_exit"]==bad["invalid"]["real_root_exit"]==1
    assert bad["invalid"]["diagnostic"]=="E0308" and bad["invalid"]["dependency_crates"]==306
    fix=bad["repair"]
    assert fix["cargo_json_success"] and fix["actual_root_program_compiles"]==1
    assert fix["retained_dependency_archives"]>100 and fix["archive_members"]>=2
    assert fix["elf"]["size"]>1_000_000 and fix["elf"]["first16"].startswith("7f454c46")
    assert fix["rlib"]["size"]>1_000_000 and fix["rlib"]["first16"].startswith("213c617263683e0a")
    assert any(j["matched_final_inode"] and j["exit"]==0 and j["name"] in ("ld","ld.bfd","ld.lld","rust-lld","wild","wild-linker") for j in fix["genuine_final_link"])
    assert [(v["actual"],v["exit"]) for v in fix["product_verdicts"]]==[("0.1.7",0),("0.2.9",0)]

def main():
    for line in (here/"SHA256SUMS").read_text().splitlines():
        h,n=line.split("  ",1)
        assert Path(n).name==n and hashlib.sha256((here/n).read_bytes()).hexdigest()==h
    data={k:read(n) for k,n in {"ty":"ty-server.json","suites":"run-make.json","training":"collector.json","invalid":"invalid-repair.json"}.items()}
    check(data)
    if "--self-test" in sys.argv:
        for kind in ("stale","invalid","provider","missing-link","clean","suite","archive","training","repair"):
            c=deepcopy(data)
            if kind=="stale":c["ty"]["phases"]["04-edited"]["elf"]=c["ty"]["phases"]["01-empty-original"]["elf"]
            if kind=="invalid":c["ty"]["phases"]["06-invalid"]["cargo"]=0
            if kind=="provider":c["ty"]["programs"][2]["list_exit"]=0
            if kind=="missing-link":c["ty"]["phases"]["04-edited"]["e2e_wild"]=0
            if kind=="clean":c["ty"]["phases"]["15-empty-edited"]["fresh"]=1
            if kind=="suite":c["suites"]["receipts"][0]["actual_compilers"]=0
            if kind=="archive":c["training"]["Opt"]["archives"][0]["size"]=0
            if kind=="training":c["training"]["Debug"]["actual_roots"]=0
            if kind=="repair":c["invalid"]["repair"]["product_verdicts"][1]["actual"]="0.1.7"
            try:check(c)
            except AssertionError:continue
            raise ValueError("accepted corrupted observation "+kind)
    print("Verified 15 Ruff builds, 38 suite compiler invocations, eight training archives and the failed/repaired real Cargo root")

if __name__=="__main__":
    main()
