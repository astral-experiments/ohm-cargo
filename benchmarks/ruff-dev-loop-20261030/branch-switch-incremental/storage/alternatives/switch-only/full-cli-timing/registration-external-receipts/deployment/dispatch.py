#!/usr/bin/env python3
"""Run the published experiment with its closed receipt streams held on a third filesystem."""
import datetime
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from site_gate import NEW,ORIGINAL,HOME_DEVICE,SCRATCH,NATIVE,PLAN,ORIG_HOST,CROSS,read,caps,mem,release
from derive_carrier import materialize
from handoff import receive,ack
from receiver import (MIB,GIB,check,check_receiver,free,digest,reserve_file,release_emergency,
                      publish,reopen,sources,storage_guards,canonical)
from select_route import exclusive_record,read_process

S=NEW/"spool"
STORE=NEW/"receiver/store"
IMAGE=NEW/"receiver.ext4"
EMERGENCY=STORE/"retained-failure-reserve"
LIMIT=180*MIB
SPOOL_RESERVE=8*MIB
PATCH_BUDGET=S/".failure-index-reserve"
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def put(p,data):exclusive_record(p,data)
def identity(p):s=p.stat();return [s.st_dev,s.st_ino]
def device(r):d=r.stat().st_dev;return f"{os.major(d)}:{os.minor(d)}"
def check_old(choice):
    p=read_process(choice["old_pid"])
    check(p["state"] in ("T","t") and p["argv"]==choice["old_process"]["argv"] and
          p["start_tick"]==choice["old_process"]["start_tick"] and not p["children"] and
          not (ORIGINAL/"clock-release.json").exists() and not list((ORIGINAL/"runs").iterdir()),
          "original physical waiter lost its exclusive hold")
def footprint():
    # Two previously checked covered empty directories and enough room for a
    # lock, terminal or first-stop receipt while the collector's mount is live.
    total=80*1024;dev=NEW.stat().st_dev
    for base,dirs,files in os.walk(NEW):
        base=Path(base);total+=base.lstat().st_blocks*512
        dirs[:]=[x for x in dirs if (base/x).lstat().st_dev==dev]
        for name in files:
            st=(base/name).lstat();check(st.st_dev==dev,"unexpected receiver staging filesystem")
            total+=st.st_blocks*512
    return total
def physical(entry):
    a,ok=storage_guards(HOME_DEVICE,SCRATCH,mem(),entry=entry)
    return [a["scratch"],a["home"],a["memory"]],bool(ok and (not entry or footprint()<384*MIB))

def orig_input_stamps(conf):
    i=Path(conf["source_inputs"]);sdk=Path(conf["sdkproduct"]).parent
    ns=[Path(conf["sdkproduct"]),Path(conf["sdkcompletion"]),sdk/"output/bin/rustc",i/"ruff.pack",i/"sources.json",i/"historical-index.json",
        Path(conf["consumer"]),*(Path(conf["proxies"])/n for n in ("rustup","cargo","rustc"))]
    dll,=list((sdk/"output/lib").glob("librustc_driver-*.so"));ns.append(dll)
    out={}
    for f in ns:
        st=f.stat();out[str(f)]=[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns,digest(f)]
    return out
def init_scope(scope,conf,choice):
    scope.mkdir(mode=0o700)
    for n in ("runs","logs","custody","donor","private","admission"): (scope/n).mkdir(mode=0o700)
    shutil.copytree(ORIGINAL/"public",scope/"public")
    materialize(ORIGINAL/"private",scope/"private",NEW/"site")
    for n in ("current-elf.json","native-reference.json"):
        orig=ORIGINAL/"untimed-current-elf-v1"/n;check(digest(orig)==CROSS[n],"lost full current native proof");shutil.copyfile(orig,scope/n)
    put(scope/"route.json",dict(name="external-home-ext4-384",original_public=PLAN,original_private=ORIG_HOST,
        external_public=choice["alternative_public"],selection=digest(NEW/"selection.json"),scope=scope.name,
        original_observations_committed=0,frontend_receipt_budget=0,measured_writable_real_home=0,measured_writable_real_scratch=0))
    put(scope/"outside-inputs.json",dict(namespace=os.readlink("/proc/self/ns/mnt"),home=identity(HOME_DEVICE),scratch=identity(SCRATCH),
       study=identity(scope),canonical=identity(Path(conf["canonical"])),inputs=orig_input_stamps(conf),
       receiver_device=device(STORE),receiver_st_dev=STORE.stat().st_dev))
    with (scope/"admission/timer.json").open("xb") as out,(scope/"admission/timer.stderr").open("xb") as err:
        subprocess.run([sys.executable,"-IB",scope/"public/test_timer.py","/run/user/1000",str(scope)],stdout=out,stderr=err,check=True)
    timer=read(scope/"admission/timer.json")
    check(len(timer["six_independent_timer_probes"])==6 and timer["contributes_scored_samples"]==0,"raw timer admission")

