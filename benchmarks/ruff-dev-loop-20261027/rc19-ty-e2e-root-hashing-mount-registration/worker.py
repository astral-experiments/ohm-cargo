"""Run one frozen stable-path root-only Ruff action; qualify it outside the measurement region."""
import argparse
import collections
import re
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from names import kernel_rows,ordered,own_recipe
from verdict import runtime

def profile_verify(d,img):
    costs=list(d.glob("ir.*"));logs=list(d.glob("vg.*"))
    assert len(costs)==len(logs)==1 and costs[0].suffix==logs[0].suffix,([p.name for p in costs],[p.name for p in logs])
    fields={}
    with costs[0].open() as stream:
        for line in stream:
            k,sep,v=line.partition(":")
            if k in ("pid","cmd","part","events","summary","totals"):
                assert k not in fields
                fields[k]=v.strip()
    vg=logs[0].read_text()
    collected,=re.findall(r"Collected\s*:\s*([\d,]+)",vg)
    references,=re.findall(r"I\s+refs:\s*([\d,]+)",vg)
    amount=int(fields["totals"]); assert fields["events"]=="Ir" and amount>1_000_000 and amount==int(collected.replace(",",""))==int(references.replace(",",""))
    pid=int(costs[0].suffix[1:]); assert fields["pid"]==str(pid) and fields["part"]=="1"
    command=fields["cmd"].split();candidate=Path(command[0])
    assert command[1:]==ARGS[2:] and candidate.samefile(M/"sdk/bin/cargo") and rawsha(candidate)==img["sha256"]
    assert not any(x in vg.lower() for x in ("illegal instruction","fatal","unhandled instruction"))
    assert "callgrind-amd64-linux" in (d/("exec."+str(pid))).read_text()
    for f in d.glob("exec.*"):
        if f.suffix[1:]!=str(pid):
            assert not any("callgrind-amd64-linux" in l and l.startswith("execve(") and l.endswith("= 0") for l in f.read_text(errors="replace").splitlines())
    put(d/"instructions.json",{"ir":amount,"summary":int(fields["summary"]),"parts":1,"pid":pid,"cargo":img["sha256"],"cost_file":rawsha(costs[0]),"tool_log":rawsha(logs[0])})

def lives(d,lane,mode,need,how,side=None):
    live=get(d/"native.json") if how=="native" else None
    rows=live["events"] if live else kernel_rows(d)
    full=[r for r in rows if r["role"]=="rustc-full" and r["target"]!="___"]
    cached=[r for r in rows if r["role"]=="rustc-link-only"]
    link=[r for r in rows if r["role"]=="stock-wild"]
    tools={r:[x for x in rows if x["role"]==r and x["out"]==str(E2E)] for r in ("stock-wild","gcc","collect2")}
    census={"full":[r["target"] for r in full],"cached":[r["target"] for r in cached],"wild_total":len(link),"root_native":{k:len(v) for k,v in tools.items()}}
    put(d/"launches.json",census)
    assert not cached
    if live:
        assert live["root_exit"]==(101 if mode=="invalid" else 0)
        registered=[r for r in rows if r["role"]=="cargo"]
        assert len(registered)==1 and registered[0]["argv"][1:]==ARGS[2:]
        for r in (full+sum(tools.values(),[])):
            status=live["process_exit"][str(r["pid"])]
            assert status==(1 if mode=="invalid" and r["role"]=="rustc-full" else 0),(r["role"],r["target"],status)
    if need=="settled":
        assert not full and not link and all(not t for t in tools.values())
    elif mode=="invalid":
        assert [r["target"] for r in full]==["e2e"] and not link and all(not t for t in tools.values())
    elif need in ("dirty","leaf"):
        assert [r["target"] for r in full]==["e2e"] and len(link)==1 and all(len(t)==1 for t in tools.values()),census
    elif need=="cold":
        assert len(full)>=300 and len(link)>=30 and len([r for r in full if r["target"]=="e2e"])==1 and all(len(t)==1 for t in tools.values()),census
    if side and need in ("dirty","leaf","cold"):
        descriptor,raw=ordered(rows,side,with_input_bytes=bool(live))
        put(d/"native-descriptor.json",descriptor)
        put(d/"raw-selected-argv-digests.json",raw)
        return descriptor

