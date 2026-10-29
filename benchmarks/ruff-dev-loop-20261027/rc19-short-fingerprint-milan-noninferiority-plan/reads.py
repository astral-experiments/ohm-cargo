"""Count real reads of regular Cargo short fingerprints in the unscored syscall census."""
import collections,gzip,hashlib,json,re,sys
from pathlib import Path
raw,out,store=map(Path,sys.argv[1:])
unfinished={}
reads=collections.defaultdict(lambda:collections.Counter())
pids=collections.Counter()
execs=[]
threadparents={}
seen=collections.Counter()
def actual_lines(stream):
    for line in stream:
        m=re.match(r"^(\d+)\s+(.*)",line.rstrip())
        if not m:continue
        pid=int(m[1]);line=m[2]
        if line.endswith("<unfinished ...>"):
            unfinished[pid]=line[:-len("<unfinished ...>")];continue
        m=re.match(r"^<\.\.\. \w+ resumed>(.*)",line)
        if m:
            line=unfinished.pop(pid,"")+m[1]
        yield pid,line
with gzip.open(raw,"rt",errors="backslashreplace") as f:
    for pid,line in actual_lines(f):
        if line.startswith("execve(") and re.search(r"\)\s+= 0$",line):
            exe=re.match(r'execve\("([^"]+)"',line)
            if exe:execs.append([pid,exe[1]])
        if line.startswith(("clone(","clone3(")) and "CLONE_THREAD" in line:
            m=re.search(r"= (\d+)$",line)
            if m:threadparents[int(m[1])]=pid
        if not line.startswith(("read(","openat(")):continue
        name=re.search(r'<(/[^<>]*?/(?:\.fingerprint|fingerprint)/[^<>]+?)>',line)
        if not name:continue
        filename=Path(name[1]);basename=filename.name
        if not filename.is_relative_to(store) or not re.fullmatch(r'(?:lib|bin|test|bench|example|build-script|run-build-script)-[\w.-]+',basename) or basename.endswith((".json",".d",".lock")):continue
        key=filename.relative_to(store).as_posix();op=line.split("(",1)[0]
        if op=="openat":
            reads[key]["opens"]+=1
        else:
            q=re.search(r', (\d+)\)\s+= (-?\d+)',line)
            if not q:continue
            request,got=map(int,q.groups())
            reads[key][f"read_{request}_returned_{got}"]+=1
            if got==16 and re.search(r'"[0-9a-f]{16}"',line):reads[key]["exact_hex16"]+=1
            seen[f"{request}:{got}"]+=1
        pids[pid]+=1
shorts={k:dict(v) for k,v in reads.items() if v["exact_hex16"]}
assert len(shorts)>0 and seen and len(execs)>=2,(len(shorts),seen,execs[:2])
summary={k:sum(v.get(k,0) for v in shorts.values()) for k in sorted({key for v in shorts.values() for key in v})}
value={"unique_hex16":len(shorts),"counts":summary,"files":shorts,"pids":pids,"execs":execs,"thread_parents":threadparents,"raw_sha256":hashlib.file_digest(raw.open("rb"),"sha256").hexdigest()}
with out.open("xb") as f:f.write(gzip.compress((json.dumps(value,sort_keys=True)+"\n").encode(),1,mtime=0))
