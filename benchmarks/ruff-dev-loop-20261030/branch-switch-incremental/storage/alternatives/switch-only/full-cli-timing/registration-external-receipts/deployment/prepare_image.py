#!/usr/bin/env python3
"""Allocate the actual HOME image, check for formatter-created holes and verify its bytes."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from site_gate import NEW,SCRATCH,HOME_DEVICE,read,release,caps,mem
from receiver import MIB,check,digest,reserve_file,storage_guards
from select_route import exclusive_record,read_process

def main():
    assert os.getuid()==1000
    a,c=release();p=read(NEW/"selection.json")
    check(p["route"]=="external-home" and p["authorization"]==digest(NEW/"authorize-selection.json") and
          read_process(p["old_pid"])["state"] in ("T","t") and not (Path(c["receipts"])/"clock-release.json").exists(),
          "alternative does not exclusively own an unstarted installation")
    check(storage_guards(HOME_DEVICE,SCRATCH,mem(),entry=True)[1],"physical H9 floors no longer admit allocation")
    img=NEW/"receiver.ext4";reserve_file(img,383*MIB)
    subprocess.run(["/usr/sbin/mkfs.ext4","-q","-F","-m0","-E","nodiscard,lazy_itable_init=0,lazy_journal_init=0",img],check=True)
    first=digest(img);before=img.stat().st_blocks*512
    with img.open("r+b") as f:
        os.posix_fallocate(f.fileno(),0,383*MIB);os.fsync(f.fileno())
    after=img.stat().st_blocks*512
    check(first==digest(img) and 383*MIB<=after<384*MIB and storage_guards(HOME_DEVICE,SCRATCH,mem(),entry=False)[1],
          "physical formatted image has changed or is under the reserve")
    exclusive_record(NEW/"image.json",dict(bytes=img.stat().st_size,after_mkfs=before,after_reserve=after,
        home_dev=img.stat().st_dev,sha_before_mount=first,selection=digest(NEW/"selection.json"),capacity=caps()))
if __name__=="__main__":main()