def run(lane,arm,label,mode,how,need):
    safe_name(lane);safe_name(label)
    assert how in ("native","ordinary","profile","io") and need in ("train","settled","dirty","cold","leaf")
    assert mode in ("original","edited","invalid")
    if label.startswith(("primary-","wall-")):
        grant=get(K/"binding/score-grant.json")
        assert grant["go"] and grant["preflight"]==rawsha(K/"binding/native-admission.json")
    d=REPORTS/lane/label
    env=trusted();img=enrolled(arm)
    mounts=mount_evidence(img["cargo"],img["sha256"])
    put(d/"kernel-mounts.json",mounts)
    tools=get(M/"qualification/native-tools.json")
    tools["images"]["cargo"]={"path":str(M/"sdk/bin/cargo"),"sha256":img["sha256"]}
    tools["selected_output"]=str(E2E)
    sources=source(mode)
    if need=="cold":
        assert not list((LIVE/"target").iterdir()) and not list((LIVE/"shared").iterdir())
    if need=="leaf":
        assert not E2E.exists() and not list(E2E.parent.parent.iterdir()) and not list(INC.iterdir())
        assert not (LIVE/"target/debug/deps"/NAME).exists()
    before=datafile(E2E) if E2E.exists() else None
    version=prior.A.process(d,"cargo-version",["cargo","+ohm","-Vv"],ROOT,env)
    assert version["status"]==0 and (d/"cargo-version.stdout").read_text()==get(Path(img["cargo"]).parent/"receipt.json")["version"]
    if how=="native":
        put(d/"contract.json",tools)
        cmd=["/usr/bin/python3","-IB",str(K/"ops/native.py"),str(d/"native.json"),str(d/"contract.json"),*ARGS]
    elif how=="io":
        cmd=["strace","-ff","-qq","-yy","-s","512","-e",
             "trace=execve,clone,clone3,open,openat,openat2,read,readv,pread64,preadv,newfstatat,statx,fstat,unlink,unlinkat","-o",str(d/"io"),*ARGS]
    elif how=="profile":
        cmd=["strace","-ff","-qq","-s","262144","-e","trace=execve","-o",str(d/"exec"),"/usr/bin/valgrind","--tool=callgrind","--vgdb=no","--cache-sim=no","--branch-sim=no","--trace-children=yes",
             "--trace-children-skip=*/rustc,*/rustdoc,*/cc,*/gcc,*/collect2,*/ld.bfd,*/git,*/build-script-build","--child-silent-after-fork=yes","--log-file="+str(d/"vg.%p"),"--callgrind-out-file="+str(d/"ir.%p"),"--error-exitcode=97",*ARGS]
    else:
        cmd=ARGS
    put(d/"command.json",{"lane":lane,"arm":arm,"selected":img["sha256"],"mode":mode,"how":how,"require":need,"source":sources,"before":before,"argv":cmd,
                         "zero_compiler_or_linker_overrides":not any(k in env for k in ("RUSTC","RUSTC_WRAPPER","RUSTFLAGS","LD_PRELOAD")),"child_env":env,"cpu":sorted(os.sched_getaffinity(0)),
                         "namespace":os.readlink("/proc/self/ns/mnt"),"mounts":list(mounts["mounts"])})
    with (d/"cargo.stdout").open("xb") as so,(d/"cargo.stderr").open("xb") as se:
        a=time.perf_counter_ns()
        proc=subprocess.run(cmd,cwd=ROOT,env=env,stdout=so,stderr=se,timeout=1250)
        b=time.perf_counter_ns()
    put(d/"exit.json",{"status":proc.returncode})
    if how=="ordinary" and label.startswith("wall-") and need=="dirty":
        put(d/"clock.json",{"start_ns":a,"end_ns":b,"elapsed_ns":b-a,"status":proc.returncode})
    assert proc.returncode==(101 if mode=="invalid" else 0),(d,proc.returncode)
    transcript=[json.loads(x) for x in (d/"cargo.stdout").read_bytes().splitlines()]
    assert transcript[-1]=={"reason":"build-finished","success":proc.returncode==0}
    arts=[x for x in transcript if x["reason"]=="compiler-artifact"]
    errors=[m["message"] for m in transcript if m["reason"]=="compiler-message" and m["message"]["level"]=="error"]
    roster=typed_identity(arts)
    full_roster=expected_roster()
    if mode=="invalid":
        assert len(arts)==299 and roster==[x for x in full_roster if x["target"]["name"]!="e2e"]
        assert errors and all((e.get("code") or {}).get("code")=="E0308" and any(s["is_primary"] and s["line_start"]==22 and s["file_name"].endswith(str(EDIT)) for s in e["spans"]) for e in errors)
    else:
        assert len(arts)==300 and roster==full_roster and not errors
    fresh=sum(x["fresh"] for x in arts)
    if need=="cold":assert fresh==0
    if need=="settled":assert fresh==300
    if need in ("leaf","dirty"):
        assert fresh==299 and all(x["fresh"] for x in arts if x["target"]["name"]!="e2e"),(d,fresh)
    put(d/"typed-roster.json",roster)
    closure=artifacts(transcript)
    assert len(closure["typed_files"])==553 and len(closure["build_script_outputs"])==30
    put(d/"dependencies.json",closure)
    donor=K/"binding/donor.json"
    if donor.exists() and not lane.startswith("cold-"):
        assert get(donor)["dependencies"]==rawsha(d/"dependencies.json"),"changed full non-root graph"
    result={"source":mode,"exit":proc.returncode,"units":len(arts),"fresh":fresh,"dependencies":rawsha(d/"dependencies.json"),"typed":rawsha(d/"typed-roster.json"),"diagnostics":errors,"full_origin":need}
    if mode=="invalid":
        if how=="native":lives(d,lane,mode,need,how)
        put(d/"result.json",result)
        return
    selected,=[x for x in arts if x["target"]["name"]=="e2e" and x["executable"]]
    assert E2E==Path(selected["executable"])
    result["e2e"]=datafile(E2E)
    side=prior.rawfiles(E2E)
    put(d/"untracked-sidecars.json",side)
    put(d/"root-current-recipe.json",own_recipe(side))
    if need in ("dirty","cold","leaf"):
        present=side["manifest"]
        assert bool(present)==(arm=="parent"),(d,present)
        if present:assert not present["unused_present"]
    if how in ("native","profile"):
        lives(d,lane,mode,need,how,side)
    if how=="profile":profile_verify(d,img)
    if how=="io":
        put(d/"post.json",{"e2e_path":str(E2E)})
        prior.module("input_io",M/"ops/io-proof.py").verify(d,arm)
    checks=runtime(d,mode,env,transcript,full=how=="native" and need!="settled")
    result["verdicts"]=checks
    if mode=="original":
        assert result["e2e"]["sha256"]==get(REF)["product"]["sha256"],"original baseline e2e bytes changed"
    if mode=="edited":
        assert result["e2e"]["sha256"]!=get(REF)["product"]["sha256"]
    if need=="cold" or (lane=="train" and need=="settled"):
        from cold import diagnostics
        diagnostics(d,closure,env)
    reference=K/"binding/native-admission.json"
    if reference.exists():
        assert result["e2e"]==get(reference)["elf"][mode],(arm,label,"unmatched complete ELF")
    put(d/"result.json",result)

if __name__=="__main__":
    run(*sys.argv[1:])
