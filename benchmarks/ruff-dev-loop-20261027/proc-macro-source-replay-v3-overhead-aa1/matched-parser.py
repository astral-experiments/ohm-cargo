"""Matched real Ruff parser child, including its ordinary native code generation. No full Cargo timings."""
from pathlib import Path
import argparse, fcntl, gzip, hashlib, json, os, re, resource, shutil, struct, subprocess, sys, tempfile, time

ap=argparse.ArgumentParser();ap.add_argument("phase",choices=["qualify","score"]);ap.add_argument("--binding")
args=ap.parse_args()
X=Path.home()/".cache/ohm-233-position-qualified-20261027";W=X/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(W))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,sha,load,dump,env
from namespace import skeleton,spawn_args
from state import source_binds,source_clean,gate_free
S=Path(__file__).parent; J=P/"mixed-registry-only-pilot";O=J/"scoped-parser-overhead-v3-r2";G=J/"fixed-source-ruff-v3"
planpath=S/"parser-overhead-v3-plan.json";plan=load(planpath)
train=G/"state/training";edited=G/"state/warm"
rs=load(G/"results.json"); argv=rs["warm"]["parser"];md=Path(rs["warm"]["rmeta"]);outdir=Path(argv[argv.index("--out-dir")+1])
inc,=[Path(s.removeprefix("incremental=")) for s in argv if s.startswith("incremental=")]
cfg=env();cfg["PATH"]=load(J/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
subjects={"parent":X/("drivers/driver-"+plan["arms"]["parent"]["driver_sha256"]),"candidate":P/"parse-source-replay-v3/candidate-driver.so"}
cargo=Path(load(G/"subject.json")["cargo"]);assert sha(cargo)==plan["cargo_sha256"]
for arm,f in subjects.items():assert sha(f)==plan["arms"][arm]["driver_sha256"]
fnts=sorted(os.sched_getaffinity(0));assert fnts==list(range(24)) and sha(FROZEN/"bin/rustc")==plan["frontend_sha256"]
def physical(logical):
    for root,sub in [(TARGET,"target"),(SHARED,"shared")]:
        if logical.is_relative_to(root):return train/sub/logical.relative_to(root)
    return logical
assert argv==rs["empty"]["parser"]
depfile,=physical(md).parent.glob("ruff_python_parser-*.d")
depsenv={s[10:].split("=",1)[0]:s[10:].split("=",1)[1] for s in depfile.read_text().splitlines() if s.startswith("# env-dep:") and "=" in s}
cfg.update(depsenv)
driver_name="librustc_driver-774a793a844d5500.so"
def elf_meta(shell):
    assert shell[:6]==b"\x7fELF\x02\x01"
    at=struct.unpack_from("<Q",shell,40)[0];size,n,si=struct.unpack_from("<HHH",shell,58)
    def info(k):return struct.unpack_from("<IIQQQQIIQQ",shell,at+size*k)
    s=info(si);names=shell[s[4]:s[4]+s[5]]
    for i in range(n):
        h=info(i)
        if names[h[0]:].split(b"\x00",1)[0]==b".rmeta":return shell[h[4]:h[4]+h[5]]
    raise ValueError("missing .rmeta")
def verify_inputs():
    externs={k:{"logical":v["logical"],"sha256":sha(physical(Path(v["logical"])))} for k,v in rs["warm"]["externs"].items()}
    assert len(externs)==16 and externs==rs["empty"]["externs"]==rs["warm"]["externs"]
    plugin=physical(Path(rs["warm"]["get_size_derive"]));assert sha(plugin)==rs["warm"]["get_size_sha256"]
    return {"driver":{k:sha(v) for k,v in subjects.items()},"cargo":sha(cargo),"frontend":sha(FROZEN/"bin/rustc"),"plugin":sha(plugin),"externs":externs,"dep_info":sha(depfile),"env_dep":depsenv,"argv":argv,"ruff_index":source_clean(),"historical_edit":load(G/"subject.json")["historical_source"]}
def run(slot,arm,history,initial=False,clock=False,trace=False):
    slot.mkdir();d=slot/"out";d.mkdir();c=slot/"inc";c.mkdir()
    if history=="retained" and not initial:
        source=O/"qualification"/arm/"training"/"inc";sub,=source.glob("ruff_python_parser-*")
        subprocess.run(["cp","-a","--reflink=auto","--",str(sub),str(c/sub.name)],check=True)
    state=train if initial else edited
    opts=spawn_args(skeleton_base,O,train,train/"registry-home",[],cargo,subjects[arm])
    i=opts.index("--")
    more=source_binds(state)
    for fr,to in [(train/"target",TARGET),(train/"shared",SHARED),(train/"registry-home",CARGO_HOME),(train/"rustup",P/"rustup")]:more+=["--ro-bind",str(fr),str(to)]
    more+=["--bind",str(d),str(outdir),"--bind",str(c),str(inc)];opts[i:i]=more
    if trace:
        opts+=["strace","-f","-qq","-yy","-s","16384","-e","trace=execve,openat","-o",str(slot/"audit.strace")]
    measurebody=O/"inner.py";cmd=[*opts,"python3","-B",str(measurebody),str(slot),"1" if clock else "0","rustc","+ohm",*argv[1:]]
    pr=subprocess.run(cmd,cwd=RUFF,env=cfg,capture_output=True)
    (slot/"launcher.stderr").write_bytes(pr.stderr);assert pr.returncode==0,(arm,history,pr.returncode,pr.stderr[-800:])
    meta=d/md.name;rlib=meta.with_suffix(".rlib")
    shell=subprocess.run(["ar","p",str(rlib),"lib.rmeta"],check=True,capture_output=True).stdout
    sealed=elf_meta(shell);raw=meta.read_bytes();assert sealed==raw
    metahead=subprocess.run([*(opts[:opts.index("strace")] if trace else opts),"rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(md)],cwd=RUFF,env=cfg,capture_output=True,check=True)
    (slot/"metadata.root").write_bytes(metahead.stdout)
    m=re.search(rb"^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)",metahead.stdout,re.M);assert m
    objnames=subprocess.run(["ar","t",str(rlib)],check=True,capture_output=True).stdout.decode().splitlines()
    row={"arm":arm,"history":history,"training":initial,"measured":clock,"rmeta_sha256":sha(meta),"archive_rmeta_sha256":hashlib.sha256(sealed).hexdigest(),"rlib_sha256":sha(rlib),"archive_member_count":len(objnames),"header":[v.decode() for v in m.groups()],"actual_driver_sha256":plan["arms"][arm]["driver_sha256"],"child":load(slot/"child.json")}
    if trace:
        rawtrace=(slot/"audit.strace").read_text(errors="replace")
        actual=[Path(m[1]) for line in rawtrace.splitlines() if (m:=re.match(r'^\d+\s+execve\("([^"]+)"',line)) and line.rstrip().endswith("= 0")]
        compiler=[f for f in actual if f.is_absolute() and f.resolve()==(FROZEN/"bin/rustc").resolve()]
        assert compiler==[P/"rustup/toolchains/ohm/bin/rustc"] and sha(compiler[0])==plan["frontend_sha256"],actual
        assert any(driver_name in line and "openat(" in line and re.search(r"\)\s+=\s*\d+",line) for line in rawtrace.splitlines())
        plug=Path(rs["warm"]["get_size_derive"]).name
        assert any(plug in line and "openat(" in line and re.search(r"\)\s+=\s*\d+",line) for line in rawtrace.splitlines())
        row["native_audit_sha256"]=sha(slot/"audit.strace")
    dump(slot/"result.json",row);return row
def roots(row):
    return tuple(row[k] if k!="header" else tuple(row[k]) for k in ["rmeta_sha256","archive_rmeta_sha256","header","archive_member_count"])
def clean_to_ledger(base,src):
    base.mkdir()
    for f in ("child.json","metadata.root","result.json","stdout","stderr","launcher.stderr"):
        shutil.copyfile(src/f,base/f)
inner='''from pathlib import Path
import json,os,resource,subprocess,sys,time
d=Path(sys.argv[1]); timed=sys.argv[2]=="1"; argv=sys.argv[3:]
with (d/"stdout").open("xb") as f,(d/"stderr").open("xb") as e:
    begin=time.monotonic_ns() if timed else None
    p=subprocess.run(argv,stdout=f,stderr=e)
    duration=time.monotonic_ns()-begin if timed else None
u=resource.getrusage(resource.RUSAGE_CHILDREN)
(d/"child.json").write_text(json.dumps({"exit":p.returncode,"wall_ns":duration,"cpu_user_s":u.ru_utime if timed else None,"cpu_system_s":u.ru_stime if timed else None,"affinity":sorted(os.sched_getaffinity(0)),"argv":argv},indent=2)+"\\n")
sys.exit(p.returncode)
'''
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);gate_free(J,2*2**30)
    if args.phase=="qualify":
        O.mkdir(mode=0o700);skeleton_base=skeleton(O);(O/"inner.py").write_text(inner);dump(O/"namespace.json",skeleton_base)
        start=verify_inputs();dump(O/"inputs.json",start);q=O/"qualification";q.mkdir();allarms={}
        for arm in ("parent","candidate"):
            home=q/arm;home.mkdir();used={}
            trainrow=run(home/"training",arm,"empty",initial=True)
            for h in ("retained","empty"):
                used[h]=run(home/h,arm,h,trace=True)
                extra=run(home/(h+"-repeat"),arm,h);assert roots(extra)==roots(used[h]),(arm,h,"unrepeated raw/ELF oracle")
                if arm=="candidate":
                    oracle=rs["warm" if h=="retained" else "empty"]
                    assert used[h]["rmeta_sha256"]==oracle["rmeta_sha256"] and trainrow["rmeta_sha256"]==rs["train"]["rmeta_sha256"],(h,"true full-Cargo reference",used[h],oracle)
            assert used["retained"]["header"][0]!=used["empty"]["header"][0] if arm=="parent" else used["retained"]["header"]==used["empty"]["header"]
            allarms[arm]=used
        assert start==verify_inputs()
        dump(q/"complete.json",{"inputs":sha(O/"inputs.json"),"runner":sha(Path(__file__)),"plan":sha(planpath),"oracles":allarms,"primary_observations":0})
    else:
        cert=O/"qualification/complete.json";assert args.binding==sha(cert)
        b=load(cert);assert b["runner"]==sha(Path(__file__)) and b["plan"]==sha(planpath) and b["inputs"]==sha(O/"inputs.json") and verify_inputs()==load(O/"inputs.json")
        skeleton_base=load(O/"namespace.json");d=O/"heldout";d.mkdir();scores=[]
        for num,block in enumerate(plan["blocks"]):
            for ep in block["endpoints"]:
                for arm in block[ep]:
                    prefix=f"{num:02d}-{ep}-{arm}"
                    with tempfile.TemporaryDirectory(dir=d,prefix="mutable-") as temp:
                        w=Path(temp)/"run";row=run(w,arm,ep,clock=True)
                        assert row["child"]["wall_ns"]>0 and roots(row)==roots(b["oracles"][arm][ep]),(prefix,row)
                        clean_to_ledger(d/prefix,w)
                    scores.append({"pair":num,"endpoint":ep,"arm":arm,**row});dump(d/"observations.json",scores)
                if num in (0,len(plan["blocks"])-1):
                    for arm in block[ep]:
                        out=d/("trace-"+str(num)+"-"+ep+"-"+arm);res=run(out,arm,ep,trace=True)
                        assert roots(res)==roots(b["oracles"][arm][ep])
        assert len(scores)==64 and verify_inputs()==load(O/"inputs.json")
        dump(d/"complete.json",{"pairs_per_endpoint":16,"observations":sha(d/"observations.json"),"certificate":sha(cert),"inputs":sha(O/"inputs.json"),"worker":sha(Path(__file__))})