def stop_worker(log,carrier):
    mark=log/"stop-before-native"
    if not mark.exists():put(mark,dict(reason="physical capacity or timeout",utc=now()))
    if not (log/"active-worker-pid").is_file():return
    try:
        pid=int((log/"active-worker-pid").read_text())
        p=read_process(pid)
        if p["state"]=="Z":return
        check(os.getpgid(pid)==pid and str(ORIGINAL/"private/safe-worker.py") in p["argv"],"unconfirmed active worker")
        parent=pid
        while parent>1 and parent!=carrier.pid:
            lines=Path(f"/proc/{parent}/status").read_text().splitlines()
            parent=int(next(x.split()[1] for x in lines if x.startswith("PPid:")))
        check(parent==carrier.pid,"different native installation")
        fd=os.pidfd_open(pid)
        try:
            check(read_process(pid)["start_tick"]==p["start_tick"],"worker replaced")
            os.killpg(pid,signal.SIGTERM)
        finally:os.close(fd)
    except (FileNotFoundError,ProcessLookupError):pass

def capture(scope,row,log,conn,carrier,minimum,protocol,conf,trip):
    name=row["slot"];tag=scope.name+"-"+name
    msg,bodies,fds=receive(conn,name,["ruff.elf","reader.elf"],owner=1000,carrier_pid=carrier.pid)
    try:
        check(msg["mountns"]!=os.readlink("/proc/self/ns/mnt"),"FDs came from outside installer")
        rc=msg["exit"]
        checked={}
        for n,body in bodies.items():
            check(body.stat().st_dev not in {S.stat().st_dev,HOME_DEVICE.stat().st_dev,SCRATCH.stat().st_dev,STORE.stat().st_dev},
                  "native product was not in the isolated installer")
            checked[n]=[body.stat().st_size,digest(body)]
        phase=read(scope/"native-reference.json")["public"]["native_reference"][row["arm"]]["unchanged-B"]
        gold={n:[phase[k]["bytes"],phase[k]["sha256"]] for n,k in [("ruff.elf","cli"),("reader.elf","reader")]}
        ok=rc==0 and not trip and checked==gold and free(S)>8*MIB
        if not ok and PATCH_BUDGET.stat().st_size:
            release_emergency(PATCH_BUDGET,SPOOL_RESERVE)
        put(log/"actual-post-exit-fds.json",dict(kernel_sender=msg,actual=checked,independent_expected=gold,
            strict_native_verdict=ok,unscored_qualification=scope.name=="qualification"))
        if ok:
            for n,(size,h) in gold.items():
                f=Path(conf["native_custody"])/"elf"/h
                check(f.stat().st_size==size and digest(f)==h,"missing durably retained correct native reference")
            closed=scope/"runs"/name/"completed.json"
            check(read(closed)["slot"]==name and read(log/"real-mounts-after.json")["external_receiver_inaccessible"],"native custody")
            put(log/"closed.json",dict(exit=0,utc=now(),minima=minimum,maximum_scratch_receipt_bytes=0,
                external_durable_allocated=footprint(),completed=digest(closed),route_sha256=digest(scope/"route.json")))
        else:
            if EMERGENCY.stat().st_size:release_emergency(EMERGENCY,LIMIT)
            put(log/"first-failure.json",dict(exit=rc,physical_capacity_trip=trip,current_bodies=checked,empty_references=gold,utc=now()))
        prefixes=["logs/"+name]
        if (scope/"runs"/name).is_dir():prefixes.append("runs/"+name)
        extra={} if ok else {"failure-artifacts/"+n:b for n,b in bodies.items()}
        record=publish(STORE,tag,protocol,sources(scope,prefixes,extra),
             emergency=(EMERGENCY,LIMIT) if ok else None)
        check(reopen(STORE/record["path"],packed_sha=record["sha256"])["tag"]==tag,"full physical reopened publication")
        put(scope/"custody"/(name+".json"),dict(**record,ok=ok,tag=tag))
        ack(conn,name,record["sha256"])
        return ok
    finally:
        for fd in fds:os.close(fd)

