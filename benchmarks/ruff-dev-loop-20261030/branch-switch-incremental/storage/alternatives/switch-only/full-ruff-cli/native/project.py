#!/usr/bin/env python3
"""Project the verified source-specific native and whole-ELF results."""
from pathlib import Path
import argparse
import hashlib
import json

def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def encode(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":")).encode()

def project(d):
    last=json.loads((d/"terminal.json").read_bytes())
    assert last["exit"]==0
    for name in ("current-elf.json","native-reference.json"):
        assert last["outputs"][name]==sha(d/name)
    proof=json.loads((d/"current-elf.json").read_bytes())
    native=json.loads((d/"native-reference.json").read_bytes())["public"]
    assert native["native_independent_terminal"]==last["independent_native"]
    branches={}
    for rev in "AB":
        packet=proof[rev]
        assert packet["full_reversible_comparison_passed"] and packet["runtime_terminal"]==last["independent_native"]
        x=packet["result"]
        cli=[native["native_reference"][o]["return-"+rev]["cli"] for o in ("off","on")]
        assert [a["sha256"] for a in cli]==x["original_elf_sha256"]
        assert cli[0]["bytes"]==cli[1]["bytes"] and len(set(x["original_elf_sha256"]))==2
        directories=[s.partition("/tikv-jemalloc-sys/") for s in x["independently_reported_compilation_directories"]]
        assert directories[0][0]==directories[1][0] and all(z[1] and z[2].endswith("/out/build") for z in directories)
        changes=set(x["changed_sections"])
        assert {".debug_str",".note.gnu.build-id"}<=changes<={".debug_str",".debug_info",".debug_macro",".note.gnu.build-id"}
        dec={}
        for group in ("info","macro"):
            p,q=[x["complete_decodings"][role][group] for role in ("P","Q")]
            assert p["each_65536_lines"]==q["each_65536_lines"] and p["canonical_output_sha256"]==q["canonical_output_sha256"]
            assert p["exit"]==q["exit"]==0 and p["lines"]==q["lines"] and p["path_replacements"]==q["path_replacements"]
            dec[group]={"lines_each":p["lines"],"matched_path_occurrences_each":p["path_replacements"],
                        "normalized_sha256":p["canonical_output_sha256"],"original_decoded_sha256":[p["raw_output_sha256"],q["raw_output_sha256"]],
                        "ordered_65536_line_block_hashes_sha256":hashlib.sha256(encode(p["each_65536_lines"])).hexdigest(),
                        "blocks":len(p["each_65536_lines"])}
        assert len(x["four_load_segments"])==4 and all(v["masked_a"]==v["masked_b"] for v in x["four_load_segments"])
        branches[rev]={"cli_off_on":cli,"consumer":native["native_reference"]["off"]["return-"+rev]["reader"],
            "consumer_output":"Expr=64 valid=1 rejected" if rev=="A" else "Expr=56 valid=1 rejected",
            "observed_unit_dirs_off_on":[z[2] for z in directories],
            "outside_permitted_equal_bytes":x["outside_allowed_bytes"],"outside_permitted_sha256":x["outside_allowed_sha256"],
            "actual_changed_sections":x["changed_sections"],"complete_decodings":dec,
            "load_segments_after_build_id_mask":[{k:v[k] for k in ("index","offset","size","masked_a")} for v in x["four_load_segments"]],
            "decoder_sha256":x["dwarfdump_sha256"]}
    return {"protocol_commit":"e91f82ceeeb9bc377dd0efbc66d3f509552d66a2","terminal":sha(d/"terminal.json"),
            "raw_complete_decode":sha(d/"current-elf.json"),"measurement_samples":0,
            "native_reference":native,"branches":branches}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("closed_read_only_proof",type=Path)
    result=project(p.parse_args().closed_read_only_proof)
    print(json.dumps(result,sort_keys=True,indent=2))
