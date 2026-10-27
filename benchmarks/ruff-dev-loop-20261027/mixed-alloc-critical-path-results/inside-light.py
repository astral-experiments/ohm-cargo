"""Observe genuine process lifetimes, resources and file reads in a disposable Ruff native state."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,os,re,subprocess,sys,threading,time
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'; H=X/'mixed-native-abc-protocol-h3-v2'
sys.path[:0]=[str(H)]
from common import RUFF,FROZEN,SONAME,env,load,dump,sha
from state import recipes,verify_view,WASM,PLAN
from witness import audit_json
from processes import parse,qualify
label,arm,kind,d,st,fixture,binding=sys.argv[1:];d=Path(d);st=Path(st);fixture=Path(fixture);binding=Path(binding);edited=label=='edit'
d.mkdir(exist_ok=False)
cfg=env();verify_view(edited,load(fixture/'manifest.json'));subj=load(binding)['arms'][arm]
assert sha(FROZEN/'bin/cargo')==subj['cargo_sha256'] and sha(FROZEN/'lib'/SONAME)==subj['driver_sha256']
known=load(st/'recorded-recipe-paths.json');before=recipes(known);args=['cargo','+ohm','build','--locked','--offline','--message-format=json']
timing=kind=='fasttrace';info=kind=='io'
if timing:prefix=['strace','--seccomp-bpf','-ff','-ttt','-qq','-s','131072','-e','trace=execve,execveat,exit_group,wait4,waitid','-e','signal=SIGCHLD','-o',str(d/'timed')]
elif info:prefix=['strace','-ff','-qq','-ttt','-s','0','-yy','-e','trace=read,pread64,readv,preadv,copy_file_range,sendfile,mmap,clone,clone3,execve,execveat','-e','signal=none','-o',str(d/'io')]
elif kind=='light':prefix=[]
else:raise ValueError(kind)
# The native command retains the registered 0-23 mask. The observer thread uses CPU 26.
assert sorted(os.sched_getaffinity(0))==list(range(24))
cfg['CARGO_LOG']='cargo::compiler=info'
stop=threading.Event()
def sample(rootpid):
    os.sched_setaffinity(0,{26})
    pbase=Path('/proc');exe_cache={};observed={}
    with gzip.open(d/'samples.jsonl.gz','wt',compresslevel=3) as f:
        while not stop.is_set():
            now=time.time_ns();desc={};stats={}
            for path in pbase.iterdir():
                if not path.name.isdigit():continue
                try:
                    fields=(path/'stat').read_text().rsplit(') ',1)[1].split();pid=int(path.name)
                    desc.setdefault(int(fields[1]),[]).append(pid);stats[pid]=fields
                except (OSError,ValueError,IndexError):continue
            todo=[rootpid];rows=[]
            while todo:
                pid=todo.pop();todo.extend(desc.get(pid,()));path=pbase/str(pid)
                try:
                    fields=stats[pid];exe=os.readlink(path/'exe');key=(pid,exe)
                    if key not in exe_cache:
                        raw=(path/'cmdline').read_bytes().split(b'\0')
                        def arg(flag):return raw[raw.index(flag)+1].decode(errors='replace') if flag in raw else None
                        name=Path(exe).name
                        desc0={'name':name,'crate':arg(b'--crate-name'),'checked':any(b'ohm-checked-mixed-rlink=' in s for s in raw),'link_only':b'link-only' in raw or b'-Zlink-only' in raw,'out':Path(arg(b'-o')).name if arg(b'-o') else None}
                        exe_cache[key]=desc0
                    ident=exe_cache[key];io={k:int(v) for k,v in (l.split(': ',1) for l in (path/'io').read_text().splitlines())}
                    rows.append([pid,int(fields[1]),int(fields[11]),int(fields[12]),int(fields[21]),int(fields[17]),io['rchar'],io['wchar'],io['read_bytes'],io['write_bytes']])
                    observed[pid]=ident
                except (OSError,ValueError,IndexError,KeyError):pass
            if rows:f.write(json.dumps([now,rows],separators=(',',':'))+'\n')
            stop.wait(.02)
    dump(d/'sampled-processes.json',observed)
def consume(src,path):
    with src,path.open('wb') as f,(path.parent/(path.name+'.clock.jsonl')).open('w') as clock:
        offset=0
        while True:
            b=os.read(src.fileno(),64*1024)
            if not b:break
            clock.write(json.dumps([offset,len(b),time.time_ns()])+'\n');f.write(b);offset+=len(b)
start=time.time_ns();tick=time.monotonic_ns()
p=subprocess.Popen([*prefix,*args],env=cfg,cwd=RUFF,stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL)
tt=[threading.Thread(target=consume,args=(p.stdout,d/'stdout')),threading.Thread(target=consume,args=(p.stderr,d/'stderr')),threading.Thread(target=sample,args=(p.pid,))]
for t in tt:t.start()
rc=p.wait();end=time.time_ns();ns=time.monotonic_ns()-tick;stop.set()
for t in tt:t.join()
dump(d/'command.json',dict(arm=arm,direction=label,probe=kind,rr=rc,started=start,ended=end,instrumented_ns=ns,argv=args,probe_argv=prefix,cargo_sha256=subj['cargo_sha256'],driver_sha256=subj['driver_sha256']))
assert rc==0,(arm,label,kind,(d/'stderr').read_text(errors='replace')[-1200:])
rows=audit_json(d/'stdout','build');assert rows['units']==501
after=recipes(known)
assert arm=='B' or before==after and len(after)==2,(arm,before,after)
dump(d/'receipts.json',dict(units=rows['units'],dirty=rows['dirty'],messages=rows['messages'],before=before,after=after,stdout_sha256=sha(d/'stdout'),stderr_sha256=sha(d/'stderr')))
if timing:
    projection=d/'projection';projection.mkdir()
    for f in d.glob('timed.*'):
        assert f.name[6:].isdigit()
        hits=[]
        for line in f.read_text(errors='replace').splitlines():
            row=re.sub(r'^\d+\.\d+\s+','',line)
            if row.startswith(('execve(','execveat(','<... execve')):hits.append(row)
        if hits:(projection/('exec.'+f.name.split('.')[-1])).write_text('\n'.join(hits)+'\n')
    trace=parse(projection,'build',before,after);qualify(trace,'build',arm,'edit');dump(d/'typed.json',trace)
