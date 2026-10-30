"""Independently reopen the whole original formatter confirmation and emit a shareable projection."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import digest_file, native

MANIFEST="8644de8014088c0bed294eaf900c89ab25d0f4bb36a784728647c7526e4165fd"
COMMAND=["cargo","+ohm","test","-p","ruff_python_formatter","--lib","--no-run","--locked","--offline","-j4","--message-format=json"]
REVISIONS={"A":"b5dba861cc38e3f7fb4524c9ceba3e01a474ea13","B":"7b13f01ba1569887a25670820764b24c206da8e5"}
ELFS={"A":"f4adc9d02e7830adb6d2ff7670b8588cf645fd1a39863dbc0c8abba270becd52","B":"0252a7a7873113c21cb22c81c186a3583dd0064d16912a400532e27b4c0a7ca9"}
DRIVERS={"P":"66380b2752a864d14799b7931e011d4ff55ce4e326a5b77e80d8b06d9dfddd5e","Q":"b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c"}
CARGO="1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add"
WILD="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
TESTS=["tests::basic","tests::string_processing","comments::tests::parenthesized_expression"]
STAGES=["empty-A","first-B","return-A","return-B","unchanged-B"]
CONTROLS=["empty-B","first-A","return-B-native","return-A-native","invalid-A","recovered-A","unchanged-A"]
def load(f):return json.loads(f.read_bytes())
def hashed(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def read_process(stage,name):
    p=load(stage/(name+".process.json"))
    for s in ["stdout","stderr"]:assert digest_file(stage/(name+"."+s))==p[s]
    for limits in (p["before"],p["after"]):
        assert all(limits[k]>x*2**30 for k,x in [("memory",52),("home",140),("scratch",133)]) and limits["private"]>650*1024**2
    return p

def condensed_unit(row):
    who,tail=row["package_id"].split("#",1)
    if who.startswith("path+") and "@" not in tail:
        tail=Path(who).name+"@"+tail
    return [tail,row["target"]["name"],row["target"]["kind"],row["profile"]["test"],row["features"],row["profile"],row["target"]["crate_types"],[Path(f).name for f in row["filenames"]]]

def reading_storage(p,row):
    assert digest_file(p/"incremental.json.gz")==row["table_sha256"]
    items=json.loads(gzip.decompress((p/"incremental.json.gz").read_bytes()))
    groups={};multiplicity=Counter();names=set()
    for root,rel,group,allocated,length,links,mode in items:
        assert root in (0,1) and (root,rel) not in names and not Path(rel).is_absolute() and ".." not in Path(rel).parts and "incremental" in Path(rel).parts
        assert allocated%512==0 and length>=0 and links>0 and group>=0
        names.add((root,rel));v=(allocated,length,links,mode)
        assert groups.setdefault(group,v)==v
        multiplicity[group]+=1
    assert len(groups)==row["unique_inodes"] and len(names)==row["paths"]
    assert sum(v[0] for v in groups.values())==row["allocated_unique_bytes"]
    assert sum(v[1] for v in groups.values() if v[3]==stat.S_IFREG)==row["regular_apparent_unique_bytes"]
    # An anonymous histogram permits recomputing physical bytes, hardlink collapse, and pathname totals offline.
    grouped=Counter((v[0],v[3],multiplicity[k]) for k,v in groups.items())
    return {"incremental_allocated_bytes":row["allocated_unique_bytes"],"incremental_apparent_bytes":row["regular_apparent_unique_bytes"],
            "storage_ledger_sha256":row["table_sha256"],"storage_paths":len(items),"storage_inodes":len(groups),
            "physical_block_histogram":[[a,m,u,c] for (a,m,u),c in sorted(grouped.items())]}

def expect_native(stage,objects,row):
    n=native(stage,objects)
    if objects:
        assert n["full"]==row["actual_compile"] and n["cached"]==row["actual_cached"] and n["tools"].get("wild",0)==row["actual_wild"]
        assert n["cgus_opened_for_creation"]==row["actual_cgus"] and n["raw_trace_sha256"]==row["trace_archive"]
    else:
        d=row["exec_only"]
        # The acquisition decoder may describe rustc target/version probes as pseudo-compilations in a cold command.
        # Preserve each of those physical native probes separately from real crate compilations.
        real=dict(d["full"]);pseudo=real.pop("___",0)
        assert real==n["full"] and (not pseudo or pseudo==n["probes"].get('target_print',0)),(stage.name,real,n["full"],pseudo,n["probes"])
        assert d["cached"]==n["cached"] and d["threads"]==n["threads"] and d["trace_sha256"]==n["raw_trace_sha256"]
        for k in ("cc_or_gcc","collect2","wild"):assert d["tools"].get(k,0)==n["tools"].get(k,0),(k,d["tools"],n["tools"])
    return n

def collect(root):
    ops=root/"ops";cfg=load(ops/"schedule.json");reg=load(root/"registration.json")
    assert digest_file(ops/"SHA256SUMS")==reg["manifest"]==MANIFEST
    for line in (ops/"SHA256SUMS").read_text().splitlines():
        dg,name=line.split("  ");assert digest_file(ops/name)==dg,name
    assert load(root/"terminal.json")["exit"]==0
    allterm=load(root/"complete.json")["terminals"];assert set(allterm)==set(cfg["order"])
    valid={};controls={};tool_receipts={};catalog=None;test_names=None
    for slot in cfg["order"]:
        folder=root/"runs"/slot;admission=slot.startswith(("admit-","post-"));arm=slot[-1]
        stages=CONTROLS if admission else STAGES
        identity=load(folder/"identity.json");e=load(folder/"entry.json")["room"]
        assert all(e[k]>v*2**30 for k,v in [("home",145),("scratch",135),("memory",75)])
        assert load(folder/"terminal.json")["exit"]==0 and digest_file(folder/"complete.json")==allterm[slot]
        assert identity["empty"] and identity["cpu"]==[28,29,30,31] and identity["plan"]==MANIFEST and identity["crates"]==505 and identity["index"]==465
        assert [identity[k] for k in ["driver","cargo","wild"]]==[DRIVERS[arm],CARGO,WILD]
        tool_receipts[slot]={"complete":allterm[slot],"entry":digest_file(folder/"entry.json"),"input_identity":digest_file(folder/"identity.json"),"driver":identity["driver"],"product":identity["product"],"health_before":e}
        rr={};copy=load(folder/"complete.json")["rows"];assert set(copy)==set(stages)
        for name in stages:
            p=folder/name;row=load(p/"result.json");assert all(copy[name][k]==v for k,v in row.items())
            proc=read_process(p,"cargo");argv=proc["args"];assert argv[-len(COMMAND):]==COMMAND
            is_return_trace=name.endswith("-native")
            assert (argv==COMMAND)==(not admission)
            if admission:assert argv[0]=="strace" and (("trace=execve,execveat,exit_group,openat,creat" in argv)==is_return_trace)
            assert row["rev"] in REVISIONS.values();rev=next(k for k,v in REVISIONS.items() if row["rev"]==v)
            assert rev==("B" if name.startswith("empty-B") or name in ("first-B","return-B","unchanged-B","return-B-native") else "A")
            messages=[json.loads(line) for line in (p/"cargo.stdout").read_bytes().splitlines()]
            assert messages[-1]=={"reason":"build-finished","success":name!="invalid-A"}
            item={"revision":rev,"exit":proc["exit"],"cargo_stdout":proc["stdout"],"cargo_stderr":proc["stderr"],"row_sha256":digest_file(p/"result.json"),
                  "wall_ns":proc["elapsed_ns"],"user_s":proc["user_s"],"system_s":proc["sys_s"],"usage_before":proc["before"],"usage_after":proc["after"]}
            if admission:item["native"]=expect_native(p,is_return_trace,row)
            if name=="invalid-A":
                errs=[]
                for d in [v["message"] for v in messages if v["reason"]=="compiler-message" and v["message"]["level"]=="error" and v["message"].get("code")]:
                    if any("OHM_FORMATTER_BRANCH_TYPE_GUARD" in t["text"] for s in d["spans"] for t in s["text"]):
                        errs.append([d["code"]["code"],d["message"],[[s["file_name"],s["line_start"],s["column_start"]] for s in d["spans"] if s["is_primary"]]])
                assert errs==row["diagnostics"]==[["E0308","mismatched types",[["crates/ruff_python_formatter/src/lib.rs",410,45]]]] and proc["exit"]==101
                item["diagnostics"]=errs;rr[name]=item;continue
            assert proc["exit"]==0
            typed=[v for v in messages if v["reason"]=="compiler-artifact"]
            ordered=sorted([(condensed_unit(v),v) for v in typed],key=lambda x:repr(x[0]))
            units=[u for u,_ in ordered]
            if catalog is None:catalog=units
            assert len({json.dumps(x,sort_keys=True) for x in units})==216
            assert catalog==units and len(catalog)==row["typed"]==216
            dirty=[i for i,(_,x) in enumerate(ordered) if not x["fresh"]]
            assert len(dirty)==len(row["dirty"])
            executable,=[x["executable"] for x in typed if x["target"]["name"]=="ruff_python_formatter" and x["profile"]["test"] and x["executable"]]
            assert row["elf"]==ELFS[rev]
            ls=read_process(p,"list");assert ls["exit"]==0 and ls["args"]==[executable,"--list","--format","terse"]
            names=[line[:-6] for line in (p/"list.stdout").read_text().splitlines() if line.endswith(": test")]
            if test_names is None:test_names=names
            assert names==test_names and len(set(names))==row["tests"]==53 and ls["stdout"]==row["inventory"]
            checked={}
            for i,test in enumerate(TESTS):
                t=read_process(p,f"test-{i}");assert t["exit"]==0 and t["args"]==[executable,"--exact",test,"--test-threads=1"] and f"test {test} ... ok" in (p/f"test-{i}.stdout").read_text()
                checked[test]=[t["stdout"],t["stderr"]]
            full=None
            if name in ["empty-A","empty-B"]:
                assert row["whole_runtime"];t=read_process(p,"all-tests");assert t["exit"]==0 and t["args"]==[executable,"--test-threads=1"]
                f=re.search(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;",(p/"all-tests.stdout").read_text());assert f
                full=[int(x) for x in f.groups()];assert full==[51,0,2]
            else:assert not row["whole_runtime"]
            ex={}
            for krate in ("ruff_python_ast","ruff_python_parser"):
                lib,=[v for v in typed if v["target"]["name"]==krate and "lib" in v["target"]["kind"]]
                q,=[f for f in lib["filenames"] if f.endswith(".rlib")];ex[krate]=q
            oracle={}
            expected=64 if rev=="A" else 56;assert row["expr_bytes"]==expected
            for size in [64,56]:
                t=read_process(p,f"size-{size}");args=t["args"];assert args[:2]==["rustc","+ohm"] and t["exit"]==(0 if size==expected else 1)
                assert dict(args[i+1].split("=",1) for i,k in enumerate(args[:-1]) if k=="--extern")==ex
                ec=[]
                if size!=expected:
                    ec=[x["code"]["code"] for x in (json.loads(l) for l in (p/f"size-{size}.stderr").read_bytes().splitlines()) if x.get("code")]
                    assert "E0308" in ec
                oracle[str(size)]={"exit":t["exit"],"diagnostic_codes":ec,"stdout":t["stdout"],"stderr":t["stderr"]}
            item.update(elf=row["elf"],size_oracle=oracle,git_ns=row["git_switch_ns"],dirty=dirty,
                        test_inventory=ls["stdout"],representative_tests=checked,complete_suite=full)
            item.update(reading_storage(p,row["allocation"]))
            assert (item["git_ns"]>0)==(name in ["first-A","first-B","return-A","return-B","return-A-native","return-B-native"])
            rr[name]=item
        (controls if admission else valid)[slot]=rr
    elf_cas={}
    for rev,sig in ELFS.items():
        f=root/"elf"/(sig+".zst");child=subprocess.Popen(["zstd","-qdc",f],stdout=subprocess.PIPE)
        h=hashlib.sha256();size=0
        with child.stdout as reader:
            magic=reader.read(4);assert magic==b"\x7fELF";h.update(magic);size=4
            while part:=reader.read(2**20):h.update(part);size+=len(part)
        assert child.wait()==0 and h.hexdigest()==sig
        elf_cas[rev]={"sha256":sig,"bytes":size,"compressed_sha256":digest_file(f)}
    return {"schema":1,"protocol_manifest":MANIFEST,"schedule_sha256":digest_file(ops/"schedule.json"),"analyzer_sha256":digest_file(ops/"analyze.py"),
            "registration_archive":reg["bundle"],"registration_time":reg["registered_ns"],"terminal":digest_file(root/"terminal.json"),
            "supervisor_complete":digest_file(root/"complete.json"),"root_sources":REVISIONS,"cargo":CARGO,"wild":WILD,"drivers":DRIVERS,
            "slot_receipts":tool_receipts,"ordered_typed_inventory":catalog,"listed_tests":test_names,"elf_cas":elf_cas,"slots":valid,"controls":controls}
if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("raw",type=Path);args=ap.parse_args()
    print(json.dumps(collect(args.raw),sort_keys=True,separators=(",",":")))
