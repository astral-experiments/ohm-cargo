#!/usr/bin/env python3
"""Project native reregistration results from the held workspace, terminal and independent ELF table."""
from pathlib import Path
import argparse
import collections
import gzip
import hashlib
import json
import re

def h(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def rd(p):
    return json.loads(p.read_bytes())

def syscalls(file):
    unfinished={}
    with file.open() as f:
        for number,text in enumerate(f,1):
            line=text.rstrip("\n")
            if line.endswith("<unfinished ...>"):
                syscall=line.partition("(")[0];assert syscall not in unfinished
                unfinished[syscall]=line[:-len("<unfinished ...>")];continue
            if line.startswith("<... "):
                name,sep,tail=line.partition(" resumed>");assert sep
                line=unfinished.pop(name[5:])+tail
            yield number,line
    assert not unfinished

def confirmed_fds(raw, traces, wild, lookup):
    selected={}
    seen_tids=set()
    for pid_s,ledger in lookup.items():
        pid=int(pid_s);assert pid in wild and wild[pid]["output"]==ledger["output"] and pid==ledger["tid"]
        family=set(ledger["family"]);assert pid in family and not (family&seen_tids);seen_tids|=family
        desired=collections.defaultdict(set)
        # Validate every claimed positive fd, including literal path, syscall, pid and returned descriptor.
        for tid,seq,role,op,answer in ledger["matches"]:
            if op.startswith("openat") and answer.isdecimal():desired[tid].add((seq,role,op,int(answer)))
        assert set(desired)<=family
        parents={};hits=[]
        for tid in sorted(family):
            f=raw/("exec."+str(tid))
            if not f.exists():
                assert tid not in desired;continue
            for seq,line in syscalls(f):
                call=line.partition("(")[0];value=line.rsplit(" = ",1)[-1].strip()
                if call in ("fork","vfork","clone","clone3") and value.isdigit() and int(value)>0:
                    child=int(value)
                    if child in family:parents[child]=tid
                if call not in ("openat","openat2") or not value.isdigit():continue
                for role,path in traces.items():
                    if '"'+path+'"' in line:hits.append((tid,seq,role,call,int(value)))
        assert set(hits)=={(tid,*row) for tid,items in desired.items() for row in items}
        for tid in {e[0] for e in hits}:
            walk=set()
            while tid!=pid:
                assert tid in parents and tid not in walk;walk.add(tid);tid=parents[tid]
        actual=sorted({v[2] for v in hits});assert actual==ledger["pos"]
        selected[pid]={"roles":actual,"positive_descriptors":len(hits),"threads_reaching_fd":len({w[0] for w in hits})}
    return selected

def project(cases,ref,independent,tiny):
    phases=rd(cases/"terminal.json");enrollment=rd(cases/"binding.json");summary=rd(independent/"verified.json")
    original=rd(ref);authority=rd(tiny/"terminal.json");actual_targets=enrollment["tuple_eligibility"]
    assert len(actual_targets)==len(set(actual_targets.values()))==50 and set(actual_targets)==set(original["selected"])
    assert summary["command_terminal"]==h(cases/"terminal.json") and summary["direct_shared_plus_exec"]==h(tiny/"terminal.json") and summary["per_target"]==h(independent/"per-target.json")
    bytarget={v:k for k,v in actual_targets.items()};fixed=sorted(actual_targets);ver=rd(independent/"per-target.json")
    paths={"provider":str(Path(enrollment["psm_path"])/"libgcc_s.so"),"hook":enrollment["provider"]}
    for category in ("exe","shared"):
        direct=authority["direct_control"]
        assert [direct[name][category]["run"]["exit"] for name in ("baseline","higher","restored")]==[0,83,0] and direct["malformed"][category]["status"]["exit"]!=0
        assert direct["baseline"][category]["file"]==direct["restored"][category]["file"]
    before={k:original["selected"][k]["sha256"] for k in fixed}
    inventory={k:original["selected"][k]["list_sha256"] for k in fixed};result={};actualfiles=set()
    for label,case_sha in sorted(phases["completed"].items()):
        d=cases/label;r=rd(d/"complete.json");p=summary["cases"][label];assert h(d/"complete.json")==case_sha==p["receipts"]["case"]
        assert h(d/"native-jobs.json.gz")==r["native"]["native_jobs"] and h(d/"cargo.stdout")==r["cargo"]["stdout"] and h(d/"cargo.stderr")==r["cargo"]["stderr"]
        job=json.load(gzip.open(d/"native-jobs.json.gz"));roles=collections.Counter(j["kind"] for j in job)
        wild={j["tid"]:j for j in job if j["kind"]=="wild"};wt={j["output"]:j for j in wild.values()}
        assert len(wild)==len(wt)==p["wild"] and sum(x in bytarget for x in wt)==p["fixed50_wild"]
        fd=confirmed_fds(d/"trace",paths,wild,r["provider_opens"]);expected={}
        for name,path in actual_targets.items():
            if path not in wt:continue
            j=wt[path];argv=j["args"];assert len([x for x in argv if x=="-L"+enrollment["psm_path"]])==1 and argv.index("-L"+enrollment["psm_path"])<argv.index("-lgcc_s")
            expected[name]=j
        assert sorted(set(fixed)-set(expected))==p["unstarted_fixed50"]
        participants={};streams={};runtime=collections.Counter()
        if p["cargo"]==0:
            assert set(ver[label])==set(r["names"])==set(fixed) and len(r["names"])==50 and r["units"]==619
            for name,rr in r["names"].items():
                a=ver[label][name];pid=expected[name]["tid"] if name in expected else None
                assert [rr["exit"],rr["sha256"],pid]==a[:3]
                if pid is not None:assert rr["wild_pid"]==pid
                pr=fd.get(pid);assert (pr["roles"] if pr is not None else None)==a[3]
                if rr["exit"]==83:assert rr["hook_present"] and not (d/rr["list_path"]).stat().st_size
                elif rr["exit"]==0:assert not rr["hook_present"] and h(d/rr["list_path"])==inventory[name]
                else:raise AssertionError((label,name,rr["exit"]))
                participants[name]={"exit":rr["exit"],"elf":rr["sha256"],"bytes":rr["bytes"],"list_sha256":rr["listing"],"real_wild":pid is not None,"positive_fds":None if pr is None else pr,"native_hook_symbol":rr["hook_present"]}
                actualfiles.add(rr["sha256"]);runtime[rr["exit"]]+=1
                for testcase,rrcase in rr["cases"].items():
                    ix=list(rr["cases"]).index(testcase);f=d/rr["list_path"]; matching=[p for p in f.parent.glob("case-*.stdout") if h(p)==rrcase["stdout"] and ("test "+testcase+" ... ok").encode() in p.read_bytes().splitlines()];assert len(matching)==1 and rrcase["exit"]==0
                    streams[testcase]=rrcase["stdout"]
            if r["mode"]=="absent":assert len(streams)==3
        else:
            assert p["cargo"]==101 and r["mode"]=="bad" and r["bad_diagnostic"]
            content=(d/"cargo.stdout").read_bytes()+(d/"cargo.stderr").read_bytes()
            assert b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in content and b"libgcc_s.so" in content and any("provider" in v["roles"] for v in fd.values())
        result[label]={"cargo":p["cargo"],"full":sum(k["kind"]=="rustc-full" and "--crate-name" in k["args"] for k in job),"cached":p["cached"],"cc":roles["gcc"],"collect2":roles["collect2"],"wild":len(wild),"typed":r["units"],"fresh":r["fresh"],"fixed_fifty_linked":sorted(expected),"fixed_not_launched":sorted(set(fixed)-set(expected)),"runtime":dict(runtime),"per_target":participants,"test_assertions":streams,"malformed_native_diagnostic":r.get("bad_diagnostic",False),"traced_wild_families":len(fd),"all_wild_with_positive_script_fd":sum("provider" in a["roles"] for a in fd.values()),"all_wild_with_positive_object_fd":sum("hook" in a["roles"] for a in fd.values()),"fixed_fd_targets":{k:fd[j["tid"]] for k,j in expected.items() if j["tid"] in fd},"raw":{"entered":h(d/"entered.json"),"cargo_stdout":h(d/"cargo.stdout"),"cargo_stderr":h(d/"cargo.stderr"),"link_jobs":h(d/"native-jobs.json.gz"),"case":case_sha,"raw_trace_family":r["native"]["raw_sha256"]}}
    assert actualfiles==set(summary["body_hashes"]) and phases["final_provider_absent"]
    return {"rust":"ad005f99d0b51fd62b5c237bc13b31b371a1686e","cargo":"7277e6cdaba44c43294a07c0661fc8e69fd8e3e7","cargo_elf":enrollment["role"]["cargo_sha256"],"stock_wild":authority["stock_wild"],"system_gcc_script_sha":phases["system_provider"],"provider_source":h(tiny/"provider.s"),"object_sha":h(tiny/"provider.o"),"direct":{"single_executable_and_loaded_shared":[0,83,"link-failed",0],"terminal":h(tiny/"terminal.json")},"baseline":before,"inventory":inventory,"real_body_lengths":summary["body_hashes"],"cases":result,"receipts":{"old_619":summary["source_matched_third"],"copy_hardlinks":summary["floor_custody"],"v1_excluded":phases["preserved_exclusion"],"v2_registered":phases["v2_plan"],"exdev_forced_zero_cargo":phases["prior_exdev"],"mount_adapter":phases["same_mount_amendment"],"commands":h(cases/"terminal.json"),"independent_full_elf_sha":h(independent/"verified.json"),"fixed_target_matrix":summary["per_target"]}}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ("cases","reference","independent","authority"):ap.add_argument("--"+k,type=Path,required=True)
    args=ap.parse_args();print(json.dumps(project(args.cases,args.reference,args.independent,args.authority),sort_keys=True,indent=2))
