"""One isolated restored visit. Only the measured ordinary Cargo child has stopwatch calls."""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import sys
import time

here=Path(__file__).resolve().parent
base=here.parent
out, arm, action=Path(sys.argv[1]), sys.argv[2], sys.argv[3]
subject=json.loads((here/"subjects.json").read_bytes())
oldroot=Path.home()/".cache/ohm-ruff-multi-select-20261029-v1"
p=oldroot/"pending-clock-stable-v2"

def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def write(path, obj):
    data=(json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()
    if path.suffix==".gz": data=gzip.compress(data,1,mtime=0)
    with path.open("xb") as f: f.write(data)

assert sha(p/"clock_common_idempotent.py")==subject["base_helper"]
assert sha(oldroot/"ops/common.py")==subject["ops_helper"]
assert sha(oldroot/"ops/trace.py")==subject["process_tracer"]
h=runpy.run_path(str(p/"clock_common_idempotent.py"))
names=("work","store","sdk","slot","rustup","proxy","stable_git","write_source","source","source_times","environment","inventory","canonical_states","space")
work,store,sdk,slot,rustup,proxy,stable_git,write_source,source,source_times,environment,inventory,canonical_states,space=map(h.__getitem__,names)
source_name=json.loads((out/"case.json").read_bytes())["source"]
spec=subject["sources"][source_name]
donor_path=p/"accepted-common-B"/(source_name+".json")
assert sha(donor_path)==spec["descriptor"]
donor=json.loads(donor_path.read_bytes())
assert donor["state"]==spec["state"] and donor["revision"]==spec["revision"]
revision=donor["revision"]
held=p/"physical-common"/("B-after-common-"+source_name+".json")
assert sha(held)==spec["products597"]
gold=json.loads(held.read_bytes()); assert len(gold)==597
assert arm in ("B","E") and action in ("inspect","qualify","holdout","measure")
assert os.geteuid()!=0 and Path("/").stat().st_uid==Path("/home").stat().st_uid==0
world=Path("/proc/self/uid_map").read_text().split()
assert world==["0","0","4294967295"]
assert slot.resolve()==slot and os.path.samefile(slot,base/"images"/arm/"cargo")
assert sha(slot)==subject["images"][arm]["binary"]
assert (os.statvfs(slot).f_flag & os.ST_RDONLY) and os.statvfs(rustup).f_flag & os.ST_RDONLY
assert os.path.samefile(store,base/"restore/active")
assert (Path("/proc/self/mountinfo").read_text().count(" - overlay ")>=2)
h["canonical_states"]();h["identity"](work,h["repo"]/".git")
os.sched_setaffinity(0,range(8));assert sorted(os.sched_getaffinity(0))==h["cpus"]()==list(range(8))
old_admin=stable_git()
env=environment()
assert not {"RUSTFLAGS","RUSTC","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","CARGO_LOG","LD_PRELOAD"} & env.keys()
assert all(v.stat().st_uid==os.geteuid() for v in (work,Path(env["CARGO_HOME"]),store,store/"target",store/"shared"))
cmd=[str(proxy),"+ohm","check","--workspace","--locked","--offline","-j8","--message-format=json"]
write(out/"namespace.json",{"uid":os.geteuid(),"uid_map":world,"affinity":sorted(os.sched_getaffinity(0)),
      "owners":{n:[f.stat().st_uid,f.stat().st_gid,f.stat().st_mode] for n,f in (("root",Path("/")),("home",Path("/home")),("work",work),("cargo_home",Path(env["CARGO_HOME"])),("state",store))},
      "cargo":sha(slot),"argv":cmd,"environment":env,"initial_floors":space(),"parent_namespace":os.readlink("/proc/self/ns/mnt")})
write_source(revision,donor["source_times"])
assert inventory(store)==donor["state"]
assert source_times()==donor["source_times"] and stable_git()==old_admin
def products(folder, label, targets=None):
    targets=sorted(gold if targets is None else targets)
    actual={}
    for name in targets:
        path=store/name
        assert not Path(name).is_absolute() and path.resolve().is_relative_to(store)
        s=path.stat(); actual[name]=[s.st_size,sha(path)]
    differences={name:{"expected":gold.get(name),"actual":actual.get(name)} for name in sorted(set(gold)|set(actual)) if gold.get(name)!=actual.get(name)}
    write(folder/(label+"-597.json.gz"),{"files":actual,"different":differences})
    assert len(actual)==597 and not differences,(label,len(differences),list(differences)[:12])
products(out,"start")
old_settled=p/"qualification"/("B-"+("child-to-parent" if source_name=="parent" else "parent-to-child"))/"settled/cargo.jsonl"
def unitkey(row):
    t=row["target"]
    return json.dumps([row["package_id"],t["name"],t["kind"],t["crate_types"],t["test"],t["doctest"],row["features"],row["profile"]],sort_keys=True,separators=(",",":"))
def parse_ordinary(log):
    rows=[json.loads(line) for line in log.read_bytes().splitlines()]
    assert rows[-1]=={"reason":"build-finished","success":True}
    arts=[r for r in rows if r["reason"]=="compiler-artifact"]
    names={Path(v).relative_to(store).as_posix() for a in arts for v in a["filenames"]}
    dirty=sorted(unitkey(a) for a in arts if not a["fresh"])
    identity=hashlib.sha256("\n".join(sorted(unitkey(a) for a in arts)).encode()).hexdigest()
    diagnostics=sorted(json.dumps([a["package_id"],a["target"]["name"],a["message"]],sort_keys=True,separators=(",",":")) for a in rows if a["reason"]=="compiler-message")
    return (len(arts),identity,dirty,diagnostics),names
expected,expected_names=parse_ordinary(old_settled)
assert expected[0]==510 and expected[1]==spec["identity"] and len(expected[2])==12 and expected_names==set(gold)

def ordinary(label, prefix=(), timed=False):
    dest=out/label;dest.mkdir();source(revision);assert stable_git()==old_admin;space()
    assert not timed or (label=="check" and action=="measure" and not prefix)
    with (dest/"cargo.jsonl").open("xb") as stdout,(dest/"stderr").open("xb") as stderr:
        if timed: before=time.monotonic_ns()
        process=subprocess.run([*prefix,*cmd],cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=360)
        if timed: after=time.monotonic_ns()
    write(dest/"exit.json",{"status":process.returncode})
    if timed: write(dest/"wall.json",{"before_ns":before,"after_ns":after,"wall_ns":after-before,"status":process.returncode})
    assert process.returncode==0,(out.name,label)
    actual,files=parse_ordinary(dest/"cargo.jsonl");write(dest/"typed.json.gz",{"inventory":actual,"files":sorted(files)})
    assert actual==expected and files==expected_names,(label,actual[:2],len(actual[2]),len(actual[3]),len(files))
    products(dest,"after",files)
    source(revision);assert stable_git()==old_admin and source_times()==donor["source_times"]
    write(dest/"receipt.json",{"units":actual[0],"typed":actual[1],"dirty":len(actual[2]),"diagnostics":len(actual[3]),
          "products":sha(dest/"after-597.json.gz"),"json":sha(dest/"cargo.jsonl"),"stderr":sha(dest/"stderr"),"space":space()})

def traces():
    config=json.loads((oldroot/"reports/qualified-rc19/images.json").read_bytes())
    config["images"]["cargo"]={"path":str(slot),"sha256":sha(slot)}
    config_path=out/"images.json";write(config_path,config)
    ordinary("native",prefix=[sys.executable,"-IB",str(oldroot/"ops/trace.py"),str(out/"native.json"),str(config_path)])
    record=json.loads((out/"native.json").read_bytes());assert record["root_exit"]==0 and set(record["process_exit"].values())=={0}
    events=record["events"];roles=collections.Counter(e["role"] for e in events)
    assert roles=={"cargo":1,"rustc-full":1} and [e["target"] for e in events if e["role"]=="rustc-full"]==["ty_python_semantic"],roles
    log=out/"fingerprints.strace.gz"
    ordinary("reads",prefix=["strace","-f","-qq","-yy","-s","160","-e","trace=clone,clone3,fork,vfork,execve,openat,read,close","-o","|gzip -1 > "+shlex.quote(str(log)),"--"])
    bound=Path(__file__).with_name("reads.py")
    subprocess.run([sys.executable,"-IB",str(bound),str(log),str(out/"reads.json.gz"),str(store)],check=True)
    write(out/"native-result.json",{"roles":dict(roles),"argv":[e["argv_sha256"] for e in events],"native":sha(out/"native.json"),"reads":sha(out/"reads.json.gz"),"raw_reads":sha(log)})

def holdout():
    producer=work/"crates/ruff_python_ast/src/token.rs";consumer=work/"crates/ruff_python_index/src/multiline_ranges.rs"
    ps,cs=producer.stat(),consumer.stat();original=producer.read_bytes();using=consumer.read_bytes()
    needle=b"    pub fn is_triple_quoted_string(self) -> bool {"
    assert original.count(needle)==1
    scoped=[str(proxy),"+ohm","check","-p","ruff_python_index","--keep-going","--locked","--offline","-j8","--message-format=json"]
    prior=oldroot/"pending-metadata/ruff-release-api-control-v1/done.json"
    reference=json.loads(prior.read_bytes())["errors"]
    def invoke(label,bad):
        dest=out/label;dest.mkdir();space()
        with (dest/"cargo.jsonl").open("xb") as stdout,(dest/"stderr").open("xb") as stderr:
            f=subprocess.run(scoped,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=360)
        rows=[json.loads(l) for l in (dest/"cargo.jsonl").read_bytes().splitlines()];errors=[]
        for a in rows:
            if a.get("reason")=="compiler-message" and a["message"]["level"]=="error":
                m=a["message"];errors.append([a["target"]["name"],(m.get("code") or {}).get("code"),m["message"],
                    sorted([s["file_name"],s["line_start"],s["column_start"],s["line_end"],s["column_end"]] for s in m["spans"] if s["is_primary"])])
        write(dest/"verdict.json",{"status":f.returncode,"errors":sorted(errors),"reference":sha(prior)})
        assert f.returncode==(101 if bad else 0) and rows[-1]=={"reason":"build-finished","success":not bad} and sorted(errors)==(reference if bad else [])
    assert source_name=="child"
    try:
        producer.write_bytes(original.replace(needle,needle.replace(b"pub fn",b"pub(crate) fn")))
        consumer.write_bytes(using+b"\n// Recheck this consumer alongside its provider.\n")
        invoke("real-private-error",True);invoke("unchanged-error",True)
    finally:
        producer.write_bytes(original);consumer.write_bytes(using)
        os.utime(producer,ns=(ps.st_atime_ns,ps.st_mtime_ns));os.utime(consumer,ns=(cs.st_atime_ns,cs.st_mtime_ns))
    invoke("recovered",False)

if action!="inspect": ordinary("warmup")
if action=="measure": ordinary("check",timed=True)
elif action=="qualify": traces()
elif action=="holdout": holdout()
write(out/"terminal.json",{"success":True,"arm":arm,"source":source_name,"action":action,"admin_unchanged":stable_git()==old_admin,"source_ok":source(revision) is None})
