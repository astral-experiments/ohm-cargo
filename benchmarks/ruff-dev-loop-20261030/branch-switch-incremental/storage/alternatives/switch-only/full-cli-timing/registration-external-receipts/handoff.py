#!/usr/bin/env python3
"""Give the external collector read-only FDs after native work, and wait for its commit."""
import array
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from receiver import HeldBody, canonical, check, identity

def connect_and_hold(address, tag, status, paths, *, after_connect=None):
    fds=[]; files=[]; absent=[]
    for role,p in paths.items():
        if p is None:
            absent.append(role)
            continue
        try:
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        except FileNotFoundError:
            absent.append(role)
            continue
        s=os.fstat(fd)
        check(stat.S_ISREG(s.st_mode) and identity(s)==identity(p.lstat()),"unexpected native path")
        fds.append(fd);files.append([role,list(identity(s))])
    check(status or (len(files)==len(paths) and not absent),"successful workload omitted an actual native body")
    message=canonical(dict(pid=os.getpid(),uid=os.getuid(),slot=tag,exit=status,files=files,absent=absent,
                           mountns=os.readlink("/proc/self/ns/mnt")))
    rights=array.array("i",fds)
    try:
        while True:
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
                try:
                    s.connect(address)
                    if after_connect:after_connect()
                    n=s.sendmsg([message],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,rights)] if fds else [])
                    check(n==len(message),"short sender record")
                    reply=s.recv(1024)
                except (FileNotFoundError,ConnectionResetError,ConnectionRefusedError,BrokenPipeError):
                    reply=b""
                if reply:
                    proof=json.loads(reply)
                    check(proof["slot"]==tag and len(proof["commit"])==64,"invalid acknowledgement")
                    return proof
            # Keep the only genuine native FDs, stream buffers and the namespace
            # intact on loss of the external receiving process or filesystem.
            time.sleep(5)
    finally:
        for fd in fds:os.close(fd)

def receive(connection, slot, roles, *, owner, carrier_pid=None):
    pid,uid,_gid=struct.unpack("3i",connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    data,aux,flags,_=connection.recvmsg(8192,socket.CMSG_SPACE(8*array.array("i").itemsize),socket.MSG_CMSG_CLOEXEC)
    fds=[];items={}
    try:
        for level,op,buf in aux:
            check((level,op)==(socket.SOL_SOCKET,socket.SCM_RIGHTS),"unexpected ancillary message")
            got=array.array("i");got.frombytes(buf);fds.extend(got)
        check(flags&(socket.MSG_CTRUNC|socket.MSG_TRUNC)==0 and data,"truncated native handoff")
        info=json.loads(data)
        check(info["pid"]==pid and info["uid"]==uid==owner and info["slot"]==slot and
              0<=info["exit"]<256 and info["mountns"]==os.readlink(f"/proc/{pid}/ns/mnt"),
              "wrong producer or slot")
        if carrier_pid is not None:
            ancestor=pid
            while ancestor>1 and ancestor!=carrier_pid:
                lines=Path(f"/proc/{ancestor}/status").read_text().splitlines()
                ancestor=int(next(x.split()[1] for x in lines if x.startswith("PPid:")))
            check(ancestor==carrier_pid,"sender does not descend from the enrolled carrier")
        names=[role for role,ident in info["files"]]
        check(len(fds)==len(names) and set(names)|set(info["absent"])==set(roles) and
              len(names)+len(info["absent"])==len(roles) and len(set(names))==len(names) and
              (info["exit"] or not info["absent"]),"incorrect captured products")
        for (role,expected),fd in zip(info["files"],fds):
            body=HeldBody(fd)
            check(list(body.original)==expected,"kernel file differs from peer's native path")
            items[role]=body
        return info,items,fds
    except BaseException:
        for fd in fds:os.close(fd)
        raise

def ack(connection,tag,sha):
    check(len(sha)==64,"invalid durable hash")
    connection.sendall(canonical(dict(slot=tag,commit=sha)))

if __name__=="__main__":
    conf=json.loads(Path(sys.argv[1]).read_bytes());view=Path(conf["canonical"])
    live=(Path(conf["receipts"])/"logs"/sys.argv[2]/"front.json").is_file()
    reply=connect_and_hold("/var/tmp/escrow.sock",sys.argv[2],int(sys.argv[3]),
           {"ruff.elf":view/"products/debug/ruff" if live else None,
            "reader.elf":view/"reader.elf" if live else None})
    sys.exit(int(sys.argv[3]))
