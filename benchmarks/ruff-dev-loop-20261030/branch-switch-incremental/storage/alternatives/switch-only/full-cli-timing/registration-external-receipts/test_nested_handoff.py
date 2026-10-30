#!/usr/bin/env python3
"""Exercise the actual root-mount/ordinary-holder boundary using real native files."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from handoff import ack,receive
from receiver import canonical,check,digest,publish,reopen

def main(frame, results):
    pub=Path(__file__).resolve().parent;spool=frame/"spool";work=frame/"work";store=frame/"receiver/store"
    shell="""set -eu
    mount --make-rprivate /
    umount "$1/receiver"
    mount --bind "$1/spool" /var/tmp
    mount -o remount,bind,ro /
    exec /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs /usr/bin/python3 -IB "$2/handoff.py" "$3" "$4" "$5"
    """
    os.chdir(spool);observations=[]
    protocol=hashlib.sha256(b"nested custody calibration").hexdigest()
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as server:
        server.bind("escrow.sock");server.listen(1);server.settimeout(15)
        for label,code,native in [("complete",0,"independent-success"),("wrong",101,"actual-wrong")]:
            view=work/("same-path-"+label);(view/"products/debug").mkdir(parents=True)
            os.link(work/"provider"/native,view/"products/debug/ruff")
            os.link(work/"provider/reference",view/"reader.elf")
            tag="nested-"+label
            (view/"logs"/tag).mkdir(parents=True);(view/"logs"/tag/"front.json").write_bytes(b"{}\n")
            conf=work/(label+".json");conf.write_bytes(canonical(dict(canonical=str(view),receipts=str(view))))
            proc=subprocess.Popen(["sudo","-n","unshare","-m","--propagation","private","/bin/bash","-c",shell,
                "sender",frame,pub,conf,tag,str(code)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL)
            try:
                expected_holder=None
                for cycle in (0,1):
                    with server.accept()[0] as conn:
                        header,bodies,fds=receive(conn,tag,["ruff.elf","reader.elf"],owner=os.getuid(),carrier_pid=proc.pid)
                        try:
                            check(header["mountns"]!=os.readlink("/proc/self/ns/mnt") and header["exit"]==code,
                                  "sender did not run in the separate native namespace")
                            if cycle==0:
                                expected_holder=header
                                continue  # An actual disconnected receiving client, without ACK.
                            check(header==expected_holder and proc.poll() is None,"failed receiver lost physical originals")
                            packet=publish(store,tag,protocol,{"failure-artifacts/"+k:v for k,v in bodies.items()})
                            read=reopen(store/packet["path"],packed_sha=packet["sha256"])
                            check(read["files"]["failure-artifacts/ruff.elf"]==[(view/"products/debug/ruff").stat().st_size,
                                  digest(view/"products/debug/ruff")],"wrong native body after reconnect")
                            ack(conn,tag,packet["sha256"])
                            observations.append(dict(tag=tag,exit=code,kernel_sender_uid=header["uid"],
                                different_mount=True,same_live_fds_after_disconnect=True,files=read["files"],archive=packet["sha256"]))
                        finally:
                            for fd in fds:os.close(fd)
                check(proc.wait(timeout=10)==code,"actual sender exit status changed")
            finally:
                if proc.poll() is None:
                    # QA fixtures only. Production keeps a failed physical namespace.
                    proc.terminate();proc.wait(timeout=10)
    (results/"nested.json").write_bytes(canonical(dict(scored_samples=0,observations=observations)))

if __name__=="__main__":main(*map(Path,sys.argv[1:3]))
