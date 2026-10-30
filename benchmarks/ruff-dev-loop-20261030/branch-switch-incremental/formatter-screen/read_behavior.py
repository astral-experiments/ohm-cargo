"""Recheck each formatter invocation, three executable callers and two real metadata readers."""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

COMMAND = ["cargo", "+ohm", "test", "-p", "ruff_python_formatter", "--lib",
           "--no-run", "--locked", "--offline", "-j4", "--message-format=json"]
TESTS = ["tests::basic", "tests::string_processing", "comments::tests::parenthesized_expression"]
DRIVERS = {"P": "66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e",
           "Q": "b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c"}
CARGO = "1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
def read(path):
    return json.loads(path.read_bytes())
def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
def check_process(stage,name):
    report=read(stage/(name+".process.json"))
    for channel in ["stdout","stderr"]:
        assert digest(stage/(name+"."+channel)) == report[channel]
    for when in ["before","after"]:
        g=report[when]
        assert g["private"]>650*1024**2 and g["memory"]>52*2**30 and g["home"]>140*2**30 and g["scratch"]>133*2**30
    return report
def run(raw):
    assert read(raw/"terminal.json")["exit"] == 0
    limits=[]
    counts=collections.Counter()
    clean={}
    diagnostics={}
    for folder,receipt in read(raw/"complete.json")["terminals"].items():
        slot=raw/"runs"/folder
        assert digest(slot/"complete.json")==receipt and read(slot/"terminal.json")["exit"]==0
        subjects=read(slot/"identity.json")
        arm=folder[-1]
        assert [subjects[k] for k in ("driver","cargo","wild")]==[DRIVERS[arm], CARGO, WILD]
        assert subjects["empty"] and subjects["cpu"]==[28,29,30,31]
        entry=read(slot/"entry.json")["room"]
        assert entry["memory"]>75*2**30 and entry["home"]>145*2**30 and entry["scratch"]>135*2**30
        for label in read(slot/"complete.json")["rows"]:
            stage=slot/label
            proc=check_process(stage,"cargo")
            limits += [proc["before"],proc["after"]]
            argv=proc["args"]
            if label.endswith("-native"):
                assert argv[0]=="strace" and argv[-len(COMMAND):]==COMMAND
                counts["traced"]+=1
            else:
                assert argv==COMMAND
                counts["ordinary"]+=1
            stream=[json.loads(line) for line in (stage/"cargo.stdout").read_bytes().splitlines()]
            summary=read(stage/"result.json")
            assert stream[-1]=={"success":label!="invalid-A","reason":"build-finished"}
            if label=="invalid-A":
                assert proc["exit"]==101
                literal=[]
                for e in [x["message"] for x in stream if x["reason"]=="compiler-message" and x["message"]["level"]=="error" and x["message"].get("code")]:
                    if any("OHM_FORMATTER_BRANCH_TYPE_GUARD" in t["text"] for span in e["spans"] for t in span["text"]):
                        literal.append([e["code"]["code"],e["message"],[[s["file_name"],s["line_start"],s["column_start"]] for s in e["spans"] if s["is_primary"]]])
                assert literal==summary["diagnostics"] and len(literal)==1 and literal[0][0]=="E0308"
                diagnostics[arm]=literal
                continue
            assert proc["exit"]==0
            typed=[x for x in stream if x["reason"]=="compiler-artifact"]
            executable,=[x["executable"] for x in typed if x["target"]["name"]=="ruff_python_formatter" and x["profile"]["test"] and x["executable"]]
            assert check_process(stage,"list")["args"]==[executable,"--list","--format","terse"]
            for i,test in enumerate(TESTS):
                p=check_process(stage,f"test-{i}")
                assert p["args"]==[executable,"--exact",test,"--test-threads=1"] and p["exit"]==0
                assert f"test {test} ... ok" in (stage/f"test-{i}.stdout").read_text()
                counts["representative_passes"]+=1
            if summary["whole_runtime"]:
                full=check_process(stage,"all-tests")
                assert full["args"]==[executable,"--test-threads=1"] and full["exit"]==0
                m=re.search(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;",(stage/"all-tests.stdout").read_text())
                assert m and int(m[1])+int(m[3])==summary["tests"] and int(m[2])==0
                clean[folder+"/"+label]=[int(m[k]) for k in (1,2,3)]
            expected_extern={}
            for krate in ("ruff_python_ast","ruff_python_parser"):
                lib,=[x for x in typed if x["target"]["name"]==krate and "lib" in x["target"]["kind"]]
                archive,=[p for p in lib["filenames"] if p.endswith(".rlib")]
                expected_extern[krate]=archive
            expected=64 if summary["rev"]=="b5dba861cc38e3f7fb4524c9ceba3e01a474ea13" else 56
            assert expected==summary["expr_bytes"]
            for size in (64,56):
                p=check_process(stage,f"size-{size}")
                args=p["args"];assert args[:2]==["rustc","+ohm"] and "--emit=metadata" in args
                actual=dict(args[i+1].split("=",1) for i,x in enumerate(args[:-1]) if x=="--extern")
                assert actual==expected_extern and p["exit"]==(0 if expected==size else 1)
                if size!=expected:
                    errs=[json.loads(l) for l in (stage/f"size-{size}.stderr").read_bytes().splitlines()]
                    assert any(e.get("code") and e["code"]["code"]=="E0308" for e in errs)
                counts["size_accepted" if size==expected else "size_rejected_E0308"]+=1
    assert diagnostics["P"]==diagnostics["Q"] and len(clean)==4 and counts==dict(traced=4,ordinary=30,representative_passes=96,size_accepted=32,size_rejected_E0308=32)
    return {"toolchain":{"drivers":DRIVERS,"cargo":CARGO,"wild":WILD},"tests":TESTS,"counts":dict(counts),"diagnostics":diagnostics,"empty_suites_pass_fail_ignore":clean,"minimum_observed_before_or_after_Cargo_bytes":{k:min(x[k] for x in limits) for k in limits[0]}}
if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raw",type=Path)
    print(json.dumps(run(ap.parse_args().raw),sort_keys=True,indent=2))
