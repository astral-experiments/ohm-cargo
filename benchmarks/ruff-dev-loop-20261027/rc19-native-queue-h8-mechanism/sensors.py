"""Capture only the gated guest process and its descendants. No ptrace or native tool replacement."""
from pathlib import Path
import ctypes as ct,json,os,queue,re,sys,time,threading,gzip
from collections import Counter
from bcc import BPF
d=Path(sys.argv[1]);source=Path(__file__).with_name('sensors.c')
w=Path(sys.argv[2]).stat();kdev=(os.major(w.st_dev)<<20)|os.minor(w.st_dev)
src=source.read_text().replace('WILD_INO',str(w.st_ino)+'ULL').replace('WILD_DEV',str(kdev)+'U')
for label in 'AB':
    root=source.parent.parent; file=root/('parent19' if label=='A' else 'product19')/'cargo';z=file.stat()
    src=src.replace('CARGO_'+label+'_INO',str(z.st_ino)+'ULL').replace('CARGO_'+label+'_DEV',str((os.major(z.st_dev)<<20)|os.minor(z.st_dev))+'U')
b=BPF(text=src,cflags=["-fms-extensions","-Wno-microsoft-anon-tag"])
class Event(ct.Structure):
    _fields_=[('ns',ct.c_uint64),('ino',ct.c_uint64),('x',ct.c_uint64*10)]+[(k,ct.c_uint32)for k in ('type','tid','tgid','owner','dev','off','len','total')]
head=ct.sizeof(Event);assert head==128,head
clocks={}; slow=[]
def touch(tid,stamp,value):
    if clocks.get(tid,-1)>stamp:return
    clocks[tid]=stamp
    if value is None:live.pop(tid,None)
    else:live[tid]=value
events=[];live={};argv={};width={};temps={};native_writes=[];err=[];samples=[];stop=threading.Event();lost=[];smaps_errors=Counter()
clock=time.monotonic_ns
def attach_threads(ts):
    c0=time.thread_time_ns();next_due=ts;next_pss=ts
    while not stop.is_set():
        now=clock();slots=list(live.items());rows=[];pss={};seen=set();want=now>=next_pss
        if want:next_pss=now+350_000_000
        for tid,owner in slots:
            t=Path('/proc')/str(tid)
            try:
                v=(t/'stat').read_text().rsplit(')',1)[1].split()
                tgid=group.get(tid)
                if not tgid:
                    tgid=int(next(s.split()[1]for s in (t/'status').read_text().splitlines()if s.startswith('Tgid:')));group[tid]=tgid
                wchan=None
                if tgid==pid and v[0] in ('S','D') and want:
                    try:wchan=(t/'wchan').read_text().strip()
                    except OSError:pass
                rows.append([tid,tgid,owner,v[0],wchan])
                if want and tgid not in seen:
                    seen.add(tgid)
                    try:
                        pss[tgid]=int(next(s.split()[1]for s in (Path('/proc')/str(tgid)/'smaps_rollup').read_text().splitlines()if s.startswith('Pss:')))
                    except (OSError,StopIteration):smaps_errors['pss_race']+=1
            except (OSError,ValueError,IndexError,StopIteration):smaps_errors['task_race']+=1
        samples.append([now,clock()-now,rows,pss if want else None]);next_due+=40_000_000
        if next_due<clock():next_due=clock()+1_000_000
        stop.wait(max(0,(next_due-clock())/1e9))
    cpu['sampler']=time.thread_time_ns()-c0
