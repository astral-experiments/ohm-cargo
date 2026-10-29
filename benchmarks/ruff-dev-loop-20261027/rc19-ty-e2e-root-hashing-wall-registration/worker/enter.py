"""Give each genuine Cargo history fresh writable state at exactly the original literal paths."""
import os
import pwd
import signal
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

def bind(here, there, readonly=False):
    subprocess.run(["/usr/bin/mount", "--bind", str(here), str(there)], check=True)
    if readonly:
        subprocess.run(["/usr/bin/mount", "-o", "remount,bind,ro", str(there)], check=True)

def mounted(lane, arm, label, mode, method, obligation, parent):
    assert os.geteuid() == 0 and os.readlink("/proc/self/ns/mnt") != parent
    state = LANES / lane
    assert state.stat().st_uid == 1000
    for key, dest, base in (("state", LIVE, M/"states/parent-warm"), ("source", ROOT,ROOT)):
        assert not os.path.ismount(dest)
        lowers = [F/"donor"/(key+"-upper"),base]
        if lane != "train":
            assert (K/"binding/donor.json").is_file()
            lowers.insert(0, LANES/"train"/(key+"-upper"))
        opt = "lowerdir="+":".join(map(str, lowers))+",upperdir="+str(state/(key+"-upper"))+",workdir="+str(state/(key+"-work"))
        subprocess.run(["/usr/bin/mount","-t","overlay","-o",opt,"overlay",str(dest)],check=True)
        os.chown(dest,1000,1000)
    if lane.startswith("leaf-"):
        bind(state/"empty-unit",E2E.parent.parent)
        bind(state/"empty-incremental",INC)
    assert str(K).startswith("/home/") and not K.is_symlink()
    image=Path(get(K/"binding/physical.json")["subjects"][arm]["cargo"])
    bind(image,M/"sdk/bin/cargo",True)
    os.setgroups([]);os.setgid(1000);os.setuid(1000)
    actual_home=pwd.getpwuid(1000).pw_dir
    os.environ.clear();os.environ.update(HOME=actual_home,PATH=actual_home+"/.cargo/bin:/usr/local/bin:/usr/bin:/bin",LANG="C",LC_ALL="C")
    os.execv("/usr/bin/python3",["/usr/bin/python3","-IB",str(K/"ops/worker.py"),lane,arm,label,mode,method,obligation])

def launch(lane,arm,label,mode,method,obligation):
    for s in [lane,arm,label]:safe_name(s)
    assert arm in ("parent","child") and mode in ("original","edited","invalid")
    assert lane in ("warm-"+arm,"leaf-"+arm+"-original","leaf-"+arm+"-edited") and not (LANES/lane).is_symlink()
    assert os.getuid()==1000 and set(os.sched_getaffinity(0))==set(SCHEMA["cpus"])
    reserve=200_000_000
    if obligation in ("dirty","leaf"):reserve=520_000_000
    before=floors(reserve)
    state=LANES/lane
    if not state.exists():
        state.mkdir(parents=True)
        for name in ["source-upper","source-work","state-upper","state-work"]:
            (state/name).mkdir()
        if lane.startswith("leaf-"):
            for name in ["empty-unit","empty-incremental"]:(state/name).mkdir()
    visit=REPORTS/lane/label
    visit.mkdir(parents=True,exist_ok=False)
    command=["sudo","-n","/usr/bin/unshare","--mount","--propagation","private","--","/usr/bin/python3","-IB",str(Path(__file__).resolve()),"mounted",lane,arm,label,mode,method,obligation,os.readlink("/proc/self/ns/mnt")]
    with (visit/"namespace.stdout").open("xb") as stdout,(visit/"namespace.stderr").open("xb") as stderr:
        process=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
        low=before.copy(); broke=None; deadline=time.monotonic()+1450
        while process.poll() is None:
            now=free()
            low={k:min(low[k],v) for k,v in now.items()}
            if any(now[k]<SCHEMA[k+"_floor"] for k in low) or time.monotonic()>deadline:
                broke=now
                os.killpg(process.pid,signal.SIGTERM)
                break
            time.sleep(.4)
        rc=process.wait()
    put(visit/"outer.json",{"start_free":before,"minimum_free":low,"exit":rc,"space_failure":broke,"new_state":str(state),"isolated_namespace":True})
    assert rc==0 and broke is None,(lane,label,rc,broke,(visit/"namespace.stderr").read_text()[-1000:])

if __name__=="__main__":
    if sys.argv[1]=="mounted":
        mounted(*sys.argv[2:])
    else:
        launch(*sys.argv[1:])
