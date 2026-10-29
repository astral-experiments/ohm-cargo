from pathlib import Path
import ast,hashlib,json,os,re,stat,subprocess,time

def get(path):return json.loads(path.read_bytes())

def digest(value):
    if isinstance(value,bytes):return hashlib.sha256(value).hexdigest()
    with Path(value).open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()

def store(path,value):
    with path.open('x') as file:json.dump(value,file,sort_keys=True,indent=1);file.write('\n')

def sound_timing(argv,stdout,stderr,cwd,env):
    # Files and the argument vector have already been prepared.
    start=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
    while True:
        try:
            child,status=os.waitpid(proc.pid,0)
            break
        except InterruptedError:continue
    end=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    assert child==proc.pid and end>start
    proc.returncode=os.waitstatus_to_exitcode(status)
    return dict(pid=child,status=proc.returncode,started_ns=start,ended_ns=end,ns=end-start)

def inventory(root):
    rows={};seen={}
    for category in ('products','shared'):
        base=root/category
        for f in [base,*sorted(base.rglob('*'))]:
            name=str(f.relative_to(root));s=f.lstat();entry=[stat.S_IFMT(s.st_mode),s.st_mode&0o7777,s.st_mtime_ns,s.st_uid,s.st_gid]
            if stat.S_ISREG(s.st_mode):
                identity=(s.st_dev,s.st_ino);entry.extend([s.st_size,digest(f),seen.setdefault(identity,name)])
            elif stat.S_ISLNK(s.st_mode):entry.append(os.readlink(f))
            else:assert stat.S_ISDIR(s.st_mode)
            rows[name]=entry
    return rows

def scan_exec(dir):
    result=[];files={}
    for f in sorted(dir.glob('kernel.*')):
        files[f.name]=digest(f);pid=int(f.suffix[1:]);partial=None
        for line in f.read_text().splitlines():
            if line.startswith('execve(')and line.endswith('<unfinished ...>'):
                assert partial is None;partial=line.removesuffix('<unfinished ...>');continue
            if line.startswith('<... execve resumed>'):
                assert partial is not None;line=partial+line[len('<... execve resumed>'):];partial=None
            if not line.startswith('execve(')or not line.endswith('= 0'):continue
            m=re.match(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',line);assert m,line[:180]
            result.append([pid,ast.literal_eval(m[1]),ast.literal_eval(m[2])])
        assert partial is None
    return files,result
