"""Verify the source-rehearsal packet and the independent native shadow outcomes."""
from pathlib import Path
from collections import Counter
import gzip
import json
import subprocess
import sys
p=Path(__file__).resolve().parent
def read(name):
    return json.loads(gzip.decompress((p/(name+".json.gz")).read_bytes()))
for name in ("focused","workspace"):
    out=json.loads(subprocess.check_output([sys.executable,"-IB",p/"compare-cohort.py",p/(name+".json.gz")]))
    assert out["warm_edit_matches_clean_elf"] and out["restored_matches_original_elf"]
    data=out["phases"]
    assert data["edited"]["e2e_links"]==data["clean"]["e2e_links"]==1
    assert set(data["edited"]["test_results"].values())=={101} and set(data["restore"]["test_results"].values())=={0}
    if name=="focused":
        assert data["repeat"]["units"]==300 and data["repeat"]["native"]=={}
    else:
        for stage in ["repeat","final-repeat"]:
            assert data[stage]["units"]==619 and data[stage]["native"]=={"full":1,"link-only":50,"wild":50}
        assert data["seed"]["e2e_sha256"]=="1d2e6e7b52aef89d9fd80ab7cbad4997baca0f08f7bb489bf721e2d60d76b82c"
        assert data["edited"]["e2e_sha256"]=="7b553c76b1547295e9a59ab96d8393233ad1ab3911d4c05e79f5d7fef30bcaa0"
native=read("consecutive-native-inputs"); assert native["shared_targets"]==native["with_same_observed_explicit_inputs"]==50
assert native["with_equal_elf"]==49 and all(r["literal_arg_differences"]==3 for r in native["results"])
edited=read("notebook-native-inputs");assert edited["with_same_observed_explicit_inputs"]==43 and edited["shared_targets"]==50
e2e,=[r for r in edited["results"] if r["e2e"]];assert not e2e["actual_elf_equal"] and any(n.startswith("libty_server-") for n in e2e["changed_explicit_file_names"])
look=read("native-lookups")
assert len(look["results"])==50 and sum(r["psm_libgcc_s_negative"] for r in look["results"])==50
assert sum(r["zstd_libgcc_s_negative"] for r in look["results"])==34
shadow=read("native-shadow");valid,bad,restored=shadow["phases"]
assert shadow["original_target_unchanged"] and shadow["targets"]==50
assert valid["native_link_execs"]==valid["original_50_linked"]==valid["exit_83"]==50
assert all(r["hook_symbol"] and r["list_exit"]==83 and r["list_count"]==0 for r in valid["outputs"])
assert bad["cargo_exit"]==101 and bad["malformed_diagnostic"] and bad["native_link_execs"]>0
assert restored["cargo_exit"]==0 and restored["exit_83"]==0 and all(not r["hook_symbol"] for r in restored["outputs"])
original={r["output"]:r["sha256"] for r in shadow["before"]}
e2e,=[r for r in restored["outputs"] if r.get("list_count")==200]
assert e2e["sha256"]==original[e2e["output"]]
assert sum(r["sha256"]==original[r["output"]] for r in restored["outputs"])==49
print("Verified six focused and six full-workspace phases, 50 native controls, real Cargo failure and clean e2e recovery.")