def cb(cpu_id,data,size):
    e=ct.cast(data,ct.POINTER(Event)).contents
    raw=ct.string_at(data+head,e.len)if e.len else b''
    if e.type==1:
        touch(e.off,e.ns,e.owner);events.append([1,e.ns,e.tid,e.tgid,e.owner,e.off])
    elif e.type==2:
        if e.total==0xffffffff:err.append('exec arg exceeds 512 KiB')
        assert e.total<=524288
        touch(e.tid,e.ns,e.owner);group[e.tid]=e.tgid
        argv[(e.tid,e.ns)]=[e.dev,e.ino,e.owner,e.total,{}];events.append([2,e.ns,e.tid,e.tgid,e.owner,e.off])
    elif e.type==3:
        row=argv[e.tid,e.ns];row[4][e.off]=raw
        if e.ino==w.st_ino and e.dev==kdev and sum(map(len,row[4].values()))==e.total:
            import hashlib
            args=[os.fsdecode(s)for s in b''.join(row[4][i]for i in sorted(row[4])).rstrip(b'\0').split(b'\0')]
            try:
                objs=[v for v in args if v.startswith('/') and v.endswith('/symbols.o')];dirs=[v[2:]for v in args if v.startswith('-L/') and v.endswith('/raw-dylibs')];res=[v.split('=',2)[2]for v in args if v.startswith('-plugin-opt=-fresolution=')]
                if not objs and not dirs and (not res or d.name.startswith("smoke")):return
                assert len(objs)==len(dirs)==len(res)==1
                obj,di,rs=[Path('/proc')/str(e.tid)/'root'/Path(p).relative_to('/')for p in (objs[0],dirs[0],res[0])]
                assert all(not f.is_symlink()for f in (obj,di,rs));ob=obj.read_bytes();rr=rs.read_bytes()
                temps[e.tid]={'object':hashlib.sha256(ob).hexdigest(),'resolution':hashlib.sha256(rr).hexdigest(),'object_len':len(ob),'resolution_len':len(rr),'raw_dylibs':sorted(x.name for x in di.iterdir())}
            except (OSError,ValueError,AssertionError)as ex: err.append('transient '+str(e.tid)+' '+str(ex))
    elif e.type==4:
        touch(e.tid,e.ns,None);events.append([4,e.ns,e.tid,e.tgid,e.owner,e.off,list(e.x)])
    elif e.type in (5,8):
        native_writes.append([e.type,e.ns,e.owner,e.tid,e.off,len(raw),raw.decode(errors='replace')[:380]])
        if b'Acquired jobserver tokens' in raw:
            clean=re.sub(rb'\x1b\[[0-9;]*m',b'',raw);v=re.search(rb'Acquired jobserver tokens.*?count[=: ]+(\d+)',clean);assert v,raw
            width.setdefault(e.owner,[]).append([e.ns,int(v[1])])
    elif e.type==6: slow.append([e.tid,e.tgid,*list(e.x)[:4],e.ns])
    else:err.append('kernel-event-'+str(e.type))
def drop(cpu_id,count):lost.append([cpu_id,count])
group={};cpu={};b['out'].open_perf_buffer(cb,page_cnt=256,lost_cb=drop)
(d/'sensor-active').write_text('ok\n')
deadline=time.monotonic()+120
while not(d/'pid').exists():
    assert time.monotonic()<deadline;time.sleep(.01)
pid=int((d/'pid').read_text());assert (Path('/proc')/str(pid)).stat().st_uid==1000
b['members'][ct.c_uint(pid)]=ct.c_uint(0);live[pid]=0
thr=threading.Thread(target=attach_threads,args=(clock(),));thr.start();start=time.thread_time_ns();(d/'armed').write_text(str(pid)+'\n');dead=None
while True:
    b.perf_buffer_poll(timeout=15)
    if not live and any(e[0]==4 and e[2]==pid for e in events):
        if dead is None:dead=time.monotonic()
        if time.monotonic()-dead>.13:break
    if time.monotonic()>deadline+240:raise TimeoutError((len(live),list(live)[:50]))
stop.set();thr.join();cpu['consumer']=time.thread_time_ns()-start
arr=[]
for (tid,ns),(dev,ino,owner,total,pieces) in argv.items():
    buf=b''.join(pieces[i]for i in sorted(pieces));assert len(buf)==total and buf.endswith(b'\0'),(tid,total,len(buf))
    arr.append([ns,tid,dev,ino,owner,[os.fsdecode(arg)for arg in buf[:-1].split(b'\0')]])
result={'root':pid,'fork_exec_exit':events,'exec_argv':arr,'temps':temps,'width':width,'native_writes':native_writes,'slow_cargo_syscalls':slow,'samples':samples,'processor_ns':cpu,'sample_misses':smaps_errors,'errors':err,'lost':lost,'clock':'CLOCK_MONOTONIC','sample_period_ms':40,'pss_period_ms':350,'exit_fields':['on_cpu_ns','runqueue_wait_ns','minflt','majflt','storage_read_bytes','storage_written_bytes','voluntary_switches','involuntary_switches','utime_ns','stime_ns']}
(d/'sensor.json.gz').write_bytes(gzip.compress((json.dumps(result,sort_keys=True)+'\n').encode(),compresslevel=1,mtime=0))
assert not err and not lost,(err,lost)
