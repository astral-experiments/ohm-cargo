"""Sample cumulative CPU and I/O for each process in this single Cargo session."""
import json,os,subprocess,sys,time
from pathlib import Path
dest=Path(sys.argv[1])
allp=Path('/proc')
current=set(os.sched_getaffinity(0))
start=time.monotonic_ns()
p=subprocess.Popen(sys.argv[2:],start_new_session=True)
monitor=set(range(8,32)) & set(int(x) for x in (allp/'self/status').read_text().split('Cpus_allowed_list:')[1].splitlines()[0].strip().split(',') if x.isnumeric())
try:os.sched_setaffinity(0,{31})
except OSError:pass
records={}
while True:
    now=time.monotonic_ns()-start
    for f in allp.iterdir():
        if not f.name.isnumeric():continue
        try:
            data=(f/'stat').read_text().rsplit(')',1)[1].split()
            if int(data[3])!=p.pid:continue
            pid=int(f.name);exe=os.readlink(f/'exe')
            key=(pid,exe)
            if key not in records:
                args=[os.fsdecode(x) for x in (f/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
                records[key]=dict(pid=pid,ppid=int(data[1]),exe=exe,argv=args,first_ns=now,peak_rss=0)
            row=records[key];row['last_ns']=now
            row['utime_ticks']=int(data[11]);row['stime_ticks']=int(data[12])
            row['cutime_ticks']=int(data[13]);row['cstime_ticks']=int(data[14]);row['peak_rss']=max(row['peak_rss'],int(data[21]))
            row['io']={k:int(v) for k,v in (s.split(':',1) for s in (f/'io').read_text().splitlines())}
        except (FileNotFoundError,PermissionError,ProcessLookupError,IndexError):continue
    rc=p.poll()
    if rc is not None:break
    time.sleep(.008)
(dest/'life.json').write_text(json.dumps(dict(start_ns=start,elapsed=time.monotonic_ns()-start,command=sys.argv[2:],child_cpus=sorted(current),monitor_cpus=sorted(os.sched_getaffinity(0)),hz=os.sysconf('SC_CLK_TCK'),records=list(records.values())),sort_keys=True)+'\n')
sys.exit(rc)
