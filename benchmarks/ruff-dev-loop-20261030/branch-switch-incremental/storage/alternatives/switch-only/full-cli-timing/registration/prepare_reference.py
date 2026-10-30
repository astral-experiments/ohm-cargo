#!/usr/bin/env python3
"""Bind completed native controls and whole-file references for the planned timings."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("analyze",HERE/"analyze.py")
analyze=importlib.util.module_from_spec(spec);spec.loader.exec_module(analyze)
require=analyze.require
def read(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def commitment(obj):return hashlib.sha256((json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()

def decoded(result, full, size):
    verify=bool(result and result.get("original_elf_sha256")==full)
    require(verify,"the decoded proof must cover the two actual input ELFs")
    changed=result["changed_sections"]
    require({".debug_str",".note.gnu.build-id"}<=set(changed)<={".debug_info",".debug_macro",".debug_str",".note.gnu.build-id"},"unsupported changed ELF section")
    for name,item in changed.items():
        a,b=item["a"],item["b"]
        require(all(a[k]==b[k] for k in ("type","offset","size","flags","entsize")),"different section layout")
        require(a["flags"]&4==0 and (not name.startswith(".debug") or a["flags"]&6==0),"allocated or executable debug difference")
    seg=result["four_load_segments"]
    require(len(seg)==4 and all(v["masked_a"]==v["masked_b"] for v in seg),"loaded executable differences")
    require(result["outside_allowed_bytes"]==size-sum(length for _,length in result["ranges"])>90_000_000,"unverified bytes outside the named ranges")
    require(analyze.sha256_text(result["outside_allowed_sha256"]),"raw outside-range witness")
    for which in ("info","macro"):
        a,b=[result["complete_decodings"][role][which] for role in ("P","Q")]
        require(a["exit"]==b["exit"]==0 and a["lines"]==b["lines"]>1000 and
                a["canonical_output_sha256"]==b["canonical_output_sha256"] and a["each_65536_lines"]==b["each_65536_lines"] and
                a["path_replacements"]==b["path_replacements"] and (which!="info" or a["path_replacements"]>0),"complete decoded debug comparison")
    return True

def build(native, historical_proof, fresh_proof=None):
    plan=read(HERE/"plan.json");ends=read(native/"independent-terminal.json");ver=read(native/"verified.json");coll=read(native/"collection.json")
    require(sha(native/"verified.json")==ends["verified"] and sha(native/"collection.json")==ends["collection"]==ver["physical_collection"],"independent native terminal")
    require(coll["source"]==plan["compiler_source"] and ver["no_timing_comparison"] and ver["same_flag_independent_raw_clean"] and ver["same_physical_57"],"native option/source guards")
    require(coll["sha256sums"]=="29099ce877f5a6589ae36b6a61bf595b2102e8df2ff9a8c0eba114e5fba53138","native original instruction and source commitments")
    require(sha(historical_proof)=="3f55abd3300e6ea05118080e5c83233345196dd3b99d50145f9f05c861ab25ae","authenticated prior comparison")
    old=read(historical_proof);fresh=read(fresh_proof) if fresh_proof else {}
    identities=[];cross={};raw={}
    refs={arm:{} for arm in analyze.ARMS}
    for arm in analyze.ARMS:
        for kind,phases in (("storage",analyze.PHASES),("clean-B",("empty-B",))):
            fs=native/"runs"/(arm+"-"+kind)
            require(sha(fs/"completed.json")==coll["slots"][fs.name],"native slot receipt")
            completed=read(fs/"completed.json");identity=read(fs/"identity.json");identities.append(identity["stable_kit"])
            require(identity["clean_initial"] and len(identity["stable_kit"])==57,"native true empty setup and physical SDK")
            for phase in phases:
                path=fs/phase;r=read(path/"result.json");key=(arm,phase);raw[key]=r
                require(sha(path/"result.json")==completed["result_hashes"][phase] and r["revision"]==plan["ruff"][phase[-1]],"source and completed native phase")
                require(r["graph_sha256"]==plan["graph_sha256"] and r["typed"]==375 and len(r["outcomes"])==7,"typed native observation")
                require(r["observed"]==("Expr=64 valid=1 rejected" if phase[-1]=="A" else "Expr=56 valid=1 rejected"),"native AST/parse verdict")
                position=ver["slots"][fs.name][phase]
                require(position["physical"]==r["physical"] and position["cli"]==r["CLI_ELF"] and position["reader"]==r["reader"],"independent native report")
                for field in ("CLI_ELF","reader"):
                    operand=r[field];retained=native/"elf"/operand["sha256"]
                    require(retained.stat().st_size==operand["bytes"] and sha(retained)==operand["sha256"],"complete native product")
                if kind=="storage":
                    refs[arm][phase]={"cli":r["CLI_ELF"],"reader":r["reader"],"verdict_sha256":commitment(r["outcomes"]),
                        "dirty_set_sha256":commitment(r["dirty"]),"real_rustc":r["physical"].get("SDK rustc",0),
                        "real_wild":r["physical"].get("stock Wild",0),"raw_native_result":sha(path/"result.json"),
                        "independent_empty_full_file_equality":True}
    require(all(x==identities[0] for x in identities) and len(identities)==4,"actual identities in four independent original installations")
    for arm in analyze.ARMS:
        for phase in analyze.PHASES:
            a=raw[arm,phase];cold=raw[arm,"empty-"+phase[-1]]
            require(all(a[k]==cold[k] for k in ("CLI_ELF","reader","observed","revision","outcomes","graph_sha256","native_comp_dir")),"whole same-option clean products")
    for rev in ("A","B"):
        a,b=[raw[v,"return-"+rev] for v in analyze.ARMS]
        require(all(a[k]==b[k] for k in ("reader","observed","outcomes","dirty","physical","graph_sha256","revision")),"cross-option native behavior or external reader")
        require(a["reader"]["sha256"]=={"A":"87dedef6a2b66c1998dd3bc4dcca0b45dd9713fbb28985bd45a8985f58798816","B":"d5cdbc87717ddd119f74c4b840dd9fa2efc7cbc0af02ec5707a96ae738c839f0"}[rev],"previously authenticated native reader")
        full=[x["CLI_ELF"]["sha256"] for x in (a,b)]
        if full[0]==full[1]:method="raw_complete_equality";receipt=full[0]
        elif old[rev]["full_reversible_comparison_passed"] and old[rev]["result"]["original_elf_sha256"]==full:
            decoded(old[rev]["result"],full,a["CLI_ELF"]["bytes"])
            method="bound_complete_prior_file_pair";receipt=sha(historical_proof)
        elif "strict_dwarf" in ver["cross_flag_elf"][rev]:
            decoded(ver["cross_flag_elf"][rev]["strict_dwarf"],full,a["CLI_ELF"]["bytes"])
            method="current_native_registered_decode";receipt=sha(native/"verified.json")
        else:
            require(fresh_proof is not None and rev in fresh and fresh[rev]["full_reversible_comparison_passed"],"fresh current-ELF decoding required")
            rr=fresh[rev]["result"];decoded(rr,full,a["CLI_ELF"]["bytes"])
            require(rr["independently_reported_compilation_directories"]==[a["native_comp_dir"],b["native_comp_dir"]],"expected observed literal paths")
            require(fresh[rev]["runtime_terminal"]==sha(native/"independent-terminal.json"),"wrong current native series")
            method="current_whole_ELFs_and_decoded_paths";receipt=sha(fresh_proof)
        cross[rev]={"method":method,"proof_sha256":receipt,"raw_cli_off_on":full,"verdict_equal":True,"ordinary_caller_equal":True}
    public={"schema":1,"source":plan["compiler_source"],"cargo":plan["cargo_source"],"native_independent_terminal":sha(native/"independent-terminal.json"),
            "raw_native_verified_sha256":sha(native/"verified.json"),"raw_native_collection_sha256":sha(native/"collection.json"),
            "physical_sdk_sha256":commitment(identities[0]),"observed_flag":{"off":None,"on":plan["on_flag"]},
            "native_reference":refs,"cross_option":cross}
    analyze.check_native(public,plan)
    return {"public":public,"physical_files":identities[0]}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("native_custody",type=Path);ap.add_argument("historical_elf_proof",type=Path);ap.add_argument("output",type=Path);ap.add_argument("--current-elf-proof",type=Path)
    a=ap.parse_args();got=build(a.native_custody,a.historical_elf_proof,a.current_elf_proof)
    with a.output.open("x") as f:json.dump(got,f,sort_keys=True,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
    print(sha(a.output))
if __name__=="__main__":main()
