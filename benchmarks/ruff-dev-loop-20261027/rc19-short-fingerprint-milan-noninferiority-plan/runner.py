"""Restore a single private ext4 store for each visit and guard the frozen cohort."""
import collections
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ops=Path(__file__).resolve().parent
root=ops.parent
oldroot=Path.home()/".cache/ohm-ruff-multi-select-20261029-v1"
p=oldroot/"pending-clock-stable-v2"
mem=Path("/dev/shm")/root.name
spec=json.loads((ops/"subjects.json").read_bytes())
roster=json.loads((ops/"order.json").read_bytes())
action=sys.argv[1]
assert action in ("inspect","qualify","measure")
assert root.name=="ohm-cargo-short-read-milan-20261029-v1" and root==Path.home()/".cache"/root.name
home_uid=os.getuid();assert home_uid!=0
os.umask(0o022)
def sha(f):
    with Path(f).open("rb") as src:return hashlib.file_digest(src,"sha256").hexdigest()
def read(f):return json.loads(Path(f).read_bytes())
def save(f,value):
    with Path(f).open("x") as out:json.dump(value,out,indent=2,sort_keys=True);out.write("\n")
def files(f):return {s.split("  ",1)[1]:s.split("  ",1)[0] for s in f.read_text().splitlines()}
assert all(sha(ops/k)==v for k,v in files(ops/"SHA256SUMS").items())
assert sha(p/"scored/observations.json")==spec["prior_trials"]["milan"] and len(read(p/"scored/observations.json"))==32
assert len(roster)==32
for arm,rec in spec["images"].items():
    folder=root/"images"/arm
    assert sha(folder/"cargo")==rec["binary"] and sha(folder/"complete.json")==rec["producer_receipt"]
    built=read(folder/"complete.json");assert all(built[k]==rec[k] for k in ("binary","source_commit","stamp","profile"))
for s,g in spec["sources"].items():
    for arm in ("A","B"):
        reference=p/"physical-common"/(arm+"-after-common-"+s+".json")
        assert sha(reference)==g["products597"] and len(read(reference))==597
    assert sha(p/"donors"/("A-"+s+".tar.zst"))==g["sha256"]
assert sha(p/"clock_common_idempotent.py")==spec["base_helper"]
assert sha(oldroot/"ops/common.py")==spec["ops_helper"] and sha(oldroot/"ops/trace.py")==spec["process_tracer"]
# Reuse the physically authenticated host path definitions, not its clock logic.
import runpy
h=runpy.run_path(str(p/"clock_common_idempotent.py"))
assert h["hot_images"]()==spec["tools"]
scratch=h["scratch"]
gib=2**30
def floors(restoring=False):
    free={str(k):shutil.disk_usage(k).free for k in (root,scratch,Path("/dev/shm"))}
    assert free[str(root)]>=6*gib+(int(1.6*gib) if restoring else 0) and free[str(scratch)]>=6*gib and free["/dev/shm"]>=8*gib,free
    return free
