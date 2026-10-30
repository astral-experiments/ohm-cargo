#!/usr/bin/env python3
"""Verify both zero-score admissions, the 14 native controls and the separate ordinary screen."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

SOURCE = {"A": "b5dba861cc38e3f7fb4524c9ceba3e01a474ea13", "B": "7b13f01ba1569887a25670820764b24c206da8e5"}
RUST = {"P": "7e71d3150938ff8ed82aca03416439d7e5b87ef3", "Q": "6b7f424ece4bc978ead5546b73e1b31d5ccb1e70"}
CARGO = "2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c"
NATIVE = "17fa53850eb32461b72563a8e514cdb9fc9d52cd3352de7b93d9b775ab4bc6d6"
CROSS = "7e88775e238732c42071cbfcfe767f9d3eda8a152c326af6ccfa15aa6832a78d"
REGISTRATION = "a72c58ac07a36623b6cd8a481494393ff4a242aac091972a0be4e4e7778b3b64"
OLD = ["bca0a7da0b49bc2fb877f3f02915da2c0ca9823cf323fbdfd4ca4c97d7267ed4", "7ff403df1b480f0e329dac29aa2bcef1e5c927a05cc9b8aea4afb837aee2d422"]
READER = {"A": "87dedef6a2b66c1998dd3bc4dcca0b45dd9713fbb28985bd45a8985f58798816", "B": "d5cdbc87717ddd119f74c4b840dd9fa2efc7cbc0af02ec5707a96ae738c839f0"}
COLD = {"GCC": 590, "SDK rustc": 379, "build script": 37, "collect2": 131, "stock Wild": 69}
RETURN = {"GCC": 1, "SDK rustc": 20, "build script": 1, "collect2": 1, "stock Wild": 1}
VERDICTS = {"version": 0, "source": 0, "clean": 0, "warning": 1, "fixed": 1, "recheck": 0, "invalid": 1}
SIZE = {"A": 149933440, "B": 149789624}
UNMASKED = {"A": 94177808, "B": 94056598}
INFO_LINES = {"A": 15551948, "B": 15528403}
INFO_HASH = {"A": "8693a7de7f9e0134e89d5d706baafba1c4a7b8d35bfd1336ea8c8740ffda51e6", "B": "6e27ae036e55b8b17e0c6863daf85508a9cda5bd4e4abb6c99f8d48fead5b5be"}
MACRO_HASH = "92aea27e4f9916049c8a70bf97ecb8e8fc4a673e10205dc686e3ddf5c955a573"
PHASES = ["empty-A", "first-B", "return-A", "return-B", "unchanged-B"]

def require(value, message):
    if not value:
        raise ValueError(message)

def sha_string(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def verify_previous(old):
    require(old["ordinary_timing_samples_from_either_attempt"] == 0, "excluded admission contributed a timing")
    require([old["rejected_original_cross_role_sha256"], old["rejected_replacement_same_role_sha256"]] == OLD, "earlier acquisition identity")
    require(set(old["results"]) == {"parent", "guarded"}, "earlier physical installers")
    for role, rec in old["results"].items():
        require(rec["prior_returned_ELF"] != rec["independently_empty_ELF"], role + " earlier raw failure")
        require(len(set(rec["actual_build_dir_namespace_returned_then_independent"])) == 2, role + " namespace source")
        require(rec["raw_outside_three_DWARF_sections_and_build_ID"]["aligned_identical"] and rec["raw_outside_three_DWARF_sections_and_build_ID"]["bytes"] == UNMASKED["A"], "earlier executable data")
        require(rec["normalized_decoded"]["info"]["same_sha256"] == INFO_HASH["A"], "old complete DWARF")
        require(rec["physical_empty"] == COLD and rec["physical_unchanged"] == {}, "old native controls")

def verify_native(doc):
    require(doc["previous_failed_before_any_timing"] == OLD and doc["new_timed_observations_in_this_packet"] == 0, "native and clock cohorts overlap")
    require(doc["registration_sha256"] == REGISTRATION and doc["native_gate_sha256"] == NATIVE and doc["complete_cross_role_sha256"] == CROSS, "actual native admission")
    require(doc["source"] == SOURCE and doc["rust"] == RUST and doc["cargo_source"] == CARGO, "source revisions")
    require(doc["cargo_sha256"] == "1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add", "real Cargo")
    require(doc["stock_wild_sha256"] == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5", "stock Wild")
    require(doc["argv"] == ["cargo", "+ohm", "build", "-p", "ruff", "--bin", "ruff", "--locked", "--offline", "-j4", "--message-format=json"], "ordinary command")
    require(doc["unique_physical_sdk_entries_verified_per_install"] == 57, "SDK identity")
    cases = doc["commands"]
    require(set(cases) == {base + "-" + a for base in ["cli-clean-A", "cli-admit-B"] for a in "PQ"}, "native installations")
    require(sum(map(len, cases.values())) == 14, "native commands")
    for rev in "AB":
        cross = doc["cross_role"][rev]
        require(len(set(cross["complete_ELF_sha256"])) == 2 and all(map(sha_string, cross["complete_ELF_sha256"])), "real cross-role raw files")
        require(cross["literal_unmasked_bytes_equal"] == UNMASKED[rev] and sha_string(cross["literal_unmasked_sha256"]), "raw unmasked bytes")
        require(cross["all_executable_bytes_match"] and cross["load_segments"] == 4, "executable-byte guard")
        require(cross["admitted_gnu_build_id_descriptor_bytes"] == 32 and set(cross["only_nonallocated_debug_sections"]) == {".debug_info", ".debug_macro", ".debug_str"}, "normalization scope")
        info, macro = (cross["exact_decoded_stream"][k] for k in ("info", "macro"))
        require(info == {"lines": INFO_LINES[rev], "path_replacements": 56517, "canonical_output_sha256": INFO_HASH[rev]}, "all decoded info records")
        require(macro == {"lines": 68285, "path_replacements": 0, "canonical_output_sha256": MACRO_HASH}, "all decoded macro records")
        require({k: v["exit"] for k, v in doc["native_verdicts"][rev].items()} == VERDICTS, "native CLI statuses")
        require(all(sha_string(v["stdout_sha256"]) and sha_string(v["stderr_sha256"]) for v in doc["native_verdicts"][rev].values()), "native stdout commitments")
    for arm_index, arm in enumerate("PQ"):
        for slot, phases in [(f"cli-clean-A-{arm}", ["empty-A", "unchanged-A"]), (f"cli-admit-B-{arm}", ["empty-B", "first-A", "return-B", "return-A", "unchanged-A"])]:
            require([r["phase"] for r in cases[slot]] == phases, "native order")
            for row in cases[slot]:
                phase, rev = row["phase"], row["revision"]
                require(rev == phase[-1] and row["typed_units"] == 375 and row["cargo_exit"] == 0 and sha_string(row["sha256"]), "native graph and exit")
                require(row["ELF"] == {"bytes": SIZE[rev], "sha256": doc["cross_role"][rev]["complete_ELF_sha256"][arm_index]}, "independent same-compiler CLI ELF")
                require(row["reader_sha256"] == READER[rev] and row["observed"] == ("Expr=64 valid=1 rejected" if rev == "A" else "Expr=56 valid=1 rejected"), "downstream actual source")
                n = row["actual_native_counts"]
                if phase.startswith("empty"):
                    require(n == COLD and row["dirty_units"] == 375, "empty stock command")
                elif phase.startswith("unchanged"):
                    require(n == {} and row["dirty_units"] == 0, "native no-op")
                elif phase.startswith("return"):
                    require(n == RETURN and row["dirty_units"] == 20 and row["link_output_same_inode"], "physical full CLI link")
                else:
                    require(n is None and row["dirty_units"] > 0, "untraced first training")
    return doc

def verify_clock_plan(p):
    require(p["chronological_new_ordinary_compilers"]==["Q","P","P","Q"] and p["opening_native_controls"]==14 and p["fresh_timing_installations"]==4, "new clock enrollment")
    require(p["reference_source_registration_sha256"]==REGISTRATION and p["reference_product_admission_sha256"]==NATIVE and p["reference_cross_role_elf_sha256"]==CROSS, "inherited independent reference")
    require(p["elapsed_registration_sha256"]=="398d34f98ab8fc107bb7cbc941d7bfe39c82b0353ca6ba6fe82243dc6139b7f8" and p["elapsed_source_and_schedule_sha256"]=="f1fbcc04a0e07a92355af95e70681aebded4fa2be44376a9b2d30dce6effae69", "independent pre-timing freeze")
    old=p["rejected_intermediate"]
    require(old["completed_unmatched_compiler"]=="Q" and old["next_unstarted_compiler"]=="P" and old["closed_prior_Q_elapsed_calls"]==2 and old["included_old_elapsed_calls"]==0, "unmatched Q exclusion")
    require(old["no_live_child_at_hold"] and old["actual_available_home_bytes_at_hold"]<old["original_home_entry_bytes"]==145*2**30, "preserved original floor")
    require(old["opaque_excluded_complete_receipt_sha256"]=="dafdaa1b4df2b35b79094c107ed5a0fe7c7fc94814b66a6e29a204f4e5504e37", "original withheld evidence")
    return p

def verify_screen(doc, native, plan):
    require(doc["schema"] == 1 and doc["two_pairs_screen_only"] and doc["old_observations_scored"] == 0 and doc["scored_commands"] == 8, "fixed screen scope")
    require(doc["native_admission_sha256"] == NATIVE and doc["cross_elf_proof_sha256"] == CROSS and doc["registration_sha256"] == plan["elapsed_registration_sha256"] and doc["native_reference_registration"]==REGISTRATION and doc["opaque_excluded_C4_Q_receipt"]==plan["rejected_intermediate"]["opaque_excluded_complete_receipt_sha256"], "registration boundary")
    require(doc["source_tools_identity"] == {"historical_source": SOURCE, "P": RUST["P"], "Q": RUST["Q"], "cargo": CARGO}, "physical subject")
    require(all(sha_string(doc[k]) for k in ["raw_complete_sha256", "independent_readback_sha256", "source_and_schedule_manifest_sha256"]), "terminal commitments")
    require(doc["source_and_schedule_manifest_sha256"] == plan["elapsed_source_and_schedule_sha256"], "frozen schedule")
    require([x["slot"] for x in doc["ordinary_slots"]] == ["cli-pair-1-Q", "cli-pair-1-P", "cli-pair-2-P", "cli-pair-2-Q"], "physical balanced order")
    scored = {}
    for run in doc["ordinary_slots"]:
        n, arm, visits = run["pair"], run["compiler"], run["visits"]
        require(run["slot"] == f"cli-pair-{n}-{arm}" and [v["phase"] for v in visits] == PHASES, "ordinary chronology")
        for row in visits:
            phase, rev = row["phase"], row["revision"]
            require(row["regular_output_on_work_tmpfs"] and len(row["after_wait_copy_stdout_and_stderr_bytes"])==2 and row["after_wait_copy_stdout_and_stderr_bytes"][0]>0 and row["after_wait_copy_stdout_and_stderr_bytes"][1]>=0, "time is independent of the receipt device")
            require(phase[-1] == rev and row["typed_units"] == 375 and row["exit"] == 0 and not row["counted_native_processes_in_this_timed_command"], "independent ordinary graph")
            require(row["ELF"] == {"bytes": SIZE[rev], "sha256": native["cross_role"][rev]["complete_ELF_sha256"]["PQ".index(arm)]}, "timed complete CLI")
            require(row["reader_sha256"] == READER[rev], "timed whole reader")
            require(sha_string(row["result_sha256"]) and sha_string(row["process_sha256"]) and sha_string(row["graph_sha256"]), "ordinary raw records")
            if phase.startswith("return"):
                require(row["selected_cli_dirty"] and row["dirty_units"] == 20, "full program returned")
                require(row["elapsed_ns"] > 0 and row["git_switch_ns"] > 0 and row["user_cpu_seconds"] > 0 and row["system_cpu_seconds"] >= 0, "blocking measurements")
                require((n, rev, arm) not in scored, "duplicate score")
                scored[(n, rev, arm)] = row
            else:
                require("elapsed_ns" not in row, "training or no-op scored")
                if phase.startswith("unchanged"):
                    require(row["dirty_units"] == 0 and not row["selected_cli_dirty"], "ordinary no-op")
                elif phase.startswith("empty"):
                    require(row["dirty_units"] == 375 and row["selected_cli_dirty"], "true empty ordinary arm")
    require(len(scored) == 8 and [(v["pair"],v["branch"]) for v in doc["paired_effects"]] == [(1,"A"),(1,"B"),(2,"A"),(2,"B")], "paired estimands")
    for v in doc["paired_effects"]:
        n, rev = v["pair"], v["branch"]
        p,q = (scored[(n,rev,a)] for a in "PQ")
        cpu = lambda s: s["user_cpu_seconds"] + s["system_cpu_seconds"]
        require(v["order"] == ("QP" if n == 1 else "PQ") and math.isclose(v["parent_over_guarded_elapsed"],p["elapsed_ns"]/q["elapsed_ns"],rel_tol=1e-12) and math.isclose(v["parent_over_guarded_cpu"],cpu(p)/cpu(q),rel_tol=1e-12), "paired arithmetic")
    require(len(doc["resources"])==4 and len({x["slot"] for x in doc["resources"]})==4, "four new independent installations")
    for x in doc["resources"]:
        entry=x["entry_scratch_home_memory"];live=x["min_scratch_home_memory"]
        require(len(entry)==len(live)==4 and all(v>g*2**30 for v,g in zip(entry,(140,140,75,8))) and all(v>g*2**30 for v,g in zip(live,(133,140,52,7))) and x["min_work_tmpfs"]>2*2**30 and x["min_receipt_runtime_bytes"]>7*2**30, "recorded capacity bounds")
        require(x["qualified_native_commands_for_its_compiler"]==7 and x["qualified_legacy_image_bodies_for_its_compiler"]==4 and x["physical_sdk_entries"]==57 and sha_string(x["front_sha256"]), "per-slot pre-Cargo proof")
    return doc

def require_rejection(target, mutate, validate):
    alternate=copy.deepcopy(target); mutate(alternate)
    try: validate(alternate)
    except (ValueError, KeyError, IndexError): return
    raise RuntimeError("corrupted observation was accepted")
def load(root,name):
    return json.loads((root/name).read_bytes())

def verify_file_list(root):
    manifest=root/"SHA256SUMS"
    if not manifest.exists():
        return
    expected={"README.md","verify.py","check_binary.py","native-admission.json","prior-installations.json","clock-plan.json","screen.json","escrow.json"}
    found=set()
    for line in manifest.read_text().splitlines():
        digest,name=line.split("  ",1)
        require(name in expected and name not in found and sha_string(digest),"portable manifest entries")
        require(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,"portable manifest content")
        found.add(name)
    require(found==expected,"complete public packet")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-only",action="store_true")
    parser.add_argument("--dir",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args();verify_file_list(args.dir)
    old=load(args.dir,"prior-installations.json");nat=load(args.dir,"native-admission.json")
    require(hashlib.sha256((args.dir/"native-admission.json").read_bytes()).hexdigest()=="5e1eaf1f7403b9b76b87c5945c0e1c4913093d8926791b2969a882c5275b49cb","independent 14-command projection file")
    clock=verify_clock_plan(load(args.dir,"clock-plan.json"))
    verify_previous(old);verify_native(nat)
    require_rejection(old,lambda d:d.update(ordinary_timing_samples_from_either_attempt=1),verify_previous)
    require_rejection(nat,lambda d:d["commands"]["cli-admit-B-Q"][2]["actual_native_counts"].update({"stock Wild":0}),verify_native)
    require_rejection(nat,lambda d:d["commands"]["cli-admit-B-Q"][3]["ELF"].update(sha256=d["cross_role"]["B"]["complete_ELF_sha256"][1]),verify_native)
    require_rejection(nat,lambda d:d["cross_role"]["A"].update(only_nonallocated_debug_sections=[".text"]),verify_native)
    out={"excluded_earlier_observations":0,"native_commands":14,"native_corruption_tests":4}
    if not args.native_only:
        doc=load(args.dir,"screen.json");verify_screen(doc,nat,clock);esc=load(args.dir,"escrow.json")
        require(esc["native_reference"]["compressed_sha256"]==clock["durable_native_escrow"]["source_and_reopened_compressed_sha256"] and esc["native_reference"]["members"]==64715, "reference raw escrow")
        for kind in ["native_reference","ordinary_screen"]:
            e=esc[kind]
            require(sha_string(e["compressed_sha256"]) and sha_string(e["content_mode_size_ledger_sha256"]) and sha_string(e["reopen_sha256"]) and e["members"]>0 and e["regular_bytes"]>600000000 and e["compressed_bytes"]>0 and e["complete_elf_bodies"]==6, "complete raw durable escrow")
        require(esc["ordinary_screen"]["native_sha256"]==doc["raw_complete_sha256"] and esc["ordinary_screen"]["independent_sha256"]==doc["independent_readback_sha256"], "ordinary escrow binds terminal")
        validate=lambda d:verify_screen(d,nat,clock)
        require_rejection(doc,lambda d:d["ordinary_slots"].reverse(),validate)
        require_rejection(doc,lambda d:d["ordinary_slots"][0]["visits"][2].update(dirty_units=0),validate)
        require_rejection(doc,lambda d:d["ordinary_slots"][1]["visits"][2]["ELF"].update(sha256="0"*64),validate)
        require_rejection(doc,lambda d:d["paired_effects"][0].update(parent_over_guarded_elapsed=0),validate)
        require_rejection(doc,lambda d:d["resources"][0]["entry_scratch_home_memory"].__setitem__(1,1),validate)
        out.update(ordinary_uninstrumented_pairs=2,real_ordinary_scored_commands=8,screen_corruption_tests=5,paired_elapsed_ratios=[round(x["parent_over_guarded_elapsed"],6) for x in doc["paired_effects"]])
    print(json.dumps(out,sort_keys=True))
if __name__=="__main__": main()
