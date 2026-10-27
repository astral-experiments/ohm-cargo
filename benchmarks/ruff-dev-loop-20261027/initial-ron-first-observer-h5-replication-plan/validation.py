"""Run the fixed H4 release schedule only after the exact arm qualification and binding grant."""
from pathlib import Path
import csv,fcntl,hashlib,json,os,re,shutil,socket,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import qualification as workload

here=Path(__file__).resolve().parent;p=workload.p;q=workload.q;root=workload.r;plan=workload.load(here/"plan.json")
def write(path,data):path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def verify_hardware():
    assert socket.gethostname()=="charlie-ohm-loader-perf-1024" and os.cpu_count()==32 and set(range(24))<=os.sched_getaffinity(0)
    cpu=next(l.split(":",1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines() if l.startswith("model name"))
    assert "AMD EPYC" in cpu
    dev=os.stat(p).st_dev
    assert dev==os.stat(root/"states").st_dev==os.stat(root/"results").st_dev and dev!=os.stat(Path.home()).st_dev
    workload.floors(16<<30)
    other=[]
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():continue
        try:
            cmd=(d/"comm").read_text().strip()
            if cmd in ("cargo","rustc","llvm-bolt","wild","wild-ld"):other.append([int(d.name),cmd])
        except (OSError,UnicodeError):pass
    assert not other,("outside compiler/linker work",other)
    return {"host":socket.gethostname(),"kernel":os.uname().release,"cpu":cpu,"device":dev,"boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),"load":os.getloadavg(),"free_bytes":shutil.disk_usage(p).free}
def audit_receipts(state,dest,arm):
    def physical(pth):
        path=Path(pth.replace("\\ "," "))
        if not path.is_absolute():return workload.WT/path
        for canon,real in ((workload.TARGET,state/"target"),(workload.BUILD,state/"build"),(workload.CH,state/"home"),(workload.p/"rustup/toolchains/ohm",workload.FROZEN)):
            if path.is_relative_to(canon):return real/path.relative_to(canon)
        assert path.is_relative_to(workload.FROZEN) or path.is_relative_to(workload.WT),path;return path
    executable=q/"blake3-file";out={}
    for phase in ("cold","first","settled"):
        base=dest/phase;cache=base/"ron";encoded=cache/"dep-lib-ron";info,=cache.glob("ron-*.d")
        raw=encoded.read_bytes();assert raw[-41:-37]==b"OBS1" and len(raw)>41;sigfile=base/"covered-observer.record"
        if sigfile.exists():assert sigfile.read_bytes()==raw[:-32]
        else:
            with sigfile.open("xb") as fp:fp.write(raw[:-32])
        signed=subprocess.check_output([executable,sigfile],text=True).strip()
        assert signed==raw[-32:].hex() and bool(raw[-33])==(phase!="cold" or arm=="C")
        rows=[]
        for s in info.read_text().splitlines():
            if not s.startswith("# checksum:"):continue
            m=re.fullmatch(r"# checksum:(blake3|sha256)=([0-9a-f]{64}) file_len:(\d+) (.+)",s);assert m,s
            f=physical(m[4]);assert f.stat().st_size==int(m[3]),f
            actual=sha(f) if m[1]=="sha256" else subprocess.check_output([executable,f],text=True).strip()
            assert actual==m[2],f;rows.append([workload.relocate(m[4]),m[1],actual,int(m[3])])
        assert len(rows)==(0 if phase=="cold" and arm!="C" else 45)
        out[phase]={"seal_blake3":signed,"encoded_sha256":sha(encoded),"depinfo_sha256":sha(info),"physical_inputs":rows}
    saved=dest/"proof-validation.json"
    if saved.exists():assert workload.load(saved)==out
    else:write(saved,out)
def retire_private(st,dest):
    assert st.resolve().parent==(root/"states").resolve() and dest.resolve().parent==(root/"results").resolve() and st.name==dest.name and st.name.startswith("score-")
    assert not st.is_symlink() and (dest/"complete.json").is_file() and (dest/"proof-validation.json").is_file()
    assert all(sha(dest/phase/"native.json")==workload.load(dest/"complete.json")["phases"][phase]["native"] for phase in ("cold","first","settled"))
    mounts=[Path(line.split()[4]) for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    assert all(not entry.is_relative_to(st) for entry in mounts)
    shutil.rmtree(st)
def same_subject_oracles(actual,reference):
    differences={}
    for phase in ("cold","first","settled"):
        a=workload.load(actual/phase/"native.json");b=workload.load(reference/phase/"native.json");assert a.keys()==b.keys() and len(a)==110
        changed=[]
        for path in a:
            if a[path]==b[path]:continue
            x,y=a[path],b[path]
            assert x["bytes"]==y["bytes"] and x["except_registered_wild_fields"]==y["except_registered_wild_fields"] and {x["rodata_entsize"],y["rodata_entsize"]}<={0,8},("independent same-subject output",phase,path,x,y)
            changed.append(path)
        differences[phase]=sorted(changed)
    return differences
