"""Read authenticated per-thread strace streams and classify complete native commands."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def string_at(line,i):
    while line[i]==" ":
        i+=1
    assert line[i]=='"'
    end=i+1
    while line[end]!='"':
        end+=2 if line[end]=="\\" else 1
    return ast.literal_eval(line[i:end+1]),end+1

def exec_argv(line):
    if line.startswith("execveat("):
        start=line.index(",")+1
    elif line.startswith("execve("):
        start=line.index("(")+1
    else:
        return None
    image,cur=string_at(line,start)
    cur=line.index("[",cur)+1
    args=[]
    while True:
        while line[cur] in " ,":cur+=1
        if line[cur]=="]":return image,args
        val,cur=string_at(line,cur);args.append(val)

def native(stage,objects):
    hs="trace-hashes.json" if objects else "exec-only-hashes.json"
    bundle="trace.tar.zst" if objects else "exec-only.tar.zst"
    want=dict(json.loads((stage/hs).read_bytes()))
    out=subprocess.Popen(["zstd","-qdc",stage/bundle],stdout=subprocess.PIPE)
    members={};commands=Counter();tools=Counter();creates=set();probes=Counter()
    all_argv=[];physical=[];object_opens={}
    with tarfile.open(fileobj=out.stdout,mode="r|") as tar:
        for node in tar:
            if node.isdir():continue
            assert node.isfile() and node.name.startswith("./exec.") and node.name[2:] not in members
            data=tar.extractfile(node).read();members[node.name[2:]]=hashlib.sha256(data).hexdigest()
            pending=None
            for orig in data.decode().splitlines():
                if not orig[:1].isdigit():continue
                _,line=orig.split(" ",1)
                if "<unfinished ...>" in line:
                    assert pending is None
                    pending=line.split("<unfinished ...>",1)[0]
                    continue
                if line.startswith("<... ") and " resumed>" in line:
                    assert pending is not None
                    line=pending+line.split(" resumed>",1)[1]
                    pending=None
                if objects and line.startswith(("openat(","creat(")) and "O_CREAT" in line and ("O_WRONLY" in line or "O_RDWR" in line) and re.search(r"= \d+$",line.rstrip()):
                    for x in re.findall(r'"([^"]+\.rcgu\.o)"',line):
                        creates.add(x)
                        object_opens.setdefault(x,[Path(x).name,hashlib.sha256(x.encode()).hexdigest(),
                                                   "O_WRONLY" if "O_WRONLY" in line else "O_RDWR","O_CREAT",int(line.rsplit("=",1)[1].strip())])
                if not line.rstrip().endswith("= 0"):continue
                rec=exec_argv(line)
                if rec is None:continue
                image,argv=rec;name=Path(image).name;crate=None;switches=[];types=[]
                if image.endswith("/rustup/toolchains/ohm/bin/rustc"):
                    if "--crate-name" not in argv:probes["version_or_other"]+=1;continue
                    krate=argv[argv.index("--crate-name")+1]
                    if krate=="___" and any(a=="--print" or a.startswith("--print=") for a in argv):probes["target_print"]+=1;continue
                    z=[a[2:] for a in argv if a.startswith("-Z") and a!="-Z"]+[argv[i+1] for i,k in enumerate(argv[:-1]) if k=="-Z"]
                    cache=any(f.split("=")[0]=="link-only" and f not in ["link-only=no","link-only=off","link-only=false"] for f in z)
                    crate=krate;switches=[s for s in z if s.split("=")[0]=="link-only"]
                    types=[argv[i+1] for i,v in enumerate(argv[:-1]) if v=="--crate-type"]+[v.split("=",1)[1] for v in argv if v.startswith("--crate-type=")]
                    commands["cached" if cache else "full",krate]+=1
                    tag="cached-rustc" if cache else "full-rustc"
                elif "wild-ld/" in image and name in ("wild","ld","ld.bfd"):tools["wild"]+=1;tag="wild"
                elif name=="collect2":tools["collect2"]+=1;tag="collect2"
                elif name in ("cc","gcc") or re.match(r".*-gcc(?:-\d+)?$",name):tools["cc_or_gcc"]+=1;tag="cc_or_gcc"
                else:continue
                checksum=hashlib.sha256(b"\0".join(a.encode() for a in [image,*argv])).hexdigest()
                all_argv.append([tag,checksum])
                physical.append([name,crate,types,switches,len(argv),checksum])
            assert pending is None,node.name
    out.stdout.close();assert out.wait()==0 and members==want
    groups={k:dict(sorted((name,n) for (mode,name),n in commands.items() if mode==k)) for k in ["full","cached"]}
    return {**groups,"tools":dict(sorted(tools.items())),"cgus_opened_for_creation":len(creates) if objects else None,
            "threads":len(members),"probes":dict(probes),"argv":sorted(all_argv),"physical_execs":sorted(physical,key=repr),
            "created_object_opens":sorted(object_opens.values()) if objects else None,"raw_trace_sha256":digest_file(stage/bundle)}
