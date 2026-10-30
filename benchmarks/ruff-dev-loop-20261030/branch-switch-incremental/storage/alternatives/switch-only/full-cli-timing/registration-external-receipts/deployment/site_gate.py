#!/usr/bin/env python3
"""One prospective H9 decision. This never supplies the original release token."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"public"))
from receiver import GIB,MIB,check,digest,free
from select_route import choose,exclusive_record,hold_waiter,read_process

_layout=json.loads((HERE/"host-paths.json").read_bytes())
ORIGINAL=Path(_layout["original"])
NEW=Path(_layout["new"])
HOME_DEVICE=Path(_layout["home"])
SCRATCH=Path(_layout["scratch"])
SOURCE="08d49cba6aacb0cac27a96eea335ed1c7439f483"
PLAN="84d1e273f3295c39b912f76fc5758a8ea6f98072afffa742066eb04bc6028381"
ORIG_HOST="6727fa64c0f3c8d2fda18cd7a99a945b6f0bf7c2fa32f3e3cf1bc4b0ab5908b7"
ORIG_PUBLICATION="e91f82ceeeb9bc377dd0efbc66d3f509552d66a2"
NATIVE="64fdf255d68e60e3152048a496b4997c516ec998546d2e4d7402aac055da7477"
OLDWAITER="41450bf024c1f71d0f73283672ec15aa41c49296e933e7ec4bae0f022f0bda67"
CROSS={"terminal.json":"23c340e8f4caf3648b7aed0c351751f4e2d238880f2a98ba26e9e703ed55bf07",
       "current-elf.json":"6d66240923768155bafd4a60c4de0f3518f9dcad2217e76a9269807212b32ce4",
       "native-reference.json":"261996aaea44a4f93969a6e3753da6e5a9b68cfd7187634f29f49989bd71d0e4"}

def read(p):return json.loads(p.read_bytes())
def mem():
    return int(next(s.split()[1] for s in Path("/proc/meminfo").read_text().splitlines() if s.startswith("MemAvailable:")))*1024
def caps():return [free(SCRATCH),free(HOME_DEVICE),mem()]
def manifest(directory,expected):
    check(digest(directory/"SHA256SUMS")==expected,"source manifest SHA mismatch")
    subprocess.run(["sha256sum","--quiet","-c","SHA256SUMS"],cwd=directory,check=True)
def dotted(obj,parts):
    for s in parts:obj=obj[int(s)] if isinstance(obj,list) else obj[s]
    return obj

def release():
    a=read(NEW/"authorize-selection.json")
    c=read(ORIGINAL/"private/config.json")
    check(os.getuid()==1000 and Path("/proc/sys/kernel/random/boot_id").read_text().strip()==c["boot_id"] and
          HOME_DEVICE.stat().st_dev!=SCRATCH.stat().st_dev and NEW.stat().st_dev==HOME_DEVICE.stat().st_dev and
          ORIGINAL.stat().st_dev==SCRATCH.stat().st_dev,"wrong machine, mount or owner")
    check(a["source"]==SOURCE and a["cpus"]==[0,1,2,3] and a["go"] is True and a["host_quiet"] is True and
          a["original_public_commit"]==ORIG_PUBLICATION and len(a["alternative_public_commit"])==40 and
          a["alternative_public_commit"]!=ORIG_PUBLICATION,"missing distinct published authorization")
    manifest(NEW/"public",a["alternative_public_manifest"]);manifest(NEW/"site",a["alternative_site_manifest"])
    for file in sorted((NEW/"public/deployment").iterdir()):
        check(file.is_file() and digest(NEW/"site"/file.name)==digest(file),"deployed external worker differs from the public source")
    check(Path(c["receipts"])==ORIGINAL and Path(c["real_home"])==HOME_DEVICE and Path(c["scratch"])==SCRATCH,
          "physical roots differ from the existing registered study")
    manifest(ORIGINAL/"public",PLAN);manifest(ORIGINAL/"private",ORIG_HOST)
    for n,w in CROSS.items():check(digest(ORIGINAL/"untimed-current-elf-v1"/n)==w,"raw H9 native reconstruction changed")
    nc=Path(c["native_custody"])
    check(digest(nc/"independent-terminal.json")==NATIVE and digest(nc/"verified.json")==read(nc/"independent-terminal.json")["verified"]
          and digest(nc/"collection.json")==read(nc/"independent-terminal.json")["collection"] and read(nc/"verified.json")["same_physical_57"],
          "unqualified native/independent empty/reference kit")
    for path,tag in zip(c["parser"],["check","test-no-run"]):
        d=Path(path);p=a["parser"][tag]
        check(p["root"]==d.name and {k for k in ["completion.json","work-terminal.json","verified.json"] if k in p["files"]}==
              {"completion.json","work-terminal.json","verified.json"},"wrong parser receipt set")
        for n,h in p["files"].items():
            check(Path(n).name==n and digest(d/n)==h,"parser terminal hash")
        check(read(d/"completion.json")["exit"]==read(d/"work-terminal.json")["exit"]==0,"parser runner incomplete")
        for k,v in [("pairs",12),("source",SOURCE),("workflow",p["genuine_workflow"])]:
            name,pointer=p["pointers"][k]
            check(name in p["files"] and dotted(read(d/name),pointer)==v,"parser study source/workflow/count")
        choices={"check":["check","cargo check","check-parser"],"test-no-run":["test-no-run","test --no-run","cargo test --no-run","test-build"]}
        check(p["genuine_workflow"] in choices[tag],"wrong prior selection")
    return a,c

def unobserved():
    check(not list((ORIGINAL/"runs").iterdir()) and not list((ORIGINAL/"logs").iterdir()) and
          not any((ORIGINAL/p).exists() for p in ("clock-release.json","route.json","terminal.json","failure.json")) and
          not (NEW/"receiver.ext4").exists(),"primary data or an original release already present")

def decide():
    check(HERE==NEW/"site" and stat_private(NEW),"unexpected H9 staging directory")
    with (NEW/"selector.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        check(not (NEW/"selection.json").exists(),"fixed route already exists")
        unobserved();a,c=release()
        check(digest(ORIGINAL/"controller.json")==OLDWAITER,"original waiter not frozen")
        expected=read(ORIGINAL/"controller.json")
        pid=int(expected["pid"]);p=read_process(pid)
        # The initial process receipt is authenticated. Bind the actual physical argv
        # and kernel start time again using facts supplied by the two-person release.
        want=a["original_waiter"]
        check(pid==int(want["pid"]) and p["argv"]==want["argv"] and p["start_tick"]==str(want["start_tick"])
              and not p["children"] and p["state"] not in ("Z","T","t") and str(ORIGINAL/"private/controller.py") in p["argv"],
              "original identity or execution state")
        capacity=caps()
        choice=choose(*capacity,predecessors=True,ordinary_slots=0,original_release_exists=False)
        if choice=="wait":
            print(json.dumps({"route":"wait","physical_free":capacity}));return
        def save(observation):
            unobserved()
            measured=caps()
            check(choose(*measured,predecessors=True,ordinary_slots=0,original_release_exists=False)==choice,
                  "preferred route changed during gate, no selection committed")
            record=dict(route=choice,actual_free=measured,source=SOURCE,old_pid=pid,old_process=observation,
                        original_public=PLAN,alternative_public=a["alternative_public_manifest"],
                        native_terminal=NATIVE,authorization=digest(NEW/"authorize-selection.json"),ordinary_samples=0)
            exclusive_record(NEW/"selection.json",record)
        if choice=="original":
            save(p)
        else:
            hold_waiter(want,ORIGINAL,save,durable_choice=NEW/"selection.json")
        print(json.dumps({"route":choice,"selection":digest(NEW/"selection.json")}))

def stat_private(p):
    s=p.stat(follow_symlinks=False)
    import stat
    return stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o700 and s.st_uid==1000

if __name__=="__main__":decide()
