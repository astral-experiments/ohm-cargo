"""Summarize file-level work without retaining regular read/write buffers."""
import collections,hashlib,json,os,re
from pathlib import Path
C=collections.Counter
O=Path.home()/".cache/ohm-ruff-18-fresh-prep-linkscout-20261028"
B=Path.home()/".cache/ohm-ty-vendored-watch-20261028-v1"
Q={}
def norm(n):return n.replace(str(B),"<B>").replace(str(Path.home()),"<home>")
def family(n):
    parts=Path(n).parts;name=Path(n).name
    if ".ohm-worktree-seed-" in name:return "policy-marker"
    if name==".ohm-worktree-result-v1":return "script-result"
    if name=="zipped_typeshed.zip":return "typeshed-zip"
    if name in ("root-output","output","stdout","root","stderr","root_output") and "build" in parts:return "script-output"
    if "fingerprint" in parts or ".fingerprint" in parts:return "fingerprint"
    if name=="Cargo.toml":return "manifest"
    if name in ("Cargo.lock",".cargo-checksum.json","config.toml",".cargo-checksum-files-v1","config","index"):return name
    if ".rlib" in name or ".rmeta" in name or name.endswith((".o",".a",".so")):return "archive-object"
    if str(B/"home") in n:return "registry-other"
    if str(B/"checkout") in n:return "source-other"
    if str(B/"target") in n or str(B/"shared") in n:return "build-other"
    return "other"
for label in ("fs1","fs2"):
    fs=sorted((O/"logs"/label).glob("trace.*"));type_count=C();types={};ro=C();rb=C();rd=C();stats=C();link=C();opened=C();statnames=C();marker=C();calls=collections.defaultdict(C);timings=collections.defaultdict(int);execs=[];miss=C();fail=C()
    file_lines={};cmeta=collections.defaultdict(list)
    for f in fs:
        raw=f.read_bytes();file_lines[f.name]=hashlib.sha256(raw).hexdigest()
        for l in raw.decode(errors="surrogateescape").splitlines():
            m=re.match(r"([a-z0-9_]+)\(",l)
            if not m:continue
            op=m[1];type_count[op]+=1
            result=re.search(r"\)\s+= (-?\d+)(?:<[^>]*>)?(?: [^<]*)? <([0-9.]+)>$",l)
            if not result:continue
            rv=int(result[1]);us=round(float(result[2])*1e6)
            if op in ("read","pread64","write","fchmod","close","getdents64"):
                r=re.match(r'[^\(]+\(\d+<([^>]+)>',l); n=r[1] if r else ""
            else:
                ss=re.findall(r'"([^"]*)"',l)
                n=ss[0] if ss else ""
                if n and not n.startswith("/") and (r:=re.match(r"[^(]+\((?:AT_FDCWD|\d+)<([^>]+)>",l)):n=str(Path(r[1])/n)
                if op=="openat" and rv>=0 and (r:=re.search(r"= \d+<([^>]+)>",l)):n=r[1]
                if op in ("rename","renameat","renameat2") and ss:n=ss[-1]
            if not n:continue
            fam=family(n);k=norm(n)
            calls[fam][op]+=1;timings[fam]+=us
            if fam=="policy-marker":marker[op]+=1
            if op=="execve":execs.append(k)
            if rv<0:fail[op]+=1;miss[(op,k)]+=1
            elif op in ("statx","newfstatat","lstat","stat"):
                stats[k]+=1;statnames[Path(k).name]+=1
            elif op=="readlink":link[k]+=1
            elif op=="openat":opened[k]+=1
            elif op in ("read","pread64") and rv>0:
                rb[k]+=rv;rd[k]+=1
                if fam in ("script-output","typeshed-zip"):cmeta[k].append(rv)
            if rv>=0 and op in ("read","pread64") and rv==0:ro[k]+=1
    paths={k:{"family":family(k.replace("<B>",str(B))),"opens":opened[k],"reads":rd[k],"bytes":v,"eof":ro[k],"stat":stats[k],"read_sizes":dict(C(cmeta[k]))if k in cmeta else None}for k,v in rb.items()}
    for k,n in opened.items():
        if k not in paths and family(k.replace("<B>",str(B)))in ("script-output","typeshed-zip","policy-marker"):paths[k]={"family":family(k.replace("<B>",str(B))),"opens":n,"reads":0,"bytes":0,"eof":ro[k],"stat":stats[k],"read_sizes":None}
    q={"syscall_count":type_count,"named_syscalls":{k:dict(v)for k,v in calls.items()},"marker":marker,"all_read_bytes":sum(rb.values()),"failed_calls":fail,"roles":execs,"trace_sha256":file_lines,"profiled_syscall_microseconds":timings,"reads":paths,"top_stat":[[k,n]for k,n in stats.most_common(28)],"top_missing":[[op,k,n]for (op,k),n in miss.most_common(30)],"top_basenames":statnames.most_common(24)}
    Q[label]=q
print(json.dumps(Q,sort_keys=True,indent=2))
