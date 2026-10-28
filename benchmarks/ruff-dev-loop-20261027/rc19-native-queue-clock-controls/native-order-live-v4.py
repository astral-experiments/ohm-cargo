"""Census actual compiler, driver, dispatcher and stock native ELF execs by identity, retaining failed runs."""
from pathlib import Path
import ctypes
import errno
import hashlib
import json
import os
import signal
import sys
import time
import threading
sys.path.insert(0,str(Path(__file__).resolve().parent))
import runpy
sample_tree=runpy.run_path(str(Path(__file__).resolve().parent/"native-order-rss-v4.py"))["sample_tree"]

libc=ctypes.CDLL(None,use_errno=True)
libc.ptrace.argtypes=(ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p)
libc.ptrace.restype=ctypes.c_long
options=2|4|8|16|0x100000
def trace(req,pid,data=0):
    rc=libc.ptrace(req,pid,None,ctypes.c_void_p(data))
    if rc==-1:
        err=ctypes.get_errno()
        if req==7 and err==errno.ESRCH:return
        raise OSError(err,os.strerror(err))
def ident(p):
    s=p.stat();return s.st_dev,s.st_ino
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def run(report,contract,cmd):
    config=json.loads(contract.read_bytes());images={}
    for role,data in config["images"].items():
        path=Path(data["path"])
        assert role in ("cargo","rustc","stock-wild","probe","gcc","collect2") and sha(path)==data["sha256"]
        idx=ident(path);assert idx not in images;images[idx]=role
    assert {"rustc","stock-wild"}<=set(images.values())
    root=os.fork()
    if root==0:
        trace(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execvp(cmd[0],cmd)
    pid,pstatus=os.waitpid(root,0);assert os.WIFSTOPPED(pstatus)
    trace(0x4200,pid,options);trace(7,pid)
    done=threading.Event();memory={};sampler=threading.Thread(target=sample_tree,args=(root,done,memory),daemon=True);sampler.start()
    events=[];rss={};exit_time={};status={};owners=set();root_code=None
    while True:
        try:pid,pstatus,usage=os.wait4(-1,0x40000000)
        except ChildProcessError:break
        if os.WIFEXITED(pstatus) or os.WIFSIGNALED(pstatus):
            code=os.waitstatus_to_exitcode(pstatus)
            if pid==root:root_code=code
            if pid in owners:
                status[pid]=code;exit_time[pid]=time.time_ns();rss[pid]=usage.ru_maxrss
            continue
        assert os.WIFSTOPPED(pstatus)
        sig=os.WSTOPSIG(pstatus);ops=pstatus>>16
        if ops==4:
            proc=Path("/proc")/str(pid)
            identity=ident(proc/"exe")
            role=images.get(identity)
            if role:
                raw=(proc/"cmdline").read_bytes()
                argv=[os.fsdecode(x) for x in raw.rstrip(b"\0").split(b"\0")]
                out=argv[argv.index("-o")+1] if "-o" in argv else None
                target=None
                if role=="rustc":
                    if "--crate-name" in argv and not (argv[argv.index("--crate-name")+1]=="___" and argv[1]=="-" and "--print=file-names" in argv):
                        role="rustc-link-only" if "-Zlink-only" in argv or "link-only" in argv else "rustc-full"
                        target=argv[argv.index("--crate-name")+1]
                    else:role="rustc-query"
                temporary={}
                if role=="stock-wild":
                    objects=[Path(x)for x in argv if x.startswith("/")and x.endswith("/symbols.o")]
                    rawdirs=[Path(x.removeprefix("-L"))for x in argv if x.startswith("-L/")and x.endswith("/raw-dylibs")]
                    resolutions=[Path(x.removeprefix("-plugin-opt=-fresolution="))for x in argv if x.startswith("-plugin-opt=-fresolution=")]
                    assert len(objects)==len(rawdirs)==len(resolutions)==1 and objects[0].parent==rawdirs[0].parent
                    assert objects[0].is_file() and not objects[0].is_symlink() and rawdirs[0].is_dir()and not rawdirs[0].is_symlink()and resolutions[0].is_file() and not resolutions[0].is_symlink()
                    temporary={"object":sha(objects[0]),"resolution":sha(resolutions[0]),"raw_dylibs":sorted(x.name for x in rawdirs[0].iterdir()),"object_len":objects[0].stat().st_size,"resolution_len":resolutions[0].stat().st_size}
                events.append({"temporary":temporary,"start_ns":time.time_ns(),"ppid":int(next(x.split()[1] for x in (proc/"status").read_text().splitlines() if x.startswith("PPid:"))),"pid":pid,"role":role,"dev":identity[0],"ino":identity[1],
                               "argv_sha256":hashlib.sha256(raw).hexdigest(),"target":target,"out":out,"argv":argv})
                owners.add(pid)
        trace(7,pid,0 if ops or sig in (signal.SIGTRAP,signal.SIGSTOP) else sig)
    done.set();sampler.join()
    assert root_code is not None and owners==status.keys()
    report.write_text(json.dumps({"root_exit":root_code,"events":events,"process_exit":status,"exit_ns":exit_time,"maxrss_kib":rss,"memory":memory,
                                 "images":config["images"]},sort_keys=True,indent=2)+"\n")
    return root_code if root_code>=0 else 128-root_code
if __name__=="__main__":
    raise SystemExit(run(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3:]))