def slot(scope,row,conf,choice,protocol):
    name=row["slot"];log=scope/"logs"/name;log.mkdir()
    while not physical(True)[1]:time.sleep(20)
    cap,ok=physical(True);check(ok,"front physical floor");check_old(choice)
    check_receiver(STORE,S,HOME_DEVICE,SCRATCH,IMAGE)
    check(EMERGENCY.stat().st_size==LIMIT and EMERGENCY.stat().st_blocks*512>=LIMIT,"reserved failure custody")
    check(PATCH_BUDGET.stat().st_size==SPOOL_RESERVE and PATCH_BUDGET.stat().st_blocks*512>=SPOOL_RESERVE and
          free(S)>16*MIB,"insufficient raw spool headroom before a new slot")
    put(log/"entered.json",dict(slot=row,capacity=cap,utc=now(),route=digest(scope/"route.json"),actual_budget=footprint()))
    minimum=cap[:];trip=False;start=time.monotonic()
    saved=os.open(".",os.O_DIRECTORY|os.O_RDONLY)
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as server:
        try:
            os.chdir(scope);server.bind("escrow.sock");server.listen(1)
        finally:os.fchdir(saved);os.close(saved)
        try:
            with (log/"stdout").open("xb") as o,(log/"stderr").open("xb") as e:
                proc=subprocess.Popen(["sudo","-n","taskset","-c","0-3","unshare","-m","--propagation","private","/bin/bash",
                    str(scope/"private/carrier.sh"),name,scope.name,os.readlink("/proc/self/ns/mnt")],
                    stdin=subprocess.DEVNULL,stdout=o,stderr=e,start_new_session=True)
                size_check=start
                while True:
                    if select.select([server],[],[],1)[0]:
                        with server.accept()[0] as conn:
                            accepted=capture(scope,row,log,conn,proc,minimum,protocol,conf,trip)
                        break
                    c,good=physical(False);minimum=list(map(min,zip(minimum,c)))
                    if time.monotonic()>=size_check:
                        good=good and footprint()<384*MIB
                        size_check=time.monotonic()+10
                    if not good or free(S)<=8*MIB or time.monotonic()-start>2.5*3600:
                        trip=True;stop_worker(log,proc)
                    if proc.poll() is not None:
                        put(log/"pre-native-failure.json",dict(status=proc.returncode,utc=now()))
                        publish(STORE,scope.name+"-"+name+"-early",protocol,sources(scope,["logs/"+name]))
                        raise RuntimeError("installer ended before the mandatory FD handshake")
                terminal=proc.wait(timeout=90)
                record=read(scope/"custody"/(name+".json"))
                history=reopen(STORE/record["path"],packed_sha=record["sha256"])["files"]
                ordinary={k:v for k,v in history.items() if not k.startswith("failure-artifacts/")}
                prefixes=["logs/"+name]+(["runs/"+name] if (scope/"runs"/name).is_dir() else [])
                latest=sources(scope,prefixes)
                if {k:[p.stat().st_size,digest(p)] for k,p in latest.items()}!=ordinary:
                    publish(STORE,scope.name+"-"+name+"-late-output",protocol,latest)
                    raise ValueError("producer changed a raw stream after durable acknowledgement")
                check(accepted and terminal==0,"first actual failed installation; no replacement or following slot")
        finally:
            sock=scope/"escrow.sock"
            if sock.exists():sock.unlink()

