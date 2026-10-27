"""Replay the genuine released Cargo workload in an isolated copy at its original logical paths."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys

donor=Path("/mnt/devbox-scratch/dev-user/ohm-dedent-lane-20261027-v1")
private=Path(__file__).resolve().parent
code=(donor/"run.py").read_text().split('\nwith (P/\'native-measure.lock\')')[0]
sc={"__name__":"verified_original","__file__":str(donor/"run.py")}
exec(compile(code,str(donor/"run.py"),"exec"),sc)
sha=sc["sha"];save=sc["save"];command=sc["command"];adjust=sc["adjust"]
def in_namespace(cmd,env,cwd,out):
    # The entire worker is already in the restored target's read-only outer namespace.
    with (out/"stdout").open("xb") as so,(out/"stderr").open("xb") as se:
        v=subprocess.run(cmd,env=env,cwd=cwd,stdout=so,stderr=se)
    save(out/"exit.json",{"returncode":v.returncode})
    assert v.returncode==0,(out,(out/"stderr").read_bytes()[-1400:])
sc["child"]=in_namespace
root=sc["root"];sdk=sc["sdk"];plan=sc["plan"]
assert len(os.sched_getaffinity(0))==8 and sha(sdk/"bin/cargo")==plan["cargo"]
env={"HOME":str(Path.home()),"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PATH":str(Path.home()/".cargo/bin")+":/usr/local/bin:/usr/bin:/bin",
     "RUSTUP_HOME":str(sc["release"]/"rustup"),"RUSTUP_AUTO_INSTALL":"0","CARGO_HOME":str(root/"registry-home"),
     "GIT_OPTIONAL_LOCKS":"0","CARGO_NET_OFFLINE":"true","CARGO_BUILD_BUILD_DIR":str(root/"build-dir/test"),
     "CARGO_TARGET_DIR":str(root/"target/test")}
out=private/"products";out.mkdir()
def reference(phase):
    return json.loads((private/"reference"/phase/"receipt.json").read_bytes())
def seal(st,reference_row,row):
    assert row["elf"]==reference_row["elf"] and row["total"]==reference_row["total"]==148
    trivia=[Path(p) for p in row["artifacts"] if "libruff_python_trivia-" in p and p.endswith(".rlib")]
    assert len(trivia)==1; t=trivia[0]; d=out/st;d.mkdir()
    shutil.copy2(t,d/"trivia.rlib");save(d/"row.json",row)
    if st=="seed":return
    assert row["processes"]["jobs"].count(["ruff_python_trivia","full"])==1
    assert sorted(row["processes"]["jobs"])==sorted(reference_row["processes"]["jobs"])
    assert sorted(row["processes"]["wild"])==sorted(reference_row["processes"]["wild"])
    deleted=set(row["artifacts"])^set(reference_row["artifacts"]);assert not deleted
    for p,digest in row["artifacts"].items():
        if "ruff_python_trivia" not in p:assert digest==reference_row["artifacts"][p],p
    records={}
    for name in row["processes"]["wild"]:
        elf,=[Path(p) for p in row["elf"] if Path(p).name==name]
        layout=elf.with_name(elf.name+".layout")
        assert layout.is_file() and sha(elf)==reference_row["elf"][str(elf)]
        shutil.copy2(layout,d/(name+".layout"));shutil.copy2(elf,d/name)
        records[name]={"layout":sha(layout),"elf":sha(elf),"bytes":layout.stat().st_size,"path":str(elf)}
    save(d/"layouts.json",records)
    print(st,row["processes"]["jobs"],records,flush=True)
sc["gate"]("original")
initial=command("test","layout-seed",env,"original",trace=True)
assert initial["total"]==initial["fresh"]==148 and not initial["processes"]["jobs"] and not initial["processes"]["wild"]
seal("seed",reference("restored-fresh"),initial)
for st in ("reversed","restored"):
    adjust(st)
    row=command("test","layout-"+st,dict(env,WILD_WRITE_LAYOUT="1"),st,trace=True,probe=True)
    seal(st,reference(st),row)
    fresh=command("test","layout-"+st+"-fresh",env,st,trace=True)
    assert fresh["total"]==fresh["fresh"]==148 and fresh["artifacts"]==row["artifacts"] and not fresh["processes"]["wild"] and not fresh["processes"]["jobs"]
save(out/"complete.json",{"directions":2,"actual_wild":4,"fresh_gates":3,"roster_per_command":148})