lock_path=scratch.parent/"ohm-whole-skips-20261027/native-measure.lock"
assert lock_path.is_file()
with lock_path.open("rb") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    mem.mkdir(mode=0o700,exist_ok=True);assert mem.resolve()==mem and mem.stat().st_uid==home_uid
    archive_dir=root/"restore";active=archive_dir/"active"
    result=root/"reports"/action;result.mkdir()
    save(result/"start.json",{"floors":floors(True),"uid":home_uid,"host":socket.gethostname(),"host_cpus":sorted(os.sched_getaffinity(0)),"manifest":sha(ops/"SHA256SUMS"),"action":action})
    def visit(label,arm,source,mode,parent=result):
        floors(True);assert not active.exists()
        case=parent/label;case.mkdir();save(case/"case.json",{"label":label,"source":source,"arm":arm,"mode":mode})
        active.mkdir();temp=mem/(action+"-"+parent.name+"-"+label);temp.mkdir()
        for n in ("src-u","src-w","home-u","home-w","tmp"):(temp/n).mkdir()
        (temp/"tmp").chmod(0o1777)
        for name,original in [("src-u",h["work"]),("home-u",oldroot/"cargo-home")]:
            (temp/name).chmod(original.stat().st_mode & 0o777);os.utime(temp/name,ns=(original.stat().st_atime_ns,original.stat().st_mtime_ns))
        operand=p/"donors"/("A-"+source+".tar.zst")
        subprocess.run(["tar","--delay-directory-restore","--same-permissions","--zstd","-xpf",operand,"-C",active],check=True)
        floors()
        cmd=["sudo","-n","unshare","--mount","--propagation","private",str(ops/"namespace.sh"),str(root),str(case),str(active),str(temp),str(home_uid),str(os.getgid()),arm,mode]
        with (case/"outer.stdout").open("xb") as o,(case/"outer.stderr").open("xb") as e:
            rc=subprocess.run(cmd,stdout=o,stderr=e,timeout=1500).returncode
        save(case/"outer-exit.json",{"status":rc,"floors":floors()})
        assert rc==0 and read(case/"terminal.json")["success"],(label,rc)
        assert active.resolve()==active and active.parent==root/"restore" and not os.path.ismount(active)
        shutil.rmtree(active)  # Only this visit's independently extracted and fully validated copy.
        return case
    try:
        if action=="inspect":visit("setup-B-child","B","child","inspect")
        elif action=="qualify":
            for source in ("parent","child"):
                for arm in ("B","E"):visit(arm+"-"+source,arm,source,"qualify")
            for arm in ("B","E"):visit(arm+"-real-error",arm,"child","holdout")
            for source in ("parent","child"):
                outcomes={}
                for arm in ("B","E"):
                    d=result/(arm+"-"+source);s=json.loads(gzip.decompress((d/"reads.json.gz").read_bytes()))
                    assert s["unique_hex16"]>0 and (arm=="B" or s["counts"].get("read_16_returned_16",0)>0 and s["counts"].get("read_1_returned_0",0)>0)
                    outcomes[arm]={"roles":read(d/"native-result.json")["roles"],"fingerprints":s["unique_hex16"],"counts":s["counts"],"raw":s["raw_sha256"]}
                save(result/(source+"-reads.json"),outcomes)
            save(result/"complete.json",{"manifest":sha(ops/"SHA256SUMS"),"sources":{s:sha(result/(s+"-reads.json")) for s in ("parent","child")},"verdicts":{a:sha(result/(a+"-real-error")/"real-private-error/verdict.json") for a in ("B","E")},"native":{a+"-"+s:sha(result/(a+"-"+s)/"native-result.json") for a in ("B","E") for s in ("parent","child")},"passed":True})
        else:
            grant=read(root/"grant.json")
            assert grant["go"] is True and grant["pairs"]==32 and grant["replacements"]==0
            assert grant["manifest"]==sha(ops/"SHA256SUMS") and grant["qualification"]==sha(root/"reports/qualify/complete.json")
            assert len(grant["published_commit"])==40 and int(grant["published_commit"],16)>0
            rows=[]
            for cell in roster:
                n=cell["pair"];pair=result/(f"pair-{n:02}");pair.mkdir();r=dict(cell);r["wall_ns"]={}
                for arm in cell["order"]:
                    v=visit(arm,arm,cell["source"],"measure",pair);q=read(v/"check/wall.json");assert q["status"]==0
                    r["wall_ns"][arm]=q["wall_ns"]
                r["validated"]=True;save(pair/"result.json",r);rows.append(r)
                print("validated pair",n+1,flush=True)
            save(result/"observations.json",rows)
            with (result/"analysis.json").open("xb") as f:subprocess.run([sys.executable,"-IB",ops/"analysis.py",result/"observations.json"],stdout=f,check=True)
    except BaseException:
        import traceback
        (result/"first-failure.txt").write_text(traceback.format_exc())
        raise
