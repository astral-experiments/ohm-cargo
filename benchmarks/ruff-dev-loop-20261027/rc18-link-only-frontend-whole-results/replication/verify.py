"""Verify all second-machine commands, native captures, safety checks and the registered statistics."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys


packet = Path(__file__).resolve().parent


def sha(content):
    return hashlib.sha256(content).hexdigest()


def file_sha(name):
    return sha((packet / name).read_bytes())


def read(name):
    data = (packet/name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


members = {}
for line in (packet/"SHA256SUMS").read_text().splitlines():
    digest,name=line.split("  ",1)
    assert name not in members and Path(name).name==name
    assert file_sha(name)==digest
    members[name]=digest
assert set(members)=={p.name for p in packet.iterdir() if p.name!="SHA256SUMS"}
deny=re.compile(rb"openai[.](org|com|internal)|artifactory[.]|authorization" rb": bearer|github_" rb"pat_|ghp_[a-z0-9]{16}|"
                rb"/home/dev" rb"-user/|/mnt/devbox" rb"-scratch/|charlie-" rb"ohm-",re.I)
for name in members:
    data=(packet/name).read_bytes()
    assert len(data)<8_000_000 and not deny.search(gzip.decompress(data) if name.endswith(".gz") else data),name
term=read("terminal.json");saved=read("statistics.json");orders=read("order.json")["batches"];samples=read("pairs.json")
assert term["complete"] and term["independent_of_first_machine"]
assert term["plan_ref"]=="c46547787e64621ad6d16b00e3f55206b0dfbf3e"
assert file_sha("paired-analysis.py")==term["analysis"]=="7c8e6bd96f9287eedd2003b8190273b3a24e83321888133580d358012cff5d5a"
assert file_sha("order.json")==term["order"]=="a9b2af0a341df8cba1ea20028f3fdbf834780b703fa468352bc0220d46cea39f"
assert file_sha("pairs.json")==term["raw"] and file_sha("statistics.json")==term["statistics"]
assert read("provenance.json")["original_complete_receipt"]==file_sha("terminal.json")
assert read("boot.json")["empty_stores"]==4 and list(sorted(read("boot.json")["registry_aliases"].values()))==[498,498]
expected=read("expected-targets.json"); assert expected["source_result"]=="7b9e9fbbd1113d961a6ec7fcca54ea620b59f49762278715800e152ecf59cbab"
targets=expected["native_names"];assert len(targets)==len(set(targets))==50
programs=read("observed-programs.json.gz")
assert len(programs["observations"])==8 and len(programs["listings"])==1
for digest,lines in programs["listings"].items():
    assert len(lines)==200 and sha(("\n".join(lines)+"\n").encode())==digest
imgs=read("images.json")
assert imgs["cargo"]=={"A":"a20b7097d6c0591464583de00bea1ee8d39bddfe461d56318532fb57991a8db7","B":"8e10b884f56d6807872c61d587b7cf152c03f04fe11e10b8bc412880f15c0ad0"}
assert imgs["rust"]["rustc"]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
assert imgs["rust"]["stock-wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
assert imgs["driver"]=="a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de"
catalogs=read("typed-catalogs.json.gz")
assert catalogs and all(len(c)==619 and all(len(e["original_typed_unit_sha256"])==64 for e in c) for c in catalogs.values())
roles={"cargo":1,"rustc-full":1,"rustc-link-only":50,"gcc":50,"collect2":50,"stock-wild":50}
func_cases={"notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"}
actual_processes=0;physical_ids={}
for n,(order,pairs) in enumerate(zip(orders,samples,strict=True),1):
    native=read("batch-%d-native.json.gz"%n);raw=read("batch-%d-raw.json.gz"%n)
    assert len(pairs)==len(raw["checks"])==len(order["order"])==24 and Counter(order["order"])=={"AB":12,"BA":12}
    assert raw["bound"]["schedule"]==order["order"] and raw["terminal"]["qualified"] and raw["preclock"]["qualified"]
    assert raw["terminal"]["pairs"]==24 and raw["terminal"]["batch"]==n==raw["bound"]["batch"]
    assert raw["terminal"]["attempt"]==term["attempts"][n-1]
    assert raw["preclock"]["warmups_per_arm"]==2
    for arm in ("A","B"):
        aux=raw["unscored"][arm]
        assert [r["stage"] for r in aux]==["cold","warm-1","warm-2"]
        assert [r["actual"]["fresh"] for r in aux]==[0,563,563]
        assert all(r["typed"] in catalogs and r["actual"]["units"]==619 and r["actual"]["exit"]==0 for r in aux)
    for when in ("pre","post"):
        arms={}
        for arm in ("A","B"):
            item=native[when+"-"+arm];r=item["report"];arms[arm]=r
            assert item["receipt_sha256"]==(raw["preclock"]["native"] if when=="pre" else raw["terminal"]["post_native"])[arm]
            assert r["arm"]==arm and r["batch"]==n and r["counts"]==roles and (r["units"],r["fresh"],r["exit"])==(619,563,0)
            assert r["tools"]==imgs["rust"] and r["driver"]==imgs["driver"] and r["image"]==imgs["cargo"][arm]
            assert r["typed_roster_sha256"] in catalogs
            assert all(event["exit"]==0 for event in r["events"])
            assert Counter(e["role"] for e in r["events"] if e["role"]!="rustc-query")==roles
            actual_processes+=len(r["events"])
            for e in r["events"]:
                k=e["role"]; k="rustc" if k.startswith("rustc-") else ("cargo-"+arm if k=="cargo" else k)
                f=(e["dev"],e["ino"])
                assert physical_ids.setdefault(k,f)==f
            observed=sorted(e["out"] for e in r["events"] if e["role"]=="stock-wild")
            assert observed==targets==sorted(f["basename"] for f in r["output_files"])
            assert all(f["bytes"]>0 and f["fields"]["bytes"]==f["bytes"] and len(f["sha256"])==64 for f in r["output_files"])
            compiler=Counter((e["role"],e["target"],e["argv_sha256"]) for e in r["events"] if e["role"] in ("rustc-full","rustc-link-only"))
            assert compiler==Counter((e["role"],e["unit"],e["raw_argv_sha256"]) for e in r["rust"])
            full=[e for e in r["rust"] if e["role"]=="rustc-full"]; cached=[e for e in r["rust"] if e["role"]=="rustc-link-only"]
            assert [(e["unit"],e["flag"]) for e in full]==[("ron","-Zthreads=8")]
            assert len(cached)==50 and {e["flag"] for e in cached}=={"-Zthreads="+("8" if arm=="A" else "1")}
            assert all(e["flag_index"]>0 for e in r["rust"])
            assert set(r["programs"])==func_cases|{"listing"} and all(v["exit"]==0 for v in r["programs"].values())
            assert r["programs"]["listing"]["listing_entries"]==200 and r["programs"]["listing"]["stdout_sha256"]=="e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316"
            orig=programs["observations"]["%d-%s-%s"%(n,when,arm)]
            assert orig["native_receipt_sha256"]==item["receipt_sha256"]
            for case in func_cases|{"listing"}:
                assert orig["cases"][case]["exit"]==0
                assert orig["cases"][case]["stdout_sha256"]==r["programs"][case]["stdout_sha256"]
                if case in func_cases:
                    assert orig["cases"][case]["actual_test_line"]=="test "+case+" ... ok"
            assert [f for f in r["output_files"] if f["basename"]==r["e2e"]["basename"]]==[r["e2e"]]
        assert arms["A"]["typed_roster_sha256"]==arms["B"]["typed_roster_sha256"]
        def arguments(v):return Counter((e["unit"],e["role"],e["all_other_arguments_sha256"]) for e in v["rust"])
        assert arguments(arms["A"])==arguments(arms["B"])
    for slot,(value,order_tag,checks) in enumerate(zip(pairs,order["order"],raw["checks"],strict=True),1):
        assert checks["n"]==slot and checks["order"]==value["order"]==order_tag
        assert not checks["before"]["other_tools"] and not checks["after"]["other_tools"]
        assert checks["before"]["online"]==checks["after"]["online"]==list(range(32))
        for arm in ("A","B"):
            r=value[arm]
            assert (r["exit"],r["units"],r["fresh"])==(0,619,563) and r["wall_ns"]>0
            assert sha((json.dumps(r,sort_keys=True)+"\n").encode())==checks["calls"][arm]["record_sha256"]
            assert checks["calls"][arm]["roster"]==native["pre-"+arm]["report"]["typed_roster_sha256"]
    per=[math.log(p["B"]["wall_ns"]/p["A"]["wall_ns"]) for p in pairs]
    assert abs(saved["batches"][n-1]["paired_reduction"]-(1-math.exp(statistics.fmean(per))))<1e-13
result=json.loads(subprocess.check_output([sys.executable,"-IB",packet/"paired-analysis.py",packet/"pairs.json","--order",packet/"order.json"]))
assert result==saved and result["pairs"]==48
print(json.dumps({"verified_pairs":48,"scored_cargo_commands":96,"native_censuses":8,"captured_native_process_entries":actual_processes,
                  "correctness":True,"timing_gate":result["passes_clock_gate"],"paired_reduction":result["paired_reduction"],
                  "interval_95":result["paired_95pct_interval"],"sign_p":result["exact_two_sided_sign_p"]},sort_keys=True))
