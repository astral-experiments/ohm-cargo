"""Coordinator grants for one source-guarded segment of the registered complete-command experiment."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

lab = Path(__file__).resolve().parent
work = lab.parent
study = work/"round18-compiler/depinfo-complete-command-v3"
bench = Path((work/"bench-home.path").read_text().strip())
observed = study/"observed"
reg = study/"registered.json"
old_roles = work/"round18-cargo/edited-role-next/cells"
wild = work/"round18-eh-release/stack-pr46/physical"
segments=("drivers","count-initial","count-replica","native-initial","native-replica")
cargo_cells=("replica-build","initial-test","replica-test")
wild_phases=("build-focus","initial-base","replica-base")
corrected=("initial-base","replica-base")
RECOVERY="8d33ecbb8c695859e848f30d20ee70ef8d3812796bfcfeaea0d743bd0e204158"
REJECTED="4cefbeb3cfac7e3a246ddb8b3937fae95a2c1c585f155fbb4b96d006d6fd1b68"
RETIRED="66f4d362d530d3843874d2e73c9737b7577bcbf0a73b9ecc48f2dc46f98c36ba"
PARK="parked-after-inconclusive-initial.json"
ORIGINAL_REG="a833e97451fb2e702ab1b345d6271854c2cb80c08bd8777aebf2024b049606e1"
REG="5fa7f3456fe8a3c5f002602c4bd71dc0a059ec1f2651ee4913e36c1e4ac53e1c"
SCHEDULE="87a652621d50050459b7ec05bb05faa392323635a5bf2caa3f7ea0047857fbfb"
FLOOR=120*2**30
receipts=lab/"depinfo-v3-segment-receipts"

def require(ok,reason):
    if not ok:
        raise ValueError(reason)

def regular(p):
    return p.is_file() and not p.is_symlink() and p.absolute()==p.resolve()

def checkfile(p,h):
    require(regular(p) and isinstance(h,str) and len(h)==64 and sha(p)==h,"receipt missing, replaced or hash mismatch: "+str(p))

def phases(segment):
    if segment=="drivers":
        return [(phase,arm,45 if phase=="build" else 15) for arm in ("pr269","head")
                for phase in ("build","audit","retire-pgo")]+[("functional","all",15)]
    mode,co=segment.split("-")
    return [(prefix+"-"+mode,co,330 if prefix=="sample" and mode=="native" and co=="initial" else
                        130 if prefix=="sample" else 60 if prefix=="prepare" else 45)
            for prefix in ("prepare","admit","sample","retire")]

def physical_paths(phase,key):
    label=phase+"-"+key
    return lab/("depinfo-complete-release-v3-"+label+".json"),study/"grants"/(label+".json"),observed/"physical"/label

def sha(p):
    with p.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def read(p): return json.loads(p.read_bytes())
def new(p, data):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x") as f:
        json.dump(data,f,indent=2,sort_keys=True)
        f.write("\n")
def quiet():
    active = []
    programs = {"cargo","cargo-real","rustc","rustc-real","wild","wild-real","drrun","ld.bfd","ld.lld",
                "ld.gold","rust-lld","ld","lld","collect2","cc1","cc1plus","clang","clang++","gcc",
                "llvm-profdata","callgrind","valgrind","as","sccache","drcachesim","drcachesim_launcher"}
    guardians = ("round18-cargo/edited-role-next/host.py","round18-eh-release/stack-pr46/phase.py",
                 "stack-pr46/phase-v2.py","stack-pr46/command-v2/cell.py","stack-pr46/host-observe-command-v2.py",
                 "depinfo-source-audit/guard-preflight.py","depinfo-complete-command/run.py","depinfo-complete-command-v2/run.py","depinfo-complete-command-v3/run.py",
                 "edited-role-recovery/recover.py","round18-eh-release/command/run.py")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid(): continue
        try:
            if (proc/"stat").read_text().rsplit(")",1)[1].split()[0] in ("Z","X"): continue
            comm=(proc/"comm").read_text().strip()
            exe_path=Path(os.readlink(proc/"exe").removesuffix(" (deleted)"))
            exe=exe_path.name
            argv=[v.decode(errors="surrogateescape") for v in (proc/"cmdline").read_bytes().split(b"\0") if v]
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        subject=exe_path.is_relative_to(study/"bin") or exe_path.is_relative_to(work/"round18-cargo/pgo/bin")
        if subject or comm in programs or exe in programs or (
            exe.startswith("python") and any(v.endswith(guardians) for v in argv)):
            active.append([int(proc.name),comm,exe])
    if active: raise RuntimeError(f"Competing compiler, linker or benchmark processes: {active}")
    for name in ("round18-cargo/edited-roles/control/pause","round18-cargo/edited-role-recovery/control/pause",
                 "round18-eh-release/command/control/pause"):
        p=work/name
        assert p.is_file() and not p.is_symlink()
    assert not (lab/"host-cleared-for-native").exists()
    return active


def peers():
    return [(lab/"depinfo-cli-control-return.json","cli","all")]+[
        (old_roles/c/"validated.json","cargo",c) for c in cargo_cells]+[
        (wild/(phase+"-returned.json"),"wild",phase) for phase in wild_phases]+[
        (wild.parent/"physical-v2"/(key+"-returned.json"),"wild-v2",key) for key in corrected]

def custody(kind,key,v,ad,close=None):
    """Distinguish an accepted outer return from its scientific disposition or nested exit."""
    if kind=="cargo":
        require(ad["cell"]==close["cell"]==key and close["worker"]==ad["worker"] and
                close["worker_exited"] is True and close["source_restored"] is True and
                close["target_vacant"] is True and close["protected_anchors"]==ad["anchors"] and
                close["pauses"]==ad["pauses"] and close["minimum_free_bytes"]>=FLOOR and
                close["issued_grant"]==ad["grant_sha256"],"Cargo closure or source/target custody failed")
        require((close["terminal"]=="complete" and close["worker_returncode"]==0 and close["rows"]==16) or
                (close["terminal"]=="excluded" and close["worker_returncode"]!=0),"invalid Cargo nested exit or terminal")
        require(ad["utc_ns"]<=v["utc_ns"],"Cargo closure predates admission")
        return v["utc_ns"]
    if kind=="wild":
        require(v["phase"]==ad["phase"]==key and ad["study"]=="wild-eh-pr46-stack" and
                v["status"] in ("qualified","inconclusive") and v["error"] is None and
                v["all_children_returned"] is True and v["remaining_on_granted_cpus"]==[] and
                v["minimum_observed_free"]>=FLOOR and not ad["other_workers"] and v["end_ns"]>=ad["started_ns"],
                "Wild phase did not return with accepted custody")
        children=v["children"]
        require(children and all(row["returncode"]==0 and row["pid"]>0 and
                ad["started_ns"]<=row["start_ns"]<=row["end_ns"]<=v["end_ns"] for row in children),
                "Wild outer status or subcommand return mismatch")
        return v["end_ns"]
    require(kind=="cli" and v["study"]=="depinfo-cli-stock-control" and v["physical_returned"] is True and
            v["actual_exit"]==0 and v["started_ns"]<v["returned_ns"] and ad["identical"] is True,
            "wrong stock CLI custody or failed fixture")
    return v["returned_ns"]

def peer_return(p,kind,key):
    v=read(p)
    if kind=="cargo":
        aq=p.with_name("admitted.json");cq=p.with_name("closure.json")
        checkfile(aq,v["admission_sha256"]);checkfile(cq,v["closure_sha256"])
        ad=read(aq);close=read(cq)
        checkfile(old_roles.parent/"grants"/(key+".json"),ad["grant_sha256"])
        return custody(kind,key,v,ad,close)
    if kind=="wild-v2":
        return check_wild_v2(key)["end_ns"]
    if kind=="wild":
        aq=wild/(key+"-started.json")
        checkfile(aq,v["start_receipt_sha256"])
        ad=read(aq)
        require(ad["grant_file"]=="owner-"+key+".json","unrecognized Wild allocation")
        checkfile(wild.parent/ad["grant_file"],ad["grant_sha256"])
        checkfile(wild.parent/"plan.json",ad["plan_sha256"])
        checkfile(wild.parent/"implementation.json",ad["implementation_sha256"])
        stamp=custody(kind,key,v,ad)
        for i,row in enumerate(v["children"]):
            require(row["log"]==key+"-"+str(i)+".log","Wild log outside its declared phase")
            checkfile(wild/row["log"],row["log_sha256"])
        return stamp
    aq=lab/"depinfo-source-audit/baseline-cli-preflight/verified.json"
    checkfile(aq,v["verified_sha256"]);checkfile(lab/"depinfo-source-audit/guard-cli.py",v["registered_guard_sha256"])
    checkfile(old_roles/"replica-build/closure.json",v["prev_closure"])
    return custody(kind,key,v,read(aq))

def triple(source):
    x={k:source[k] for k in ("session","chunk","exit")}
    require(type(x["session"]) is int and x["session"]>0 and re.fullmatch(r"[0-9a-f]{6}",x["chunk"]) and
            type(x["exit"]) is int,"bad outer tool return information")
    return x

def guest_custody(directory,key,v,ad,expected_exit):
    paths={n:directory/(key+"-"+n+".json") for n in ("returned","host-returned","tool-return","slots-premark","slots-returned")}
    require(all(regular(p) for p in paths.values()),"missing real Wild tool, guest or slot closure")
    host=read(paths["host-returned"]);tool=read(paths["tool-return"])
    sup=triple(tool["supervisor"]);obs=triple(tool["host_observer"])
    require(tool["phase"]==key and sup["exit"]==expected_exit and obs["exit"]==0 and
            sup["session"]!=obs["session"] and host["guest_boot_id"]==ad["host_boot_id"] and
            host["true_supervisor_absent"] is True and host["workers_on_granted_cpus"]==[] and
            host["observed_ns"]>=v["end_ns"],"guest custody or actual tool exit failed")
    checkfile(paths["returned"],tool["physical_return_sha256"])
    checkfile(paths["host-returned"],tool["guest_return_sha256"])
    require(host["log"]==key+"-host-observer.jsonl","wrong guest observer log path")
    logs=directory/host["log"]
    require(regular(logs),"missing Wild guest observer log")
    with logs.open() as f:
        observed=False;last=None
        for line in f:
            last=json.loads(line)
            require(last["guest_boot_id"]==host["guest_boot_id"],"guest boot drift")
            observed|=tool["supervisor"]["guest_pid"] in last["supervisor_pids"]
    require(observed and last and not last["supervisor_pids"] and not last["workers"] and last["ns"]<=host["observed_ns"],
            "outer tool PID was not observed in the guest, or owned work remains")
    before=read(paths["slots-premark"]);after=read(paths["slots-returned"])
    require(before["allocation_sha256"]==ad["grant_sha256"] and before["slot_identity"]==after["slot_identity"] and
            before["source_sha256"]==after["uv_source_sha256"] and before["source_mtime_ns"]==after["before_source_mtime_ns"]==after["after_source_mtime_ns"] and
            after["visible_target_absent"] is True,"Wild slot, source or borrowed target failed return")
    return sup

def wild_recovery_base():
    base=wild.parent
    corrected_plan=base/"recovery/registration.json"
    checkfile(corrected_plan,RECOVERY)
    rr=read(corrected_plan)
    checkfile(base/"plan.json",rr["original_plan_sha256"]);checkfile(base/"implementation.json",rr["original_implementation_sha256"])
    require(rr["original_plan_sha256"]=="a1428428f46dd140c7a93d71ebe4207cfb5a9e013e6fd576ac852342a35d48ed" and
            rr["original_implementation_sha256"]=="c5a10df57657cf2acfbd541b987c0155e62b2753e2547ed525afcc9646d8c1cb" and
            rr["unchanged_failed_return_sha256"]==REJECTED and rr["unchanged_macro_cohorts"]==read(base/"plan.json")["macro_cohorts"] and
            rr["stock_path_bindings"]==read(base/"command/plan.json")["stock_path_bindings"],"Wild recovery escaped its original plan")
    for n,h in rr["new_files"].items():
        p=base/n
        require(p.resolve().is_relative_to(base),"a registered Wild reader file escaped its owner")
        checkfile(p,h)
    checkfile(wild/"build-focus-returned.json","6d8e43377823daccc3e6d8eb6abb763999de5ff4e5851731047f19fe67ca4190")
    require(read(wild/"build-focus-returned.json")["status"]=="qualified","original Wild focus did not qualify")
    checkfile(wild/"initial-base-returned.json",REJECTED)
    v=read(wild/"initial-base-returned.json")
    aq=wild/"initial-base-started.json";checkfile(aq,v["start_receipt_sha256"]);ad=read(aq)
    require(v["status"]=="rejected" and v["error"] and v["all_children_returned"] is True and not v["remaining_on_granted_cpus"] and
            [c["returncode"] for c in v["children"]]==[1] and v["minimum_observed_free"]>=FLOOR,"original rejected return was relabeled")
    bad=guest_custody(wild,"initial-base",v,ad,1)
    require(bad=={"session":80753,"chunk":"232fc9","exit":1},"original supervisor exit or session changed")
    checkfile(base/"recovery/diagnosis.json",rr["rejection_diagnosis_sha256"])
    audit=lab/"wild-46-rejected-initial-audit.json"
    checkfile(audit,"443e5e674a0732bd03b6f1c28748266bf31fd8fd7bf82c6ffd37c48197af47cd")
    audited=read(audit)
    require(audited["canonical_equal"]==74 and audited["test_executables"]==72 and audited["sampled"]==0 and audited["tampered_control_failed"],
            "missing zero-row re-audit or rejected tamper control")
    rt=base/"recovery/banks-retired.json"
    checkfile(rt,RETIRED);ret=read(rt)
    inventory=base/"recovery/bank-retirement.json";checkfile(inventory,ret["retirement_sha256"])
    checkfile(base/"owner-retire-rejected-banks.json",ret["grant_sha256"])
    require(ret["deleted_exactly"]==read(inventory)["allowed_paths"] and len(ret["deleted_exactly"])==2 and
            ret["original_seeds_unchanged"] is True and ret["both_retained_elf_sha256_verified"] is True,
            "original Wild bank retirement or evidence preservation incomplete")
    return {"registration":RECOVERY,"preserved_rejected_exit":bad,"rejected_sha256":REJECTED,"bank_retirement":RETIRED,"reader_audit":sha(audit)}

def score_wild(key):
    require(__debug__,"read-only verification must run with all original assertions enabled")
    import contextlib,importlib.util,io
    base=wild.parent;cmd=base/"command-v2";cfg=read(base/"plan.json")["macro_cohorts"][key]
    root=cmd/"results"/cfg["cohort"]/cfg["control"]
    summary=root/"summary.json";complete=root/"complete.json";restored=root/"restore.json"
    require(all(regular(x) for x in (summary,complete,restored,root/"samples.csv",root/"release-product-parity.json")),
            "need prior existing summary, full eight pairs, stock product parity and return before read-only verification")
    closed=read(complete);restore=read(restored);parity=read(root/"release-product-parity.json")
    require(closed["pairs"]==8 and closed["arms"]==16 and closed["admission_cells"]==4 and
            restore["home_restored"] is True and restore["target_vacant"] is True and
            parity["actual_commands"]==20 and parity["canonical_file_equal"]==1480,
            "incomplete corrected Wild workload or product coverage")
    # The frozen verifier validates the raw row order, original edit IDs, role counts and every
    # selected process total, before recomputing every statistic. With an existing summary it
    # compares and never writes. No Cargo, linker, fixture or instrumented workload is invoked.
    modfile=cmd/"verify.py"
    checkfile(modfile,"d63382a11cc078539a67bfea76be4a96590dfb103634024c9345cb3889af3642")
    spec=importlib.util.spec_from_file_location("depinfo_private_wild_rescore",modfile)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    args=sys.argv
    try:
        sys.argv=[str(modfile),key]
        with contextlib.redirect_stdout(io.StringIO()):mod.main()
    finally:sys.argv=args
    result=read(summary)
    require(type(result["qualified"]) is bool and len(result["signed_improvements_pct"])==8,
            "no eight-pair scientific disposition")
    return {"qualified":result["qualified"],"summary_sha256":sha(summary),"samples_sha256":sha(root/"samples.csv"),
            "complete_sha256":sha(complete),"restored_sha256":sha(restored),"parity_sha256":sha(root/"release-product-parity.json")}

def check_wild_v2(key):
    require(key in corrected,"unknown Wild correction")
    base=wild.parent;d=base/"physical-v2";evidence=wild_recovery_base()
    p=d/(key+"-returned.json");require(regular(p),"corrected Wild terminal is absent")
    v=read(p);aq=d/(key+"-started.json");checkfile(aq,v["start_receipt_sha256"]);ad=read(aq)
    gp=base/("owner-"+key+"-v2.json")
    require(ad["grant_file"]==gp.name,"wrong corrected Wild grant name")
    checkfile(gp,ad["grant_sha256"]);g=read(gp)
    require(g["owner"]=="/root" and g["study"]=="wild-eh-pr46-stack" and g["phase"]==key and
            g["plan_sha256"]==ad["plan_sha256"]==read(base/"recovery/registration.json")["original_plan_sha256"] and
            g["implementation_sha256"]==ad["implementation_sha256"]==read(base/"recovery/registration.json")["original_implementation_sha256"] and
            g["recovery_sha256"]==RECOVERY and g["rejected_attempt_root_replay"]==evidence["reader_audit"] and
            g["bank_retirement_sha256"]==RETIRED and g["retirement_supervisor"]=={"session":41297,"chunk":"914624","exit":0} and
            g["host_boot_id"]==ad["host_boot_id"] and g["cpus"]==ad["cpus"]==list(range(16,24)) and
            g["utc_ns"]<=ad["started_ns"] and ad["native_lease"]=="shared","wrong corrected Wild grant or reservation")
    if key=="initial-base":
        prev=wild/"initial-base-returned.json";ts=evidence["preserved_rejected_exit"]
    else:
        prior=check_wild_v2("initial-base")
        require(prior["qualified"] is True,"replica was not selected by the corrected Wild initial results")
        prev=d/"initial-base-returned.json";ts=prior["supervisor"]
    require(g["previous_return"]==str(prev) and g["previous_sha256"]==sha(prev) and g["previous_supervisor"]==ts,
            "corrected Wild predecessor/grant chain is not the one that actually returned")
    stamp=custody("wild",key,v,ad)
    for i,row in enumerate(v["children"]):
        require(row["log"]==key+"-"+str(i)+".log","wrong Wild subcommand log")
        checkfile(d/row["log"],row["log_sha256"])
    sup=guest_custody(d,key,v,ad,0)
    scored=score_wild(key)
    require((v["status"]=="qualified")==scored["qualified"],"independent eight-pair Wild disposition mismatch")
    return {"phase":key,"end_ns":stamp,"supervisor":sup,**scored,"physical_return_sha256":sha(p),
            "guest_return_sha256":sha(d/(key+"-host-returned.json")),"tool_return_sha256":sha(d/(key+"-tool-return.json")),
            "grant_sha256":sha(gp)}

def replica_allocated():
    base=wild.parent;d=base/"physical-v2"
    return any(p.exists() or p.is_symlink() for p in (base/"owner-replica-base-v2.json",base/"command-v2/results/replica/base",
               d/"replica-base-started.json",d/"replica-base-returned.json",d/"replica-base-slots-premark.json",d/"replica-base-tool-return.json"))

def choose_wild_terminal(initial,replica,park,started):
    if initial["qualified"]:
        require(park is None and replica is not None,"positive initial requires a real corrected replica, with no futility disposition")
        return {"status":"both-corrected-cohorts-returned","initial":initial,"replica":replica}
    require(not started and replica is None and park is not None,"inconclusive initial awaits explicit root parking; a started replica cannot be skipped")
    expected=make_park(initial)
    require(park==expected,"explicit root futility parking did not bind this actual eight-pair terminal")
    return {"status":"initial-inconclusive-replica-parked","initial":initial,"park":park}

def make_park(initial):
    require(initial["qualified"] is False,"cannot park a selected replica")
    return {"owner":"/root","study":"wild-eh-pr46-stack","disposition":"park-unselected-replica-after-inconclusive-initial",
            "registered_order":"initial-base must qualify to start replica-base","registration_sha256":RECOVERY,
            "failed_original_initial_sha256":REJECTED,"verified_bank_retirement_sha256":RETIRED,"replica_started":False,
            "initial":initial}

def park_form():
    initial=check_wild_v2("initial-base")
    require(not replica_allocated(),"replica has been allocated")
    return make_park(initial)

def wild_gate():
    initial=check_wild_v2("initial-base")
    pp=wild.parent/"recovery"/PARK
    if pp.exists() or pp.is_symlink():require(regular(pp),"invalid futility parking evidence path")
    park=read(pp) if regular(pp) else None
    started=replica_allocated()
    replica=check_wild_v2("replica-base") if initial["qualified"] and started else None
    return choose_wild_terminal(initial,replica,park,started)

def physical_return(phase,key,digest,supervisor_pid,prev,prev_hash):
    release,grant,d=physical_paths(phase,key)
    out=d/"returned.json"
    checkfile(out,digest)
    v=read(out);owner=read(d/"owner.json");launch=read(d/"launched.json");g=read(grant)
    checkfile(grant,v["grant_sha256"]);checkfile(release,g["release_sha256"])
    checkfile(d/"process.log",v["process_sha256"])
    r=read(release)
    require(g["phase"]==r["phase"]==phase and g["key"]==r["key"]==key and
            g["registration_sha256"]==REG and g["release"]==str(release) and
            r["previous_return"]==str(prev) and r["previous_return_sha256"]==prev_hash and
            owner["grant_sha256"]==v["grant_sha256"] and owner["coordinator_release"]==g["release_sha256"] and
            owner["host"]==g["host_boot_id"]==r["boot_id"] and
            owner["parent_pid"]==launch["parent"]==supervisor_pid and launch["worker"]==launch["pid_session"] and
            launch["worker"]>0 and owner["started_ns"]<=v["timestamp_ns"] and
            v["worker_exit"]==0 and v["final_owned"]=={} and not (d/"fault.json").exists() and
            min(v["minimum_free"],v["after_free"])>=FLOOR,
            "physical worker, grant, predecessor, process or capacity mismatch: "+str(out))
    return out

def segment_return(name):
    d=receipts/name
    p=d/"returned.json"
    require(regular(p),"missing segment return: "+str(p))
    v=read(p);scopes=phases(name)
    require(v["segment"]==name and v["physical_returned"] is True and v["actual_exit"]==0 and
            v["registration_sha256"]==REG and v["schedule_sha256"]==SCHEDULE and
            v["coordinator_sha256"]==sha(Path(__file__)) and len(v["phases"])==len(scopes),"wrong compound return")
    prev=Path(v["previous_return"]);digest=v["previous_return_sha256"]
    checkfile(prev,digest)
    for (phase,key,_),row in zip(scopes,v["phases"],strict=True):
        label=phase+"-"+key
        require(row==read(d/(label+".json")) and row["phase"]==phase and row["key"]==key and
                row["exit"]==0,"missing nested parent wait status: "+label)
        checkfile(d/(label+".log"),row["log_sha256"])
        q=physical_return(phase,key,row["physical_sha256"],row["supervisor_pid"],prev,digest)
        require(row["physical_file"]==str(q) and row["grant_sha256"]==sha(physical_paths(phase,key)[1]),"nested return path/grant mismatch")
        prev,digest=q,row["physical_sha256"]
    require(v["last_return_sha256"]==digest and v["finished_ns"]>=read(prev)["timestamp_ns"],"incomplete compound return")
    return v["finished_ns"]

def known_returns():
    result={}
    for p,kind,key in peers():
        if p.exists():
            require(regular(p),"unsafe external evidence path")
            # The nominated latest return gets full validation. Read only its date for sorting here.
            v=read(p)
            result[p]=v[{"cargo":"utc_ns","wild":"end_ns","wild-v2":"end_ns","cli":"returned_ns"}[kind]]
    for segment in segments:
        p=receipts/segment/"returned.json"
        if p.exists():
            require(regular(p),"unsafe segment evidence path")
            result[p]=read(p)["finished_ns"]
    return result

def verify_handoff(p,digest,latest):
    checkfile(p,digest)
    matches=[(kind,key) for path,kind,key in peers() if path==p]
    if matches:
        stamp=peer_return(p,*matches[0])
    else:
        require(p.parent.parent==receipts and p.parent.name in segments and p.name=="returned.json",
                "unknown custody family; a raw inner return cannot stand in for a root-supervised segment")
        stamp=segment_return(p.parent.name)
    if latest:
        candidates=known_returns()
        require(p in candidates and stamp==max(candidates.values()),"supplied tool return is older than an already completed host family")
    return stamp

def supervisor_receipt(session,chunk,exit_code):
    require(isinstance(session,int) and session>0 and isinstance(chunk,str) and
            re.fullmatch(r"[0-9a-f]{6}",chunk) and type(exit_code) is int and exit_code==0,
            "pass the actual successful root exec session and final six-hex completion chunk")
    return {"session":session,"chunk":chunk,"exit":exit_code,"source":"root-observed final exec/write_stdin result"}

def foreign_grants():
    for phase in wild_phases:
        end=wild/(phase+"-returned.json")
        require(not any(p.exists() for p in (wild.parent/("owner-"+phase+".json"),wild/(phase+"-started.json"))) or
                regular(end),"Wild allocation is outstanding: "+phase)
    for key in corrected:
        here=wild.parent/"physical-v2"
        started=any(p.exists() for p in (wild.parent/("owner-"+key+"-v2.json"),here/(key+"-started.json")))
        require(not started or all(regular(here/(key+"-"+suffix+".json")) for suffix in ("returned","host-returned","tool-return")),
                "corrected Wild supervisor/guest/outer tool has not returned: "+key)
    for cell in cargo_cells:
        require(not ((old_roles.parent/"grants"/(cell+".json")).exists() or (old_roles/cell).exists()) or
                regular(old_roles/cell/"validated.json"),"Cargo allocation is outstanding: "+cell)

def expected_progress(segment):
    prior=segments[:segments.index(segment)]
    for name in ("depinfo-complete-command","depinfo-complete-command-v2"):
        old=study.with_name(name)
        require(not any((old/s).exists() or (old/s).is_symlink() for s in ("grants","observed")),
                "superseded studies cannot have any authority or physical work")
    for name in ("depinfo-v2-segment-receipts","depinfo-segment-receipts"):
        require(not (lab/name).exists() and not (lab/name).is_symlink(),"superseded coordinator acquired a segment")
    require(all(p.name.startswith("depinfo-complete-release-v3-") for p in lab.glob("depinfo-complete-release-*.json")),
            "a superseded physical release exists")
    for s in prior:segment_return(s)
    require(all(not (receipts/s).exists() for s in segments[len(prior):]),"current/future segment already allocated")
    done={(p,k) for s in prior for p,k,_ in phases(s)}
    allscopes={(p,k) for s in segments for p,k,_ in phases(s)}
    for phase,key in allscopes:
        present=tuple(p.exists() or p.is_symlink() for p in physical_paths(phase,key))
        require(present==((phase,key) in done,)*3,"pre-granted, missing or outstanding scope: "+phase+" "+key)
    for folder,expected,prefix in ((study/"grants",{p+"-"+k+".json" for p,k in done},"*.json"),
                (observed/"physical",{p+"-"+k for p,k in done},"*"),
                (lab,{"depinfo-complete-release-v3-"+p+"-"+k+".json" for p,k in done},"depinfo-complete-release-v3-*.json")):
        require({x.name for x in folder.glob(prefix)}==expected,"unknown or uncompleted physical scope under "+str(folder))
    return prior

def validate_native(segment):
    if segment.startswith("native-"):
        sys.path.insert(0,str(study))
        from rescore import all_results
        result=all_results("count",verify_logs=True)
        require(result["qualifies"] is True,"all six registered count comparisons must pass before issuing any native release")
        return result
    return None

@contextlib.contextmanager
def exclusive(path,create=False):
    require(not path.is_symlink() and (create or regular(path)),"unsafe physical lock "+str(path))
    with path.open("a" if create else "r") as fd:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield

def not_allocated(scope_list):
    for phase,key in scope_list:
        require(all(not (p.exists() or p.is_symlink()) for p in physical_paths(phase,key)),
                "outstanding or premature grant/release: "+phase+" "+key)

def external_snapshot():
    stack=wild.parent
    extra=[stack/"recovery"/PARK,stack/"recovery/banks-retired.json",stack/"recovery/registration.json"]
    for key in corrected:
        extra.extend([stack/("owner-"+key+"-v2.json")]+[stack/"physical-v2"/(key+"-"+name+".json")
                      for name in ("host-returned","tool-return","slots-returned")])
    return {str(p):sha(p) for p in [p for p,_,_ in peers()]+extra if regular(p)}

def form_for(phase,key,minutes):
    result=json.loads(subprocess.check_output([sys.executable,"-I","-B",str(study/"grant_form.py"),phase,key,
                                              "--minutes",str(minutes)],cwd=study))
    release,grant,_=physical_paths(phase,key)
    require(Path(result["release_path"])==release and Path(result["grant_path"])==grant and
            result["grant_template"]["registration_sha256"]==REG and
            result["grant_template"]["study"]==result["release_template"]["study"]==read(reg)["study"],
            "the frozen form does not identify the registered scope")
    return result,release,grant

def dispatch(a):
    require(__debug__ and os.geteuid()!=0 and Path("/proc/1/comm").read_text().strip()=="systemd",
            "run the coordinator on the real non-root host, with Python assertions enabled")
    checkfile(reg,REG);checkfile(study/"schedules.csv",SCHEDULE)
    sys.path.insert(0,str(study))
    from verify_amendment import verify
    verify()
    provenance=supervisor_receipt(a.previous_session,a.previous_chunk,a.previous_exit)
    prev=a.previous.absolute()
    digest=a.previous_sha
    with exclusive(lab/"depinfo-physical-owner.lock",create=True), exclusive(old_roles.parent/"one-cell.lock"):
        with exclusive(bench/"round18/native-lease"):
            verify_handoff(prev,digest,latest=True)
            wild_authority=wild_gate()
            if prev.parent==wild.parent/"physical-v2":
                t=read(prev.with_name(prev.name.replace("-returned.json","-tool-return.json")))["supervisor"]
                require(all(t[k]==provenance[k] for k in ("session","chunk","exit")),"outer supervisor session/chunk differs from the actual Wild tool return")
            prior=expected_progress(a.segment)
            for n in prior:
                previous=read(receipts/n/"returned.json")["previous_supervisor"]
                require((previous["session"],previous["chunk"])!=(a.previous_session,a.previous_chunk),
                        "previous root tool completion has already been consumed")
            foreign_grants();quiet()
            if a.segment!="drivers":
                require(regular(observed/"subjects.json") and read(observed/"subjects.json")["registration_sha256"]==REG,
                        "prospectively frozen real driver/SDK/functional subjects absent")
            gate=validate_native(a.segment)
        others=external_snapshot()
        order=phases(a.segment)
        remaining=[(p,k) for n in segments[segments.index(a.segment):] for p,k,_ in phases(n)]
        logs=receipts/a.segment
        logs.mkdir(parents=True,exist_ok=False)
        history={"segment":a.segment,"previous_supervisor":provenance,"registration_sha256":REG,
                 "schedule_sha256":SCHEDULE,"coordinator_sha256":sha(Path(__file__)),"previous_return":str(prev),
                 "previous_return_sha256":digest,"external_returns":others,"wild_read_only_custody":wild_authority,"started_ns":time.time_ns(),"phases":[]}
        new(logs/"intake.json",history)
        if gate is not None:new(logs/"count-gate-before-grants.json",gate)
        try:
            for phase,key,minutes in order:
                label=phase+"-"+key
                with exclusive(bench/"round18/native-lease"):
                    checkfile(prev,digest)
                    foreign_grants();quiet()
                    require(external_snapshot()==others,"another physical family returned during this compound allocation")
                    not_allocated(remaining)
                    min_gib=180 if phase.startswith("prepare-") else 130 if phase=="build" else 126
                    require(shutil.disk_usage(bench).free>=min_gib*2**30,"insufficient space before release: "+str(min_gib)+" GiB")
                    form,release,grant=form_for(phase,key,minutes)
                    certificate=form["release_template"]
                    certificate.update(exclusive=True,competing_tools=[],previous_return=str(prev),
                        previous_return_sha256=digest,inspection_utc_ns=time.time_ns(),granting_segment=a.segment,
                        root_intake_sha256=sha(logs/"intake.json"))
                    if phase.endswith(("-count","-native")):
                        require(certificate["subjects_sha256"]==sha(observed/"subjects.json"),"unbound driver set")
                    new(release,certificate)
                    g=form["grant_template"]
                    g["release_sha256"]=sha(release)
                    new(grant,g)
                    ghash=sha(grant)
                # The frozen runner independently takes this same exclusive physical lock before it
                # starts a worker. Another root issuer in this handoff gap causes refusal, never overlap.
                mask="24-31" if phase=="build" else "0-15"
                args=["taskset","-c",mask,sys.executable,"-I","-B",str(study/"run.py"),phase,key]
                log=logs/(label+".log")
                print("Starting",label,"grant",ghash,flush=True)
                with log.open("xb") as f:
                    child=subprocess.Popen(args,cwd=study,env={**os.environ,"OHM_DEPINFO_GRANT_SHA256":ghash},
                                           stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                    try:
                        code=child.wait()
                    except BaseException:
                        if child.poll() is None:
                            child.send_signal(signal.SIGINT)
                        child.wait()
                        raise
                returned=physical_paths(phase,key)[2]/"returned.json"
                rec={"phase":phase,"key":key,"exit":code,"supervisor_pid":child.pid,"args":args,
                     "grant_sha256":ghash,"log_sha256":sha(log),"physical_file":str(returned),
                     "physical_sha256":sha(returned) if regular(returned) else None}
                new(logs/(label+".json"),rec)
                history["phases"].append(rec)
                require(code==0,"physical supervisor rejected "+label+" with exit "+str(code))
                physical_return(phase,key,rec["physical_sha256"],child.pid,prev,digest)
                prev,digest=returned,rec["physical_sha256"]
                require(remaining.pop(0)==(phase,key),"phase order changed")
                print("Returned",label,digest,flush=True)
            with exclusive(bench/"round18/native-lease"):
                foreign_grants();quiet();not_allocated(remaining)
                require(others==external_snapshot(),"physical families overlapped or changed custody")
                history.update(physical_returned=True,actual_exit=0,finished_ns=time.time_ns(),last_return_sha256=digest)
                new(logs/"returned.json",history)
                segment_return(a.segment)
            print("Sealed segment",a.segment,sha(logs/"returned.json"),flush=True)
        except BaseException as exc:
            new(logs/"failure.json",{**history,"error":repr(exc),"failure_ns":time.time_ns()})
            raise

def selftest():
    import tempfile
    from unittest.mock import patch
    checks=[]
    def reject(tag,fn):
        try: fn()
        except (ValueError,KeyError,FileNotFoundError): checks.append(tag)
        else: raise AssertionError("negative control passed: "+tag)
    for (label,args) in (("empty chunk",(1,"",0)),("invented shape",(1,"xyzxyz",0)),("unreturned session",(1,"ad4bcd",None)),("nonzero host return",(1,"abcdef",1))):
        reject(label,lambda:supervisor_receipt(*args))
    supervisor_receipt(13,"ab12af",0)
    boot="synthetic"
    ad={"cell":"replica-build","worker":{"pid":12},"anchors":{"source":[9,10]},"pauses":{"x":"y"},"grant_sha256":"g","utc_ns":1}
    close={"cell":ad["cell"],"worker":ad["worker"],"worker_exited":True,"source_restored":True,"target_vacant":True,
           "protected_anchors":ad["anchors"],"pauses":ad["pauses"],"minimum_free_bytes":FLOOR,"issued_grant":"g",
           "terminal":"excluded","worker_returncode":1,"rows":0}
    def cag(c):return custody("cargo","replica-build",{"utc_ns":2},ad,c)
    cag(close);cag({**close,"terminal":"complete","worker_returncode":0,"rows":16})
    reject("unreturned Cargo target",lambda:cag({**close,"target_vacant":False}))
    reject("exclusion mislabeled complete",lambda:cag({**close,"terminal":"complete"}))
    wad={"phase":"build-focus","study":"wild-eh-pr46-stack","started_ns":1,"other_workers":[]}
    wc={"phase":"build-focus","status":"inconclusive","error":None,"all_children_returned":True,
        "remaining_on_granted_cpus":[],"minimum_observed_free":FLOOR,"end_ns":4,
        "children":[{"pid":1,"start_ns":2,"end_ns":3,"returncode":0}]}
    def wic(item):return custody("wild","build-focus",item,wad)
    wic(wc);reject("leftover Wild process",lambda:wic({**wc,"remaining_on_granted_cpus":[2]}))
    reject("failed Wild inner command",lambda:wic({**wc,"children":[{**wc["children"][0],"returncode":1}]}))
    low={"phase":"initial-base","qualified":False,"supervisor":{"session":10,"chunk":"abc123","exit":0},"summary_sha256":"fixture-low"}
    high={**low,"qualified":True,"summary_sha256":"fixture-high"}
    rep={"phase":"replica-base","qualified":False}
    parked=make_park(low)
    require(choose_wild_terminal(low,None,parked,False)["status"].endswith("parked"),"valid independently rescored futility did not release")
    require(choose_wild_terminal(high,rep,None,True)["status"].endswith("returned"),"valid two-cohort physical closure rejected")
    reject("pending corrected replica after positive initial",lambda:choose_wild_terminal(high,None,None,False))
    reject("unparked inconclusive initial",lambda:choose_wild_terminal(low,None,None,False))
    reject("faked positive-initial parking",lambda:make_park(high))
    reject("parking after replica grant",lambda:choose_wild_terminal(low,None,parked,True))
    reject("parking binds wrong score",lambda:choose_wild_terminal(low,None,{**parked,"initial":high},False))
    reject("original Wild rejection cannot satisfy corrected status",lambda:wic({**wc,"status":"rejected"}))
    with tempfile.TemporaryDirectory() as guest:
        d=Path(guest);key="initial-base";aq={"host_boot_id":boot,"grant_sha256":"g"}
        vals={"returned":{"end_ns":5},"host-returned":{"guest_boot_id":boot,"workers_on_granted_cpus":[],"true_supervisor_absent":True,
                   "observed_ns":6,"log":key+"-host-observer.jsonl"},
              "slots-premark":{"slot_identity":{"x":[1,2]},"source_sha256":"s","source_mtime_ns":3,"allocation_sha256":"g"},
              "slots-returned":{"slot_identity":{"x":[1,2]},"uv_source_sha256":"s","before_source_mtime_ns":3,"after_source_mtime_ns":3,"visible_target_absent":True}}
        for name,v in vals.items():new(d/(key+"-"+name+".json"),v)
        tp=d/(key+"-tool-return.json")
        fields={"phase":key,"supervisor":{"guest_pid":99,"session":8,"chunk":"c0ffee","exit":0},"host_observer":{"session":9,"chunk":"123456","exit":0},
                "physical_return_sha256":sha(d/(key+"-returned.json")),"guest_return_sha256":sha(d/(key+"-host-returned.json"))}
        new(tp,fields)
        observer=d/vals["host-returned"]["log"]
        lines=[{"guest_boot_id":boot,"ns":i,"supervisor_pids":([99] if i==1 else []),"workers":[]} for i in (1,5)]
        observer.write_text("".join(json.dumps(x)+chr(10) for x in lines))
        guest_custody(d,key,vals["returned"],aq,0)
        reject("guest success cannot attest failed outer exit",lambda:guest_custody(d,key,vals["returned"],aq,1))
        observer.write_text(json.dumps({**lines[0],"supervisor_pids":[]})+chr(10))
        reject("unobserved guest supervisor pid",lambda:guest_custody(d,key,vals["returned"],aq,0))
        observer.write_text("".join(json.dumps(x)+chr(10) for x in (lines[0],{**lines[1],"workers":[{"pid":11}]})))
        reject("guest log has surviving worker",lambda:guest_custody(d,key,vals["returned"],aq,0))
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);l=root/"lab";s=root/"v2";obs=s/"observed";rcpt=l/"receipts";o=root/"cargo/cells";wi=root/"wild/physical"
        with patch.dict(globals(),dict(lab=l,study=s,observed=obs,receipts=rcpt,old_roles=o,wild=wi)):
            prev=root/"external.json";new(prev,{"fixture":True});digest=sha(prev)
            reject("unrelated positive root file",lambda:verify_handoff(prev,digest,False))
            for predecessor in ("depinfo-complete-command","depinfo-complete-command-v2"):
                previous_authority=s.with_name(predecessor)/"grants"
                previous_authority.mkdir(parents=True)
                reject("earlier protocol authority",lambda:expected_progress("drivers"))
                previous_authority.rmdir()
            obsolete=l/"depinfo-complete-release-v2-build-head.json"
            new(obsolete,{"synthetic":True})
            reject("earlier generation root authority",lambda:expected_progress("drivers"))
            obsolete.unlink()
            prior_segments=l/"depinfo-v2-segment-receipts"
            prior_segments.mkdir()
            reject("a superseded coordinator has acquired the host",lambda:expected_progress("drivers"))
            prior_segments.rmdir()
            _,future,_=physical_paths("prepare-native","initial")
            new(future,{"synthetic":True})
            reject("pregiven later native authority",lambda:expected_progress("drivers"))
            future.unlink()
            for segment in segments:
                expected_progress(segment)
                d=rcpt/segment
                initial=prev;initial_hash=digest
                history=[]
                for phase,key,_ in phases(segment):
                    rel,g,dest=physical_paths(phase,key)
                    label=phase+"-"+key
                    new(rel,{"phase":phase,"key":key,"boot_id":boot,"previous_return":str(prev),"previous_return_sha256":digest})
                    new(g,{"phase":phase,"key":key,"host_boot_id":boot,"registration_sha256":REG,"release":str(rel),"release_sha256":sha(rel)})
                    dest.mkdir(parents=True)
                    (dest/"process.log").write_bytes(b"fixture")
                    new(dest/"owner.json",{"grant_sha256":sha(g),"coordinator_release":sha(rel),"host":boot,"parent_pid":9,"started_ns":1})
                    new(dest/"launched.json",{"parent":9,"worker":19,"pid_session":19})
                    out=dest/"returned.json"
                    new(out,{"worker_exit":0,"final_owned":{},"minimum_free":FLOOR,"after_free":FLOOR,"process_sha256":sha(dest/"process.log"),
                             "grant_sha256":sha(g),"timestamp_ns":2})
                    d.mkdir(parents=True,exist_ok=True)
                    logfile=d/(label+".log");logfile.write_bytes(b"fixture")
                    row={"phase":phase,"key":key,"exit":0,"supervisor_pid":9,"physical_sha256":sha(out),"physical_file":str(out),
                         "grant_sha256":sha(g),"log_sha256":sha(logfile)}
                    new(d/(label+".json"),row);history.append(row)
                    physical_return(phase,key,sha(out),9,prev,digest)
                    prev,digest=out,sha(out)
                terminal=d/"returned.json"
                new(terminal,{"segment":segment,"physical_returned":True,"actual_exit":0,"schedule_sha256":SCHEDULE,"registration_sha256":REG,
                    "coordinator_sha256":sha(Path(__file__)),"previous_return":str(initial),"previous_return_sha256":initial_hash,
                    "phases":history,"finished_ns":3,"last_return_sha256":digest})
                segment_return(segment)
                prev,digest=terminal,sha(terminal)
            reject("duplicate segment / grant",lambda:expected_progress("drivers"))
            old=prev
            reject("wrong terminal digest",lambda:verify_handoff(old,"0"*64,False))
            last=physical_paths("retire-native","replica")[2]/"returned.json"
            last.write_text("{}")
            reject("nested custody changed",lambda:segment_return("native-replica"))
    print(json.dumps({"synthetic":True,"physical_tools_started":0,"accepted":["real Cargo completed/excluded shapes","Wild inconclusive with physical return","original retirement and corrected guest/tool custody shapes","both valid corrected-Wild outcomes","all five sequenced segments / 23 single-use synthetic scopes"],
                      "rejected":checks},indent=2))

def main():
    if sys.argv[1:]==["--wild-park-form"]:
        print(json.dumps(park_form(),indent=2,sort_keys=True))
        return
    if sys.argv[1:]==["--check-wild-recovery-base"]:
        print(json.dumps(wild_recovery_base(),indent=2,sort_keys=True))
        return
    if sys.argv[1:]==["--self-test"]:
        return selftest()
    if len(sys.argv)==4 and sys.argv[1]=="--verify-return":
        p=Path(sys.argv[2]).absolute()
        print("verified physical custody timestamp",verify_handoff(p,sys.argv[3],False))
        return
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("segment",choices=segments)
    ap.add_argument("--previous",type=Path,required=True)
    ap.add_argument("--previous-sha",required=True)
    ap.add_argument("--previous-session",type=int,required=True)
    ap.add_argument("--previous-chunk",required=True)
    ap.add_argument("--previous-exit",type=int,required=True)
    def interrupted(number,_frame):
        raise KeyboardInterrupt("root supervisor received signal "+str(number))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGHUP,interrupted)
    dispatch(ap.parse_args())

if __name__=="__main__":
    main()
