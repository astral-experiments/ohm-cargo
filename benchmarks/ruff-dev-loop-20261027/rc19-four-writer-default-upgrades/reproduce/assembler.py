"""Exercise the published generic assembler source on an already-poisoned -19 target."""
import hashlib,json,os,stat,subprocess,sys
from pathlib import Path

old,new,dest=(Path(s).resolve() for s in sys.argv[1:4])
root=Path(__file__).resolve().parent
original=Path(os.environ.get("OHM_ASM_REPRO",Path(__file__).with_name("reproduce-generic.py")))
raw=original.read_bytes()
assert hashlib.sha256(raw).hexdigest()=="eebd066f852f85b3d7605fb6ae8f1263230b9371b949d4536fc2e83b6cb5a487"
assert not dest.exists() and set(os.sched_getaffinity(0))==set(range(24,28))
pre=raw.decode().split("rows={}\nfor arm,flags in",1)[0]
mark="p=sub(cmd,root,e);"
assert pre.count(mark)==1
pre=pre.replace(mark,"p=sub(['strace','-ff','-qq','-s','2000','-e','trace=execve,open,openat','-o',str(out/'syscall'),*cmd],root,e);")
mark="r=sub([exe],root,e); assert r.returncode==0;"
assert pre.count(mark)==1
pre=pre.replace(mark,"assert stat.S_ISREG(Path(exe).lstat().st_mode) and Path(exe).read_bytes()[:4]==b'\\x7fELF'; r=sub([exe],root,e); (out/'program.stdout').write_bytes(r.stdout); (out/'program.stderr').write_bytes(r.stderr); assert r.returncode==0;")
# Use the exact existing project generator and ordinary Cargo argv, adding only syscall and output capture.
sys.argv=[str(original),str(dest),str(old)]
context={"__name__":"__main__","stat":stat}
exec(compile(pre,str(original),"exec"),context)
root=dest/"project"
context["project"](root)
state=dest/"live"
payload=root/"untracked.bin"
alias=dest/"rustup/toolchains/ohm"
rows={}
def snapshot():
    h=hashlib.sha256();n=0;size=0
    for top in (root,state):
        for item in sorted(top.rglob("*")):
            if item.is_file():
                with item.open("rb") as fd:
                    st=os.fstat(fd.fileno())
                    assert stat.S_ISREG(st.st_mode)
                    b=hashlib.file_digest(fd,"sha256").hexdigest()
                n+=1;size+=st.st_size
                h.update(json.dumps([str(item.relative_to(dest)),st.st_dev,st.st_ino,st.st_mtime_ns,st.st_size,b],separators=(",",":")).encode()+b"\n")
    return {"files":n,"bytes":size,"sha256":h.hexdigest()}
def put(path,obj):
    with path.open("x") as f:
        json.dump(obj,f,indent=2,sort_keys=True);f.write("\n")
def step(label,expected,store=None,strict=True):
    r=context["action"](label,root,state if store is None else store,[])
    out=dest/"commands"/label
    rustcs=[];wild=[];reads=[];commands=[]
    for f in sorted(out.glob("syscall.*")):
        for line in f.read_text(errors="replace").splitlines():
            if line.startswith("execve(") and line.endswith("= 0"):
                if '"/' in line:
                    path=line.split('"',2)[1]
                    if '/wild-ld/' in path:wild.append(hashlib.sha256(line.encode()).hexdigest())
                    if Path(path).name=="rustc" and '"--crate-name", ' in line:
                        role=line.split('"--crate-name", "',1)[1].split('"',1)[0]
                        rustcs.append([role, '"link-only"' in line or '"-Zlink-only"' in line])
                    if Path(path).name=="cargo" and ("/sdk/" in path or str(alias) in path or "/measured-h4-" in path):
                        commands.append(hashlib.sha256(line.encode()).hexdigest())
            if line.startswith(("openat(","open(")) and 'untracked.bin"' in line:
                reads.append(["absent" if " ENOENT " in line else "present",hashlib.sha256(line.encode()).hexdigest()])
    r.update(label=label,current_input=list(payload.read_bytes()) if payload.exists() else None,physical_rustcs=sorted(rustcs),physical_wild=wild,physical_payload_reads=reads,observed_cargo_execs=commands)
    rows[label]=r
    put(out/"physical.json",r)
    actual=r["value"] if r["status"]==0 else r["status"]
    if strict:assert actual==expected,(label,actual,expected)
    return actual
payload.write_bytes(bytes([17]))
step("old-original","5:17")
context["put"](root/"revision/src/lib.rs",context["revision"](9))
payload.write_bytes(bytes([29]))
step("old-edited","9:17")
step("old-repeat","9:17")
step("old-empty","9:29",dest/"old-empty")
bef=snapshot()
assert bef["files"]>10 and alias.resolve()==old
next_alias=alias.with_name("next")
next_alias.symlink_to(new,target_is_directory=True)
os.replace(next_alias,alias)
assert alias.resolve()==new and snapshot()==bef
put(dest/"upgrade.json",{"old":context["sha"](old/"bin/cargo"),"new":context["sha"](new/"bin/cargo"),"changed_alias_only":True,"snapshot":bef})
# Record independent current verdicts even if this particular upgrade exposes a stale state.
first=step("new-unchanged-after-upgrade","9:29",strict=False)
repeat=step("new-repeat","9:29",strict=False)
clean=step("new-independent","9:29",dest/"new-empty")
context["put"](root/"revision/src/lib.rs",context["revision"](7))
payload.unlink()
missing=step("new-missing",101,strict=False)
missing_clean=step("new-empty-missing",101,dest/"new-empty-missing")
context["put"](root/"revision/src/lib.rs",context["revision"](5))
payload.write_bytes(bytes([17]))
restored=step("new-restore","5:17",strict=False)
settled=step("new-restore-repeat","5:17",strict=False)
result={"fixture_source":hashlib.sha256(raw).hexdigest(),"old_cargo":context["sha"](old/"bin/cargo"),"new_cargo":context["sha"](new/"bin/cargo"),"old_rustc":context["sha"](old/"bin/rustc"),"new_rustc":context["sha"](new/"bin/rustc"),"snapshot":bef,"rows":rows,"pass":first==repeat==clean=="9:29" and missing==missing_clean==101 and restored==settled=="5:17"}
put(dest/"result.json",result)
assert result["pass"],{k:(r["status"],r.get("value")) for k,r in rows.items()}
for label in ["old-repeat","new-repeat","new-restore-repeat"]:
    r=rows[label];assert r["target_fresh"] and not r["physical_rustcs"] and not r["physical_wild"],(label,r)
assert rows["old-edited"]["physical_payload_reads"]==[]
for label in ["new-unchanged-after-upgrade","new-independent","new-restore"]:
    r=rows[label];assert ["app",False] in r["physical_rustcs"] and r["physical_wild"] and any(x[0]=="present" for x in r["physical_payload_reads"]),(label,r)
for label in ["new-missing","new-empty-missing"]:
    r=rows[label];assert r["missing"] and ["app",False] in r["physical_rustcs"] and any(x[0]=="absent" for x in r["physical_payload_reads"]),(label,r)
