#!/usr/bin/env python3
import argparse
import collections
import copy
import gzip
import hashlib
import json
from pathlib import Path

CODES={"00-baseline-one":0,"01-baseline-two":0,"02-baseline-three":0,"03-diagnostic":0,"10-valid":0,"11-valid-repeat":0,"12-forced-valid":0,"13-malformed":101,"14-remove":0,"15-forced-malformed":101,"16-final-remove":0}
VALID={"10-valid","11-valid-repeat","12-forced-valid"}
CASES={"inlay_hints::default_inlay_hints","notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"}
def validate(j,tiny):
    fixed=set(j["baseline"]);arms=j["cases"];assert set(arms)==set(CODES) and len(fixed)==50 and set(j["inventory"])==fixed
    assert j["receipts"]["old_619"]=="35171c6a4565a7b9f9535f4993aa015971de2914329e8a6067e506bf37fe0551"
    assert j["receipts"]["v2_registered"]=="2c7764b17292ad3690e926e436f26c267a6d49d788051019d6c12bdd5bd41682" and j["receipts"]["exdev_forced_zero_cargo"]=="3c20da92fb537a17756d738d10d3d1f69dd8e5fba2e5eeb2acb435ea2caf6953"
    assert j["receipts"]["mount_adapter"]=="0f442a6c9ef9039705cba41375361036c200bdf62d89eb2948fb88b9af8f3907"
    assert j["system_gcc_script_sha"]==tiny["gcc_script"] and j["stock_wild"]==tiny["wild"] and j["provider_source"]==tiny["source"]
    for kind in ("exe","shared"):
        r=tiny["operations"];assert all(r[name][kind]["link"]==0 for name in ("baseline","higher","restored"))
        assert [r[name][kind]["runtime"] for name in ("baseline","higher","malformed","restored")]==[0,83,None,0] and r["malformed"][kind]["link"]!=0
        assert r["baseline"][kind]["elf"]==r["restored"][kind]["elf"]!=r["higher"][kind]["elf"]
    tested=collections.Counter();digests=set()
    for name,expected in CODES.items():
        a=arms[name];assert a["cargo"]==expected and a["cached"]==0
        assert set(a["fixed_fifty_linked"]).isdisjoint(a["fixed_not_launched"]) and set(a["fixed_fifty_linked"])|set(a["fixed_not_launched"])==fixed
        if expected:
            native=(24,9,515) if name=="13-malformed" else (23,8,514)
            assert a["malformed_native_diagnostic"] and (a["full"],a["wild"],a["typed"])==native and a["fresh"]==431
            assert a["fixed_fifty_linked"]==["ruff_mdtest/test/mdtest"] and not a["per_target"] and not a["runtime"]
            assert a["all_wild_with_positive_script_fd"]==3 and a["all_wild_with_positive_object_fd"]==0
            assert a["fixed_fd_targets"]["ruff_mdtest/test/mdtest"]["roles"]==["provider"]
            continue
        assert not a["malformed_native_diagnostic"] and set(a["per_target"])==set(a["fixed_fifty_linked"])==fixed
        assert (a["full"],a["cc"],a["collect2"],a["wild"],a["typed"],a["fresh"])==(119,103,103,103,619,433)
        good=name in VALID;stage=a["per_target"];other=arms["10-valid"]["per_target"] if good else arms["00-baseline-one"]["per_target"]
        assert a["runtime"]=={("83" if good else "0"):50} and set(a["test_assertions"])==(set() if good else CASES)
        for target,v in stage.items():
            assert v["real_wild"] and v["exit"]==(83 if good else 0) and v["native_hook_symbol"]==good
            assert v["elf"]==other[target]["elf"] and v["bytes"]==j["real_body_lengths"][v["elf"]] and j["baseline"][target]!=arms["10-valid"]["per_target"][target]["elf"]
            if not good:assert v["elf"]==j["baseline"][target] and v["list_sha256"]==j["inventory"][target]
            else:assert v["list_sha256"]==hashlib.sha256(b"").hexdigest()
            digests.add(v["elf"]);tested[v["exit"]]+=1
        if name=="10-valid":
            assert len(a["fixed_fd_targets"])==50 and a["traced_wild_families"]==103 and a["all_wild_with_positive_script_fd"]==a["all_wild_with_positive_object_fd"]==68
            assert all(r["roles"]==["hook","provider"] and r["positive_descriptors"]>=2 and r["threads_reaching_fd"] for r in a["fixed_fd_targets"].values())
    assert tested=={0:300,83:150} and digests==set(j["real_body_lengths"]) and len(digests)==100 and sum(j["real_body_lengths"].values())==7879441416
    return {"cargo_commands":11,"positive_provider_commands":3,"successful_runtime_checks":dict(tested),"native_malformed_jobs":{"ordinary":[24,9],"forced":[23,8]},"malformed_selected_terminal":"ruff_mdtest/test/mdtest","distinct_complete_elfs":len(digests),"complete_elf_bytes":sum(j["real_body_lengths"].values()),"native_positive_fd_families":68,"fixed_targets":len(fixed)}

def main():
    ap=argparse.ArgumentParser(description="Verify all 11 workspace commands, 450 direct executions and the independent direct-link replay.")
    ap.add_argument("--self-test",action="store_true");args=ap.parse_args();p=Path(__file__).resolve().parent
    names=set()
    for l in (p/"SHA256SUMS").read_text().splitlines():
        digest,n=l.split("  ");assert "/" not in n and n not in names and hashlib.sha256((p/n).read_bytes()).hexdigest()==digest;names.add(n)
    assert names|{"SHA256SUMS"}=={f.name for f in p.iterdir() if f.is_file()}
    j=json.loads(gzip.decompress((p/"observations.json.gz").read_bytes()));tiny=json.loads((p/"direct-replay.json").read_bytes())
    assert hashlib.sha256((p/"provider.s").read_bytes()).hexdigest()==j["provider_source"]
    result=validate(j,tiny)
    if args.self_test:
        assert all(n in j["cases"] for n in VALID)
        for variant in ("missing-fd","drop-target","overcredit-failure","stale-restore","missing-cold-error","promote-extra-link"):
            bad=copy.deepcopy(j);c=bad["cases"];target="ty_server/test/e2e"
            if variant=="missing-fd":c["10-valid"]["fixed_fd_targets"][target]["roles"]=["provider"]
            if variant=="drop-target":del c["12-forced-valid"]["per_target"][target]
            if variant=="overcredit-failure":c["13-malformed"]["fixed_fifty_linked"].append(target)
            if variant=="stale-restore":c["16-final-remove"]["per_target"][target]["elf"]=c["10-valid"]["per_target"][target]["elf"]
            if variant=="missing-cold-error":c["15-forced-malformed"]["cargo"]=0
            if variant=="promote-extra-link":c["00-baseline-one"]["wild"]-=1
            try:validate(bad,tiny)
            except AssertionError:continue
            raise AssertionError("accepted corrupt "+variant)
        result["rejected_mutations"]=6
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
