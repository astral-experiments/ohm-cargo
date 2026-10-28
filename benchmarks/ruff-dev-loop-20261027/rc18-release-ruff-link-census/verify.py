"""Verify the complete released Ruff control using Python's standard library."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

here = Path(__file__).resolve().parent
if not __debug__:
    raise SystemExit("invoke without Python optimization")
H = re.compile("[0-9a-f]{64}")
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda f: json.loads((here / f).read_bytes())
original = "be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7"
edited = "d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8"
wild = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
archive = "629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8"
listing = "e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316"
names = {"notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"}
phases = ("seed","repeat","edited","clean","restore","final-repeat")
counts = {
    "focused":[(0,304,0,48,0),(300,0,0,0,0),(298,2,0,1,0),(0,304,0,48,0),(298,2,0,1,0),(300,0,0,0,0)],
    "workspace":[(0,625,0,188,62),(563,1,50,50,0),(559,12,43,52,0),(0,625,0,188,62),(559,12,43,52,0),(563,1,50,50,0)],
}


def integrity():
    lines = (here / "SHA256SUMS").read_text().splitlines()
    expected = {}
    for line in lines:
        checksum, name = line.split("  ",1)
        assert H.fullmatch(checksum) and not Path(name).is_absolute() and ".." not in Path(name).parts
        assert name not in expected
        expected[name] = checksum
    paths = list(here.rglob("*"))
    assert not any(f.is_symlink() for f in paths)
    actual = {f.relative_to(here).as_posix(): sha(f.read_bytes()) for f in paths if f.is_file() and f != here / "SHA256SUMS"}
    assert expected == actual


def check_scope(subject, data, scope):
    bundle = (here / (scope + ".json.gz")).read_bytes()
    assert sha(bundle) == data["original_packets"][scope]
    packet = json.loads(gzip.decompress(bundle))
    assert packet["arm"] == "release" and packet["group"] == scope and set(packet["phases"]) == set(phases)
    roster = 619 if scope=="workspace" else 300
    source = subject["source"]
    expected_argv = ["cargo","+ohm","test"] + (["--workspace"] if scope=="workspace" else ["-p","ty_server","--test","e2e"]) + [
        "--no-run","--locked","--offline","-j8","--message-format=json"]
    accepted = [original, edited] if scope=="workspace" else [
        "786de444f9e531d077dab9eff5a94e51e2312adc99e3ba11f06e508d5926b125",
        "f6de480999a7ceadb579e80ddabdbc3127127d15be690228c3cedfce306569ae"]
    for step, key in enumerate(phases):
        p = packet["phases"][key]
        cmd = p["command"]
        change = key in ("edited", "clean")
        assert p["state"] == ("edited" if change else "original")
        assert cmd["state"] == p["state"] and cmd["source"] == source
        assert cmd["source_sha256"] == subject["edited_sha256" if change else "old_sha256"]
        assert cmd["empty_shared"] == cmd["empty_target"] == (key in ("seed","clean"))
        assert cmd["images"] == data["package"]["outer_comparison"]["images"] and cmd["argv"]==expected_argv
        assert all(H.fullmatch(e["argv_sha256"]) for e in p["executed"])
        events = Counter(e["kind"] for e in p["executed"])
        assert dict(events) == p["native"]
        assert (p["fresh"], events["full"], events["link-only"], events["wild"], events["other-linker"])==counts[scope][step]
        assert p["units"] == roster and p["listed"] == 200 and p["test_list_sha256"] == listing
        file = p["e2e_file"]
        assert p["e2e_sha256"] == accepted[change] == p["executables"][file]["sha256"]
        assert p["e2e_size"] == p["executables"][file]["size"]
        assert len(p["links"]) == events["wild"] and sum(x["file"]==file for x in p["links"]) == p["e2e_link_count"]
        assert Counter(e["id"] for e in p["executed"] if e["kind"]=="full") == Counter(p["full_crates"])
        if scope == "workspace" and key in ("repeat","final-repeat"):
            assert p["full_crates"]==["ron"] and p["test_results"]=={} and p["e2e_link_count"]==1
            before, after = p["ron"]["before"], p["ron"]["after"]
            assert set(before) == set(after) and {Path(x).suffix for x in before} == {".rmeta",".rlib"}
            for f in before:
                rb, ra = before[f], after[f]
                assert rb["ino"] != ra["ino"]
                assert (rb["sha256"]==ra["sha256"]) == f.endswith(".rlib")
                assert (rb["mtime_ns"]==ra["mtime_ns"]) == f.endswith(".rmeta")
        else:
            assert p["test_results"]==dict.fromkeys(names, 101 if change else 0)
        assert len(p["assertions"]) == (2 if change else 0)
        for f, digest in p["private_original_sha256"].items():
            assert data["raw"]["reports/release-"+scope+"-"+key+"/"+f] == digest
    return packet


def target_map(records):
    result = {r["target"]: r for r in records}
    assert len(result)==len(records)
    return result


def check_runs(data):
    package = data["package"]
    assert package["download"]["sha256"] == archive and package["download"]["bytes"] == 359656945
    assert package["download"]["additional_files"]["ohm-installer.sh"] == "0148622878ce6a6278c31b7652563090e522aadb8be9f7282da28018061a2d07"
    assert package["inner_installer_sha256"] == "72807761d932e9ea33ac98208ab00ce7f9cd5eee3dbe86cd911007358ac71b01"
    install = package["outer_comparison"]
    assert install["images"] == {"cargo":"02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573",
        "rustc":"c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60",
        "rustdoc":"dc6501f27285e927df450d559108a1e5609fc11d266e628d4f1b27d416b84cef","wild":wild}
    assert install["compared_files_and_symlinks"]==69866 and len(install["different"])==11
    assert set(install["different"])=={"lib/rustlib/install.log"}|{"lib/rustlib/manifest-"+x for x in (
        "cargo","clippy-preview","rust-analysis-x86_64-unknown-linux-gnu","rust-docs","rust-docs-json-preview",
        "rust-src","rust-std-wasm32-unknown-unknown","rust-std-x86_64-unknown-linux-gnu","rustc","rustfmt-preview")}
    assert install["verified_ledger_paths_relative_to_prefix"] and install["published_archive_sha256"]==archive
    assert install["identical_entries_sha256"]=="c1d19ca71481ffcb6f574dd56e2b40a8e3b685cf6e77bdd4a05e56d65e5a095a"
    r = data["raw"]
    assert all(H.fullmatch(v) for v in r.values()) and all(not Path(k).is_absolute() and ".." not in Path(k).parts for k in r)
    assert data["subject"]["source"]=="93526150df078af7dd8fc4226cdcc469539d2001"
    assert data["subject"]["historical_fix"]=="eb9e9bdcf988fffcd619dcf5d2a2bd74d75be1c6"
    workspace=check_scope(data["subject"],data,"workspace")
    check_scope(data["subject"],data,"focused")
    inner = data["live_native_captures"]["inner"]
    outer = data["live_native_captures"]["outer"]
    ik, ok = target_map(inner["records"]), target_map(outer["records"])
    e2e=inner["ty_e2e"]; assert e2e==outer["ty_e2e"]=="e2e-f978f73ba5a3a2ed"
    assert len(ik)==50 and set(ik)==set(ok)
    assert sorted(k for k in ik if ik[k]["sha256"]!=ok[k]["sha256"])==["ruff-d6ddb74de333d3e2","ty-28db247cc67222c0"]
    inn, ou = "v2-0de3af5db4b086d2","v2-ed8a5e5c44d2fb2b"
    for x,mp,ns in ((inner,ik,inn),(outer,ok,ou)):
        assert x["native_counts"]=={"full":1,"link-only":50,"wild":50} and x["units"]==619 and x["stock_linker"]==wild
        assert x["unique_explicit_paths"]==3401
        assert {a["output_namespace"] for a in mp.values()}=={a["search_namespace"] for a in mp.values()}=={ns}
        assert (mp[e2e]["argv_fields"],mp[e2e]["explicit_operands"],mp[e2e]["sha256"])==(446,394,original)
    census = target_map(read("custody/targets.json"))
    assert set(census)==set(ik) and all(census[k]["physical_exec_record_sha256"]==ik[k]["raw_exec_sha256"]
        and census[k]["elf_sha256"]==ik[k]["sha256"] for k in census)
    assert r["reports/release-workspace-raw/result.json"]==workspace["raw_capture"]["private_original_sha256"]==read("custody/summary.json")["raw_link_capture_sha256"]
    assert read("single-archive/summary.json")["outcome"]["native_fallback_sha"]==edited
    assert read("single-archive/summary.json")["outcome"]["restored"]==original
    o=data["observer"]; assert (o["namespace"],o["marker_stat_errno"],o["marker_occurrences"],o["record_magic"],o["record_complete_byte"])==(inn,20,4,"OBS1",0)
    assert o["record_sha256"]=="9da8124b6213f0c764d149a263c81bfb6642da294b478b248b08aa883b4d49e4"
    widths=target_map(data["widths"]["samples"])
    assert set(widths)==set(ok) and all(x["workers"]==x["token_count"]+1 for x in widths.values())
    assert Counter(x["workers"] for x in widths.values())=={1:47,2:2,3:1}
    assert data["widths"]["distribution"]=={"1":47,"2":2,"3":1}
    assert widths[e2e]["workers"]==2 and widths[e2e]["sha256"]!=original and widths[e2e]["size"]==ok[e2e]["size"]
    assert widths["generate_inline_tests-00680913f20a7bbc"]["workers"]==1
    negative=data["wrong_namespace"]
    assert negative["job"]["exit"]==1 and negative["cargo"]["cargo_success"] and negative["cargo"]["units"]==619
    bad=target_map(negative["processes"]["successful_native_execs"])
    assert set(bad)==set(ok) and {x["search_namespace"] for x in bad.values()}=={ou} and ou!=inn
    d=data["active_shadow"]; assert d["mask_namespace"]==ou and d["original_target_unchanged"]
    before=target_map(d["before"]); assert {k:x["sha256"] for k,x in before.items()}=={k:x["sha256"] for k,x in ok.items()}
    assert [q["phase"] for q in d["phases"]]==["valid","invalid","restored"]
    for phase, returns, full, split, links, n in zip(d["phases"], [0,101,0],[1,1,51],[50,8,0],[50,8,50],[619,569,619]):
        assert (phase["cargo_exit"],len(phase["full"]),phase["link_only"],phase["native_link_execs"],phase["original_50_linked"],phase["units"])==(returns,full,split,links,links,n)
        assert phase["streams"]["units"]==n and phase["streams"]["cargo_success"]==(returns==0)
        assert phase["streams"]["finished_stdout_sha256"]==phase["cargo_stdout_sha256"] and phase["streams"]["stderr_sha256"]==phase["stderr_sha256"]
        jobs=phase["processes"]; names_seen=target_map(jobs["successful_native_execs"])
        assert len(names_seen)==links and set(names_seen)<=set(ok)
        assert jobs["rustc_counts"].get("link-only",0)==split and jobs["rustc_counts"]["full"]==full
        assert {x["search_namespace"] for x in names_seen.values()}=={ou} and all(H.fullmatch(x["trace_sha256"]) for x in names_seen.values())
        assert phase["streams"]["has_malformed_provider_diagnostic"]==(returns==101)
    valid,invalid,restored=d["phases"]; poisoned=target_map(valid["outputs"]); recovered=target_map(restored["outputs"])
    assert set(poisoned)==set(recovered)==set(ok)
    assert all(x["hook_symbol"] and x["list_exit"]==83 and x["list_count"]==0 and x["list_sha256"]==sha(b"") for x in poisoned.values())
    assert all(not x["hook_symbol"] and x["sha256"]==before[k]["sha256"] for k,x in recovered.items())
    assert recovered[e2e]["list_exit"]==0 and recovered[e2e]["list_count"]==200 and recovered[e2e]["sha256"]==original
    x=data["post_restore_chronology"]
    assert x["counts"]=={"rustc-full":1,"rustc-link-only":50,"gcc":50,"collect2":50,"stock-wild":50}
    assert x["units"]==619 and x["stock_touched_original_50"]==50 and x["exit"]==0
    assert x["e2e_before_elf"]==x["e2e_after_elf"]==original and x["e2e_ran_wild"] and x["small_ran_wild"]
    assert x["e2e_tests"]==dict.fromkeys(names,0)
    assert data["jobs"]["public-installer-actual-native-controls"]["exit"]==0


def check_capsule():
    c=read("capsule.json")
    assert c["component_manifest"]=="938bc72b5fd4b269e0c8a8573ab70323b825cf242b743d6b22bd3758b9ee276d"
    assert c["controlled_workspace_only"] and c["original_seed_untouched"]
    assert c["target"]=="e2e-f978f73ba5a3a2ed" and c["wild_sha256"]==wild
    assert c["training_sha256"]==read("single-archive/summary.json")["outcome"]["training"]
    assert c["sources"]["unchanged-all-threads.json.gz"]["decoded_sha256"]=="06b56fba6c718747e56c062b8f7c3b1b9fcdef75586ee0ed5c940ed367b11d30"
    assert c["reviewed_sha256"]=="06dd1b5608a5801503ce07b812543fb1ef0c8999a8267373c389338a1d38886c"
    assert c["complete_sha256"]==c["sources"]["complete.json.gz"]["decoded_sha256"]=="37a4d26e924d8addd72241dd4b6bf85fe3688648e4159167b15c2f065391f5bc"
    order=["unchanged-1","unchanged-2","unchanged-3","notebook-edit","notebook-restore","post-restore"]
    assert [x["phase"] for x in c["phases"]]==order
    for i,p in enumerate(c["phases"]):
        base="commands/"+p["phase"]+"/"
        assert p["native_result_sha256"]==c["sources"][base+"result.json.gz"]["decoded_sha256"]
        assert p["process_receipt_sha256"]==c["sources"][base+"execs.json.gz"]["decoded_sha256"]
        assert p["units"]==619 and p["e2e_list_count"]==200 and p["e2e_listing_sha256"]==listing
        assert p["e2e_before_sha256"]==(edited if i==4 else original) and p["e2e_after_sha256"]==(edited if i==3 else original)
        assert p["observed_stock_identity"]==[64769,34865193]
        assert all(x["exit"]==0 and H.fullmatch(x["argv_sha256"]) for x in p["events"])
        events=Counter(x["role"] for x in p["events"]); assert events==p["counts"]
        full, split, driver, stock = (1,50,50,49) if i<3 else ((12,43,52,52) if i<5 else (1,50,50,50))
        assert (events["rustc-full"],events["rustc-link-only"],events["gcc"],events["collect2"],events["stock-wild"])==(full,split,driver,driver,stock)
        children=[x["out"] for x in p["events"] if x["role"]=="stock-wild"]
        assert len(set(children))==len(children) and (c["target"] in children)==(i>=3)
        assert p["e2e_hit"]==(i<3) and p["e2e_ran_stock"]==(i>=3)
        assert p["audit"]["workers"]==1 and p["audit"]["checker_code"]==int(i>=3)
        assert p["audit"]["training_sha256"]==c["training_sha256"]
        assert p["notebook_tests"]==dict.fromkeys(names,101 if i==3 else 0) and p["generator_exit"]==0
    rot=c["object_rotation"]; assert len(rot["original"])==len(rot["after"])==139
    assert not (rot["original"].keys() & rot["after"].keys())
    counts=lambda r:Counter((x["sha256"],x["size"]) for x in r.values())
    assert counts(rot["original"])==counts(rot["after"])
    assert rot["literal_names_in_rlink"]==rot["literal_names_in_rlink_cache"]=={"new_only":[0,139],"old_only":[139,0]}
    fam=c["thread_families"];assert len(fam)==len({v["pid"] for v in fam})==100
    assert all(x["threads"]==x["observed_clone_edges"] for x in fam)
    assert Counter(x["threads"] for x in fam if x["role"]=="rustc-link-only")=={10:50}
    assert Counter(x["workers"] for x in fam if x["role"]=="stock-wild")=={1:47,2:2,3:1}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--originals",type=Path,help="recompute additional projections from the protected study root")
    ap.add_argument("--capsule-originals",type=Path,help="compare the separately sealed handoff projection")
    args=ap.parse_args()
    integrity()
    data=read("release.json")
    check_runs(data)
    check_capsule()
    for folder in ("custody","single-archive"):
        subprocess.run([sys.executable,"-IB",str(here/folder/"verify.py")],check=True)
    if args.originals:
        reproduced = subprocess.check_output([sys.executable,"-IB",str(here/"collect.py"),str(args.originals)])
        assert reproduced==(here/"release.json").read_bytes()
    if args.capsule_originals:
        reproduced=subprocess.check_output([sys.executable,"-IB",str(here/"project-capsule.py"),str(args.capsule_originals)])
        assert reproduced==(here/"capsule.json").read_bytes()
    print("Verified six separate single-target handoff decisions, 12 notebook outcomes and 100 native process families.")
    print("Verified official release identity, two six-phase Cargo cohorts, two 50-process captures, worker widths, the ineligible namespace, the 50-program native fault, recovery, and archive-only edit.")


if __name__=="__main__":
    main()
