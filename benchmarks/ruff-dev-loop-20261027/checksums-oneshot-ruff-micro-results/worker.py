"""Bind and audit the actual local ELF, then run the separately released instruction series."""
import argparse, ctypes, ctypes.util, fcntl, gzip, hashlib, json, os, platform, re, shutil, stat, subprocess as sp, sys
from pathlib import Path

SOURCE_COMMIT="32c4f9da05956359fbd8d660c712c846fd8ff01f"
SOURCE_MANIFEST="b8a8c4156519267acd6247adb582b160328b3107c8f8e9e2f805a5975495e42f"
W=Path("/dev/shm/ohm-262-blake3-screen-20261028")
D=Path("/home/dev-user/.cache/ohm-dynamorio-20261026")
ELF=W/"target/release/ohm-checksum-isolated"
CORPUS=W/"corpus"
ST=Path("/usr/bin/strace")
CC=Path("/usr/bin/cc")
DR=D/"sdk/bin64/drrun"
CLIENT=D/"client/libpidcounter.so"
CPU=14
NATIVE_ENV={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","TZ":"UTC","HOME":"/home/dev-user"}
NATIVE=W/"host-native-v1"
SCORE=W/"score-v1"
def dec(p): return json.loads(Path(p).read_bytes())
def raw_json(obj): return (json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
def save(p,obj): p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def h(data): return hashlib.sha256(data).hexdigest()
def sha(p): return h(p.read_bytes())
def stamp(p):
    s=p.stat()
    return [s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def freeze(p): return {"physical":str(p.resolve()),"stamp":stamp(p),"sha256":sha(p)}
def proc_text(path): return Path(path).read_text().strip()
def capture(cmd):return sp.check_output(cmd,env=NATIVE_ENV,cwd=W,text=True)
def inputs(src,full=True):
    desc=gzip.decompress((src/"corpus.json.gz").read_bytes()); plan=dec(src/"screen-plan.json")
    assert h(desc)==plan["corpus"]
    rows=json.loads(desc)["actual_inputs"]
    assert set(p.name for p in CORPUS.iterdir())=={str(i) for i in range(len(rows))} and len(rows)==1238
    entries=[]
    for i,r in enumerate(rows):
        p=CORPUS/str(i);s=stamp(p)
        assert s[3]==r["size"] and p.is_file() and not p.is_symlink() and i==r["file"]
        if full: assert sha(p)==r["sha256"] and sha(W/"recreated-from-portable"/str(i))==r["sha256"]
        entries.append(s)
    return rows,entries

def check_source(src):
    assert sha(src/"SHA256SUMS")==SOURCE_MANIFEST
    for line in (src/"SHA256SUMS").read_text().splitlines():
        expected,rel=line.split("  ",1); assert sha(src/rel)==expected
    return dec(src/"screen-plan.json")

def host(src):
    plan=check_source(src)
    assert sha(ELF)==plan["harness"]
    assert sha(DR)==plan["counter"]["drrun"] and sha(CLIENT)==plan["counter"]["client"]
    paths=[ELF,DR,D/"sdk/lib64/release/libdynamorio.so", D/"sdk/lib64/release/libdrpreload.so", CLIENT,
           D/"sdk/ext/lib64/release/libdrmgr.so", D/"sdk/ext/lib64/release/libdrreg.so"]+[Path(k) for k in plan["known_loaded_native"]]
    assert sha(paths[2])==plan["counter"]["libdynamorio"]
    assert all(sha(Path(k))==v for k,v in plan["known_loaded_native"].items())
    search=D/"client/libpidcounter.so.drpath"
    assert search.read_text().strip()==str(D/"sdk/ext/lib64/release")
    byname={p.name:p for p in paths}
    elfs={}
    for p in paths:
        tags=re.findall(r"\(NEEDED\).*?\[(.*?)\]",capture(["/usr/bin/readelf","-dW",p]))
        elfs[str(p)]={**freeze(p),"needed":{x:str(byname[x]) for x in tags}}
    elfs[str(search)]={**freeze(search),"text":search.read_text()}
    observed=sorted(os.sched_getaffinity(0)); assert observed==[CPU]
    assert platform.node()=="charlie-oss-8" and proc_text("/proc/sys/kernel/random/boot_id")=="b343f54a-aec6-413e-925d-e1a7c2268c56"
    assert proc_text(f"/sys/devices/system/cpu/cpu{CPU}/topology/thread_siblings_list")==str(CPU)
    return dict(source_commit=SOURCE_COMMIT,source_manifest=SOURCE_MANIFEST,plan=sha(src/"screen-plan.json"),environment=NATIVE_ENV,
                host=platform.node(),boot=proc_text("/proc/sys/kernel/random/boot_id"),kernel=platform.release(),machine=platform.machine(),
                cpu_model=next(x.split(":",1)[1].strip() for x in proc_text("/proc/cpuinfo").splitlines() if x.startswith("model name")),
                cpu_topology=capture(["/usr/bin/lscpu","-p=cpu,core,socket,node"]),core=CPU,siblings=[CPU],elf_paths=elfs,
                strace=freeze(ST),cwd=str(W),corpus=str(CORPUS),source_sweep=plan["corpus"],source_count=plan["files_per_sweep"],
                expected_stdout=plan["expected_stdout"],work_sha256=sha(Path(__file__)))
def bytes_cmd(d,cmd):
    d.mkdir();save(d/"invocation.json",dict(argv=list(map(str,cmd)),cwd=str(W),environment=NATIVE_ENV,affinity=sorted(os.sched_getaffinity(0))))
    with (d/"stdout").open("wb") as fo,(d/"stderr").open("wb") as fe:
        p=sp.Popen(cmd,cwd=W,env=NATIVE_ENV,stdout=fo,stderr=fe);rc=p.wait()
    save(d/"status.json",dict(pid=p.pid,rc=rc));assert rc==0,(d,rc)
    assert (d/"stderr").stat().st_size==0,(d,(d/"stderr").read_bytes()[-400:])
    return (d/"stdout").read_bytes()

def read_records(raw,binpath,corpus_path,sizes):
    """Reconstruct ordered open/read/EOF/close matches on a single real descriptor."""
    seq=[];active={};roster=[]
    numpath=re.escape(str(corpus_path))+r"/(\d+)"
    opened=re.compile(r'^openat\(.*?, "'+numpath+r'", O_RDONLY\|O_CLOEXEC\)\s+= (\d+)<'+numpath+r'>$')
    read=re.compile(r'^read\((\d+)<'+numpath+r'>, .*, (\d+)\)\s+= (\d+)$')
    closed=re.compile(r'^close\((\d+)<'+numpath+r'>\)\s+= 0$')
    for ln in raw.decode().splitlines():
        if ln.startswith("execve("):
            m=re.match(r'^execve\("([^"]+)".*\)\s+= 0$',ln);assert m,ln;roster.append(m[1])
        if m:=opened.match(ln):
            i,fd,i2=map(int,m.groups());assert i==i2==len(seq)%len(sizes) and fd not in active and not active
            active[fd]=(i,[]);continue
        if m:=read.match(ln):
            fd,i,n,ret=map(int,m.groups());assert fd in active and i==active[fd][0]
            active[fd][1].append((n,ret));continue
        if m:=closed.match(ln):
            fd,i=map(int,m.groups());seen,reads=active.pop(fd);assert i==seen
            size=sizes[i];q,r=divmod(size,65536)
            expected=[(65536,65536)]*q+([(65536,r)] if r else [])+[(65536,0)]
            assert reads==expected,(i,size,reads)
            seq.append([i,fd,reads]);continue
        if re.search(numpath+r'(?:>|")',ln): raise AssertionError(ln)
    assert not active and len(seq)==len(sizes)*4 and roster==[str(binpath)],(len(seq),roster)
    return seq

def reference(d,src,rows):
    # Independent portable C, not Rust crate SIMD, and stock Python's SHA implementation.
    cdir=W/"vendor/blake3-1.8.5/c";so=d/"reference.so"
    cfiles=[cdir/f for f in ["blake3.c","blake3_dispatch.c","blake3_portable.c"]]
    headers=[cdir/f for f in ["blake3.h","blake3_impl.h"]]
    argv=[CC,"-O2","-fPIC","-shared","-DBLAKE3_NO_SSE2","-DBLAKE3_NO_SSE41","-DBLAKE3_NO_AVX2","-DBLAKE3_NO_AVX512","-o",so,*cfiles]
    bytes_cmd(d/"reference-build",argv)
    lib=ctypes.CDLL(str(so)); size=ctypes.c_size_t;ptr=ctypes.c_void_p
    lib.blake3_hasher_init.argtypes=[ptr];lib.blake3_hasher_update.argtypes=[ptr,ptr,size];lib.blake3_hasher_finalize.argtypes=[ptr,ptr,size]
    def c_hash(x):
        obj=ctypes.create_string_buffer(4096);out=ctypes.create_string_buffer(32)
        lib.blake3_hasher_init(obj);lib.blake3_hasher_update(obj,x,len(x));lib.blake3_hasher_finalize(obj,out,32);return out.raw
    b=[];s=[]
    for r in rows:
        v=(CORPUS/str(r["file"])).read_bytes();b.append(c_hash(v));s.append(hashlib.sha256(v).digest())
    oracle=dec(src/"oracle.json")
    result=dict(c_arbitrary_per_file_then_over_ledger=c_hash(b"".join(b)).hex(),four_sweeps=c_hash(b"".join(b)*4).hex(),sha_over_ledger=h(b"".join(s)),
                compiler=freeze(CC),files={p.name:sha(p) for p in cfiles+headers},library=freeze(so),prior_c_library=oracle["foreign_c_library_sha"])
    assert result["c_arbitrary_per_file_then_over_ledger"]==oracle["blake3_c_reference"] and result["sha_over_ledger"]==oracle["sha256_python_reference"]
    assert result["four_sweeps"]==dec(src/"screen-plan.json")["expected_stdout"]
    save(d/"references.json",result)

def replay(arm):return [ELF,arm,CORPUS,"4"]
def native(src):
    d=NATIVE;d.mkdir(mode=0o700)
    save(d/"host.json",host(src));rows,stamps=inputs(src);(d/"input-identity.json.gz").write_bytes(gzip.compress(raw_json(stamps),mtime=0))
    reference(d,src,rows);expected=(dec(src/"screen-plan.json")["expected_stdout"]+"\n").encode()
    (d/"mutable-tests").mkdir();assert bytes_cmd(d/"functional",[ELF,"check",CORPUS,d/"mutable-tests"])==(src/"correctness.stdout").read_bytes()
    assert bytes_cmd(d/"packet",[ELF,"packet-witness",CORPUS])==(src/"packet-v2.stdout").read_bytes()
    audit={};both=[]
    for arm in ("before","after"):
        assert bytes_cmd(d/("ordinary-"+arm),replay(arm))==expected
        t=d/("trace-"+arm)
        args=[ST,"-ff","-qq","-yy","-s","0","-e","trace=execve,openat,read,close","-o",t/"syscalls",*replay(arm)]
        assert bytes_cmd(t,args)==expected
        f,=t.glob("syscalls.*");raw=f.read_bytes()
        seq=read_records(raw,ELF,CORPUS,[r["size"] for r in rows]);payload=raw_json(seq);both.append(h(payload))
        (t/"raw.txt.gz").write_bytes(gzip.compress(raw,mtime=0));(t/"reads.json.gz").write_bytes(gzip.compress(payload,mtime=0))
        audit[arm]=dict(pid=int(f.suffix[1:]),opens=len(seq),bytes=sum(ret for _,_,reads in seq for _,ret in reads),
                        reads=sum(len(reads) for _,_,reads in seq),eofs=sum(ret==0 for _,_,reads in seq for _,ret in reads),
                        execs=1,sha_raw=h(raw),sha_reads=h(payload))
    assert both[0]==both[1] and inputs(src)[1]==stamps
    save(d/"admission.json",dict(raw=audit,positive=both[0],host=sha(d/"host.json"),native_scores=0,inputs=sha(d/"input-identity.json.gz"),
                                 source_commit=SOURCE_COMMIT,proof="Same full-size requests and returned bytes including EOF and successful close in each of 4952 file opens per arm."))
    return audit

def counter(f,pid):
    rec=[q.split() for q in f.read_text().splitlines()]
    assert [r[0] for r in rec]==["B","T","F","P"] and all(int(r[1])==pid for r in rec),rec
    assert int(rec[1][2])==int(rec[2][2])==pid and len(rec[2])==4 and int(rec[2][3])>0
    return int(rec[2][3])
def score(src,grant):
    assert grant and grant.is_file(),"A separate explicit score grant is mandatory"
    g=dec(grant);assert g["release"]=="score-local-12" and g["native"]==sha(NATIVE/"admission.json") and g["host"]==sha(NATIVE/"host.json")
    plan=check_source(src);assert host(src)==dec(NATIVE/"host.json")
    stamps=json.loads(gzip.decompress((NATIVE/"input-identity.json.gz").read_bytes()));assert inputs(src)[1]==stamps
    SCORE.mkdir(mode=0o700);save(SCORE/"grant.json",g);expected=(plan["expected_stdout"]+"\n").encode()
    scores=[]
    for pair,order in enumerate(plan["orders"]):
        for slot,arm in enumerate(order):
            assert inputs(src,False)[1]==stamps and host(src)==dec(NATIVE/"host.json")
            dest=SCORE/f"{pair:02d}-{slot}-{arm}";out=dest/"pid.count"
            av=[DR,"-quiet","-no_follow_children","-c",CLIENT,out,"--",*replay(arm)]
            assert bytes_cmd(dest,av)==expected
            ir=counter(out,dec(dest/"status.json")["pid"])
            scores.append(dict(arm=arm,pair=pair,slot=slot,ir=ir,count_sha256=sha(out),stdout_sha256=sha(dest/"stdout")))
            save(SCORE/"rows.json",scores)
    for arm in ("before","after"):assert bytes_cmd(SCORE/("post-native-"+arm),replay(arm))==expected
    assert inputs(src)[1]==stamps and host(src)==dec(NATIVE/"host.json")
    result=sp.check_output([sys.executable,"-B",src/"analyze.py",SCORE/"rows.json"],env=NATIVE_ENV)
    (SCORE/"result.json").write_bytes(result);return json.loads(result)
if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("phase",choices=["native","score"]);cli.add_argument("src",type=Path);cli.add_argument("--grant",type=Path)
    args=cli.parse_args();os.sched_setaffinity(0,{CPU})
    with (W/"bound-cpu14.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print(json.dumps(native(args.src) if args.phase=="native" else score(args.src,args.grant),indent=2))
