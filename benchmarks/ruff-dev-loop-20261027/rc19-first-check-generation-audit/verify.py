"""Verify package-level and per-argv commitments from the six independent Cargo records."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import sys


def load(root, name):
    return json.loads((root / name).read_bytes())


def check(root):
    report=load(root,"phases.json")
    ids=load(root,"identity-sidecars.json")["rows"]
    assert hashlib.sha256((root/"identity-sidecars.json").read_bytes()).hexdigest() == report["later_sidecar_projection_sha256"]
    expected_transient=Counter(("ruff_python_index","ruff_linter","ruff_graph","ruff_benchmark","ruff_workspace","ruff_markdown","ruff_wasm","ruff_server","ruff","ruff","ruff_dev"))
    assert report["cargo_source"] == "235f9228651b74c591e6f62cae4c9b761448dd2d"
    assert report["cargo_sha256"] == "6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac"
    assert report["rustc_sha256"] == "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
    for direction,delta,gap,edge_count in (("parent",54_820_408_592,23_619_464,3),("child",14_673_109_324,23_043_471,5)):
        edit,first,settled=[report["phases"][direction+"-"+p] for p in ("edit","unchanged-1","unchanged-2")]
        for phase,count,fresh in ((edit,51,454),(first,12,489),(settled,1,498)):
            assert len(phase["rustcs"]) == phase["native_roles"]["rustc-full"] == count
            assert phase["typed_artifacts"] == 510 and phase["typed_fresh"] == fresh
            assert phase["all_observed_processes_succeeded"]
        assert edit["native_roles"] == dict(cargo=1,collect2=1,gcc=1,**{"rustc-full":51,"stock-wild":1})
        assert first["native_roles"] == {"cargo":1,"rustc-full":12} and settled["native_roles"] == {"cargo":1,"rustc-full":1}
        assert not edit["stale_mtime_edges"] and not settled["stale_mtime_edges"]
        stale,=first["stale_mtime_edges"]
        assert (stale["consumer"],stale["dependency"],stale["delta_ns"]) == ("ruff_python_index","ruff_python_ast",delta)
        assert first["missing_marker"] == settled["missing_marker"] == ["ty_python_semantic-6b9874c016d55a10.d/ohm-foreign-span-bytes"]
        assert Counter(r["crate"] for r in first["rustcs"]) - Counter(r["crate"] for r in settled["rustcs"])==expected_transient
        assert [r["crate"] for r in settled["rustcs"]] == ["ty_python_semantic"]
        assert all(r["emit"] == "dep-info,metadata" for r in first["rustcs"]+settled["rustcs"])
        first_index,=(r for r in first["rustcs"] if r["crate"]=="ruff_python_index")
        edit_index,=(r for r in edit["rustcs"] if r["crate"]=="ruff_python_index")
        assert edit_index["argv_sha256"]==first_index["argv_sha256"] and first_index["early_metadata_requested"]
        assert first_index["extern_ast"]==edit_index["extern_ast"]=="libruff_python_ast-58057b12cc3f5bc9.rmeta"
        assert first_index["completed_unchanged_local_hash"]["changed_dependency"] and not edit_index["completed_unchanged_local_hash"]["changed_dependency"]
        assert (first_index["extra_filename"],first_index["completed_unchanged_local_hash"]["public_hash"])==("dcdcb0c9486a5ac5","2f9c1818424b48cc58b5919f750ef821")
        assert edit["unique_sidecar_and_terminal_joins"] == 47 and len(edit["early_completion_edges"]) == edge_count
        x,=(r for r in edit["early_completion_edges"] if r["consumer"]=="ruff_python_index")
        assert (x["producer"],x["consumer_unit"],x["producer_unit"],x["terminal_log_gap_ns"]) == ("ruff_python_ast",351,345,gap)
        for row in edit["rustcs"]:
            if "completed_unchanged_local_hash" in row:
                assert ids[row["argv_sha256"]]["public_hash"]["value"] == row["completed_unchanged_local_hash"]["public_hash"]
    survey=load(root,"source-survey.json")
    subjects=set(survey["branches"].values())|set(survey["pulls"].values())|set(survey["release_inputs_as_previously_verified"].values())
    assert subjects == set(survey["commits"]) and len(subjects)==319
    assert (len(survey["branches"]),len(survey["pulls"]),len(survey["release_inputs_as_previously_verified"]))==(287,231,55)
    assert sum(bool(r) for r in survey["commits"].values())==306
    for missing,paths in survey["commits"].items():
        if not paths:
            assert any("evidence" in branch and value==missing for branch,value in survey["branches"].items())
    blobs=survey["blobs"]
    assert {v for paths in survey["commits"].values() for v in paths.values()}==set(blobs)
    fp=[b for b in blobs.values() if b["kind"]=="fingerprint"]
    jq=[b for b in blobs.values() if b["kind"]=="job_queue"]
    assert (len(fp),len(jq),sum(x["has_pending"] for x in fp))==(72,16,70)
    assert all(not x["pending_in_changed_guard"] for x in fp)
    assert not any(any(x["time_or_generation_in_finish"].values()) for x in jq)
    print("Both directions verified: 51 -> 12 -> 1 real compilers. One transient Rust metadata edge and 11 transient checks per direction. 306 product revisions and 13 evidence-only tips accounted for.")


if __name__ == "__main__":
    check(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
