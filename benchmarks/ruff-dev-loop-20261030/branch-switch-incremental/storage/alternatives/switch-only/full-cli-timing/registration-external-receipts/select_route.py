#!/usr/bin/env python3
"""Choose before observation. Identify and hold only the verified original waiter."""
import json
import os
from pathlib import Path
import signal
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from receiver import GIB, MIB, check, sync_dir

def choose(scratch, home, memory, *, predecessors, ordinary_slots, original_release_exists):
    check(ordinary_slots==0 and not original_release_exists,
          "a route cannot be chosen after any ordinary observation or release")
    if not predecessors or memory<=75*GIB or home<=140*GIB or scratch<=140*GIB:
        return "wait"
    if scratch>140*GIB+384*MIB:
        return "original"
    if scratch>140*GIB+8*MIB and home>140*GIB+384*MIB:
        return "external-home"
    return "wait"

def read_process(pid):
    proc=Path("/proc")/str(pid)
    data=(proc/"stat").read_text()
    fields=data[data.rfind(")")+2:].split()
    children=sorted({int(x) for t in (proc/"task").iterdir()
                     for x in (t/"children").read_text().split()})
    return dict(start_tick=fields[19],state=fields[0],argv=[os.fsdecode(x) for x in
                (proc/"cmdline").read_bytes().split(b"\0")[:-1]],children=children)

def hold_waiter(expected, original, delegate, *, deadline=3, durable_choice=None):
    """Retain its exact kernel pidfd through stop and the durable choice marker."""
    pid=int(expected["pid"]);fd=os.pidfd_open(pid)
    stopped=False;committed=False
    def recheck():
        p=read_process(pid)
        check(p["argv"]==expected["argv"] and p["start_tick"]==str(expected["start_tick"]) and
              not p["children"], "waiter identity or children changed")
        check(not (original/"clock-release.json").exists() and not (original/"route.json").exists()
              and not any((original/"runs").iterdir()), "original has already admitted an observation")
        return p
    try:
        p=recheck();check(p["state"] not in ("T","t","Z"),"waiter was not independently running")
        signal.pidfd_send_signal(fd,signal.SIGSTOP);stopped=True;end=time.monotonic()+deadline
        while time.monotonic()<end and read_process(pid)["state"] not in ("T","t"):
            time.sleep(0.01)
        p=recheck();check(p["state"] in ("T","t"),"waiter did not stop")
        result=delegate(p)
        committed=True
        return result
    finally:
        if stopped and not committed and (durable_choice is None or not durable_choice.exists()):
            signal.pidfd_send_signal(fd,signal.SIGCONT)
        os.close(fd)

def exclusive_record(path, value):
    import tempfile
    fd,name=tempfile.mkstemp(prefix="."+path.name+"-pending-",dir=path.parent)
    with os.fdopen(fd,"w") as f:
        json.dump(value,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
    pending=Path(name)
    try:
        os.link(pending,path,follow_symlinks=False);sync_dir(path.parent)
    finally:
        pending.unlink();sync_dir(path.parent)