def group(scope,stage,conf,protocol):
    subprocess.run([sys.executable,"-IB",scope/"public/collect.py",scope,"--stage",stage],check=True)
    observed=read(scope/stage/"verified.json")
    check(observed["analysis_sha256"]==digest(scope/stage/"result.json"),"unbound estimator")
    for f in (scope/"custody").glob("*.json"):
        rec=read(f);check(rec["ok"] and rec["sha256"]==read(STORE/(rec["tag"]+".commit.json"))["sha256"],
                          "analytic observations lack an independent durable slot")
        reopen(STORE/rec["path"],packed_sha=rec["sha256"])
    return observed["go"]

def main():
    check(os.getuid()==1000 and os.sched_getaffinity(0)=={0,1,2,3},"wrong receiver principal/CPU set")
    a,conf=release();choice=read(NEW/"selection.json");check_old(choice)
    check(choice["route"]=="external-home" and choice["authorization"]==digest(NEW/"authorize-selection.json"),
          "unselected alternative")
    grant=read(NEW/"authorize-capture.json")
    check(grant["selection"]==digest(NEW/"selection.json") and grant["whole_native_qualification"] is True
          and grant["pilot_if_native_go"] is True and grant["published"]==a["alternative_public_commit"],
          "no separate native and pilot release")
    check_receiver(STORE,S,HOME_DEVICE,SCRATCH,IMAGE)
    protocol=a["alternative_public_manifest"];check(physical(True)[1],"actual physical capacity")
    reserve_file(EMERGENCY,LIMIT)
    reserve_file(PATCH_BUDGET,SPOOL_RESERVE)
    for scope_name in ("qualification","scored"):
        scope=S/scope_name;init_scope(scope,conf,choice)
        plan=read(scope/"public/plan.json")
        if scope_name=="qualification":
            # Compare complete independent cold/return bodies on both options
            # with no estimator or interaction with route selection.
            for row in plan["schedule"][:2]:slot(scope,row,conf,choice,protocol)
            check({r["arm"] for r in plan["schedule"][:2]}=={"on","off"},"unbalanced preliminary native gate")
            put(scope/"admission/native.json",dict(scored_pairs=0,qualification_slots=[r["slot"] for r in plan["schedule"][:2]],
                 verified=[digest(scope/"custody"/(r["slot"]+".json")) for r in plan["schedule"][:2]],source=NATIVE))
            publish(STORE,"actual-native-admission",protocol,sources(scope,["admission","custody"]))
            continue
        for stage in ("pilot","confirmation"):
            for row in plan["schedule"]:
                if row["stage"]==stage:slot(scope,row,conf,choice,protocol)
            passed=group(scope,stage,conf,protocol)
            report=publish(STORE,"scored-"+stage,protocol,sources(scope,[stage,"custody","admission"],
                {"registration/route.json":scope/"route.json","registration/physical-front.json":scope/"outside-inputs.json",
                 "registration/native-reference.json":scope/"native-reference.json","registration/current-elf.json":scope/"current-elf.json",
                 "registration/public-plan.json":scope/"public/plan.json","registration/original-SHA256SUMS":scope/"public/SHA256SUMS"}))
            if not passed or stage=="confirmation":
                put(NEW/"terminal.json",dict(stage=stage,go=passed,exit=0,score=report,protocol=protocol,
                    source=choice["source"],selection=digest(NEW/"selection.json"),first_attempt_only=True))
                return

if __name__=="__main__":
    try:main()
    except BaseException:
        # On failure the outer namespace is kept alive, even if the receiving FS
        # is full. A producer may also hold current native FDs inside its own mount.
        report=traceback.format_exc()[-6000:]
        for file in [S/"first-stop.json",NEW/"first-stop.json"]:
            try:put(file,dict(utc=now(),error=report,pid=os.getpid(),native_or_receipt_failure=True))
            except OSError:pass
        while True:time.sleep(3600)
