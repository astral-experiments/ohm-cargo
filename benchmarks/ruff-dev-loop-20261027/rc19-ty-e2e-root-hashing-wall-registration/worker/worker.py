"""Run one frozen stable-path root-only Ruff action; qualify it outside the measurement region."""
import re
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from names import kernel_rows,ordered,own_recipe
from verdict import runtime
from wire import acquire,prove

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
    if side and need in ("dirty","leaf"):
        descriptor,raw=ordered(rows,side,with_input_bytes=bool(live))
        put(d/"native-descriptor.json",descriptor)
        put(d/"raw-selected-argv-digests.json",raw)
        return descriptor

def run(lane,arm,label,mode,how,need):
    safe_name(lane);safe_name(label)
    assert how in ("native","ordinary","io") and need in ("settled","dirty","leaf")
    assert mode in ("original","edited","invalid")
    if label.startswith("pair-"):
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
    if need=="leaf":
        assert not E2E.exists() and not list(E2E.parent.parent.iterdir()) and not list(INC.iterdir())
        assert not (LIVE/"target/debug/deps"/NAME).exists()
    before=datafile(E2E) if E2E.exists() else None
    acquire(d, "before")
    version=prior.A.process(d,"cargo-version",["cargo","+ohm","-Vv"],ROOT,env)
    assert version["status"]==0 and (d/"cargo-version.stdout").read_text()==get(Path(img["cargo"]).parent/"receipt.json")["version"]
    if how=="native":
        put(d/"contract.json",tools)
        cmd=["/usr/bin/python3","-IB",str(K/"ops/native.py"),str(d/"native.json"),str(d/"contract.json"),*ARGS]
    elif how=="io":
        cmd=["strace","-ff","-qq","-yy","-s","512","-e",
             "trace=execve,clone,clone3,open,openat,openat2,read,readv,pread64,preadv,newfstatat,statx,fstat,unlink,unlinkat","-o",str(d/"io"),*ARGS]
    else:
        cmd=ARGS
    put(d/"command.json",{"lane":lane,"arm":arm,"selected":img["sha256"],"mode":mode,"how":how,"require":need,"source":sources,"before":before,"argv":cmd,
                         "zero_compiler_or_linker_overrides":not any(k in env for k in ("RUSTC","RUSTC_WRAPPER","RUSTFLAGS","LD_PRELOAD")),"child_env":env,"cpu":sorted(os.sched_getaffinity(0)),
                         "namespace":os.readlink("/proc/self/ns/mnt"),"mounts":list(mounts["mounts"])})
    with (d/"cargo.stdout").open("xb") as so,(d/"cargo.stderr").open("xb") as se:
        a=time.perf_counter_ns()
        proc=subprocess.run(cmd,cwd=ROOT,env=env,stdout=so,stderr=se,timeout=None if how=="ordinary" else 1250)
        b=time.perf_counter_ns()
    put(d/"exit.json",{"status":proc.returncode})
    acquire(d, "after")
    if how=="ordinary" and re.fullmatch(r"pair-[0-9]{2}-edit",label) and need=="dirty":
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
    if need=="settled":assert fresh==300
    if need in ("leaf","dirty"):
        assert fresh==299 and all(x["fresh"] for x in arts if x["target"]["name"]!="e2e"),(d,fresh)
    put(d/"typed-roster.json",roster)
    closure=artifacts(transcript)
    assert len(closure["typed_files"])==553 and len(closure["build_script_outputs"])==30
    put(d/"dependencies.json",closure)
    donor=K/"binding/donor.json"
    if donor.exists() :
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
    recipe=own_recipe(side)
    put(d/"root-current-recipe.json",recipe)
    if need in ("dirty","leaf"):
        present=side["manifest"]
        assert bool(present)==(arm=="parent"),(d,present)
        if present:assert not present["unused_present"]
    if how=="native":
        lives(d,lane,mode,need,how,side)
    if need in ("dirty","leaf"):
        prove(d,mode,recipe,how=="native")
    if how=="io":
        put(d/"post.json",{"e2e_path":str(E2E)})
        prior.module("input_io",M/"ops/io-proof.py").verify(d,arm)
    checks=runtime(d,mode,env,transcript,full=how=="native" and need!="settled")
    result["verdicts"]=checks
    if mode=="original":
        assert result["e2e"]["sha256"]==get(REF)["product"]["sha256"],"original baseline e2e bytes changed"
    if mode=="edited":
        assert result["e2e"]["sha256"]!=get(REF)["product"]["sha256"]
    assert result["e2e"]==get(DESIGN/"whole-reference.json")["sources"][mode]["elf"]
    reference=K/"binding/native-admission.json"
    if reference.exists():
        assert result["e2e"]==get(reference)["elf"][mode],(arm,label,"unmatched complete ELF")
    put(d/"result.json",result)

if __name__=="__main__":
    run(*sys.argv[1:])
