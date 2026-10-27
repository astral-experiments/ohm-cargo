"""Count one resolved rustc, binding the observed executable, driver and proc macro to real mapped inodes."""
from pathlib import Path
from collections import Counter
import json, os, signal, subprocess, sys, time

d=Path(sys.argv[1]); assert sys.argv[2]=="0"; args=sys.argv[3:]
assert args[:2]==["rustc","+ohm"]
spec=json.loads((Path(__file__).parent/"inner-binding.json").read_bytes());sdk=Path(spec["sdk"]);image=Path(spec["frontend"])
paths={k:Path(v) for k,v in spec["mapped"].items()}
ident={k:(f.stat().st_dev,f.stat().st_ino) for k,f in paths.items()}
counter=d/"counter.txt"
cmd=[str(sdk/"sdk/bin64/drrun"),"-no_follow_children","-c",str(sdk/"client/libpidcounter.so"),str(counter),"--",str(image),*args[2:]]
maps={};t0=time.monotonic();timed_out=False
with (d/"stdout").open("xb") as out,(d/"stderr").open("xb") as err:
    child=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True)
    while child.poll() is None:
        if time.monotonic()-t0>300:
            os.killpg(child.pid,signal.SIGKILL);child.wait();timed_out=True;break
        if len(maps)<len(paths) and counter.is_file():
            first=counter.open().readline().split()
            if len(first)==4 and first[0]=="B":
                pid=int(first[1])
                try: data=Path('/proc',str(pid),'maps').read_text()
                except (FileNotFoundError,ProcessLookupError): data=''
                for line in data.splitlines():
                    a=line.split(None,5)
                    if len(a)!=6:continue
                    maj,mi=map(lambda v:int(v,16),a[3].split(':')); ident_here=(os.makedev(maj,mi),int(a[4]))
                    for k,v in ident.items():
                        if k not in maps and v==ident_here:maps[k]={"pid":pid,"device":v[0],"inode":v[1],"path":a[5],"logical":str(paths[k])}
        time.sleep(.10)
rc=child.returncode
(d/"mappings.json").write_text(json.dumps({"captured":maps,"expected":ident,"complete":set(maps)==set(paths),"timed_out":timed_out},indent=2,sort_keys=True)+"\n")
(d/"child.json").write_text(json.dumps({"exit":rc,"argv":args,"actual_count_command":cmd,"wall_ns":None,"affinity":sorted(os.sched_getaffinity(0))},indent=2)+"\n")
if rc or timed_out or set(maps)!=set(paths):sys.exit(1)
