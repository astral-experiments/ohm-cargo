"""Repeat an actual historical Ruff edit after removing one parser incremental input from an independent Cargo state."""
from pathlib import Path
import collections, fcntl, hashlib, json, os, re, shutil, subprocess, sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,load,dump,sha,need,env
from namespace import skeleton,spawn_args
from state import source_binds,source_clean,gate_free,set_source
from processes import records
j=P/"mixed-registry-only-pilot";out=j/"parser-incremental-components";cfg=env()
cfg["PATH"]=load(j/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
arms=load(w/"runner-binding.json")["arms"];fixture=hist/"fixture"
edits={"all":[],"no-prefix":["metadata-prefix-v3.ohm-prefix-v3"],"no-metadata":["metadata.rmeta"],"no-query":["query-cache.bin"],"no-work-products":["work-products.bin"],"no-graph":["dep-graph.bin"],"empty":["*"]}
def namespace(st,arm):
    o=spawn_args(mount,out,st,st/"registry-home",[],Path(arms[arm]["cargo"]),Path(arms[arm]["driver"]));i=o.index("--");o[i:i]=source_binds(st);return o
def read_header(o,md):
    q=subprocess.run([*o,"rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(md)],env=cfg,cwd=RUFF,capture_output=True,check=True)
    m=re.search(r"^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)",q.stdout.decode(),re.M);assert m
    return q.stdout,{"private":m[1],"stable":m[2],"public":m[3]}
def run(d,st,arm,ed,argument):
    set_source(st,fixture,ed);opt=namespace(st,arm);cmd=["cargo","+ohm","build","--locked","--offline","--message-format=json"]
    with(d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:
        z=subprocess.run([*opt,"strace","-ff","-qq","-s","1048576","-e","trace=execve,execveat,prctl","-o",str(d/"exec"),*cmd],cwd=RUFF,env=cfg,stdout=so,stderr=se)
    if z.returncode!=0:
        dump(d/"failed-command.json",{"status":z.returncode,"tail":(d/"stderr").read_text()[-3000:]});raise ValueError((d,"cargo",z.returncode))
    comp=[r for ln in(d/"stdout").read_bytes().splitlines() if (r:=json.loads(ln))["reason"]=="compiler-artifact"]
    actual=[a for _,f,a in records(d) if Path(f).name=="rustc" and "--crate-name" in a and "--out-dir" in a]
    arg,=[a for a in actual if a[a.index("--crate-name")+1]=="ruff_python_parser"]
    assert arg==argument and len(comp)==501 and all(r["fresh"] for r in comp if r["target"]["name"]=="ruff_python_ast"),(arm,arg==argument)
    row,=[r for r in comp if r["target"]["name"]=="ruff_python_parser"];assert not row["fresh"]
    md,=[Path(v) for v in row["filenames"] if v.endswith(".rmeta")];rlib,=[Path(v) for v in row["filenames"] if v.endswith(".rlib")]
    raw,header=read_header(opt,md);(d/"parser.root.txt").write_bytes(raw)
    externs={}
    for i,a in enumerate(arg[:-1]):
        if a=="--extern":
            n,logical=arg[i+1].split("=",1);p=Path(logical)
            assert p.is_relative_to(TARGET),p
            externs[n]={"logical":logical,"sha":sha(st/"target"/p.relative_to(TARGET))}
    r={"arm":arm,"source":"edited" if ed else "original","command":cmd,"status":z.returncode,"unit_count":len(comp),"dirty_units":[r["target"]["name"] for r in comp if not r["fresh"]],
       "rustc_jobs":[[a[a.index("--crate-name")+1],"-Z" in a and any(t.startswith("link-only") for t in a)] for a in actual],
       "rustc_argv":arg,"cargo":arms[arm]["cargo_sha256"],"driver":arms[arm]["driver_sha256"],"rmeta":str(md),"rmeta_sha256":sha(st/"target"/md.relative_to(TARGET)),
       "rlib":str(rlib),"rlib_sha256":sha(st/"target"/rlib.relative_to(TARGET)),"parser_header":header,"externs":externs,"git_index":source_clean()}
    dump(d/"result.json",r);return r
def clone(donor,st):
    assert not st.exists() and shutil.disk_usage(x).free>107*2**30
    gate_free(st.parent,8*2**30);subprocess.run(["cp","-a","--reflink=auto","--",str(donor),str(st)],check=True)
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);out.mkdir(mode=0o700);mount=skeleton(out);idx=source_clean()
    assert (j/"parser-ich-callers-v2/complete.json").is_file() and (hist/"failure.txt").is_file()
    dump(out/"design.json",{"edits":edits,"order":["B","A"],"cargo":{a:arms[a]["cargo_sha256"] for a in "AB"},"driver":{a:arms[a]["driver_sha256"] for a in "AB"},"source":load(fixture/"manifest.json"),"inherited_PATH":cfg["PATH"],"timed":False})
    groups={}
    for arm in ["B","A"]:
        d=out/arm;d.mkdir();training=d/"train-original";training.mkdir();baseline=training/"physical";donor=hist/"state/build"/arm
        actual=[a for _,f,a in records(hist/"receipts/build"/arm/"first-edit") if Path(f).name=="rustc" and "--crate-name" in a and a[a.index("--crate-name")+1]=="ruff_python_parser" and "--out-dir" in a]
        arg,=actual;incr,=[Path(a.removeprefix("incremental=")).relative_to(TARGET) for a in arg if a.startswith("incremental=")]
        clone(donor,baseline);assert (baseline/"source-state").read_text()=="edited"
        ct=run(training,baseline,arm,False,arg);res={}
        bsession,=(baseline/"target"/incr).glob("ruff_python_parser-*/s-*-*-*");assert bsession.is_dir()
        inv={str(f.relative_to(bsession)):{"bytes":f.stat().st_size,"sha":sha(f)} for f in sorted(bsession.rglob("*")) if f.is_file()}
        assert not any("check-session" in n for n in inv);dump(training/"session.json",inv)
        for name,remove in edits.items():
            sub=d/name;sub.mkdir();st=sub/"physical";clone(baseline,st);session=st/"target"/bsession.relative_to(baseline/"target")
            assert (session/"metadata.rmeta").is_file() and not(session/"metadata.rmeta").samefile(bsession/"metadata.rmeta")
            seen={str(f.relative_to(session)):{"bytes":f.stat().st_size,"sha":sha(f)} for f in sorted(session.rglob("*")) if f.is_file()};assert seen==inv
            if remove==["*"]:session.parent.rename(sub/"inactive-parser-cache")
            else:
                for rel in remove:
                    assert rel in inv
                    (session/rel).rename(sub/("disabled-"+rel))
                    assert not (session/rel).exists()
                    alias=session/("ohm-build-"+rel)
                    if alias.exists():assert sha(alias)==inv[rel]["sha"]
            row=run(sub,st,arm,True,arg);row["disabled"]=remove;row["started_from"]=sha(training/"session.json");row["state"]=name
            dump(sub/"result.json",row);res[name]=row;groups[arm]=res;dump(out/"results.json",groups)
            print(arm,name,row["parser_header"],row["rmeta_sha256"][:10],len(row["rustc_jobs"]),flush=True)
        assert len({r["started_from"] for r in res.values()})==1 and all(r["externs"]==res["all"]["externs"] for r in res.values())
    assert source_clean()==idx;dump(out/"complete.json",{"arms":list(groups),"results_sha256":sha(out/"results.json"),"experiments":sum(map(len,groups.values())),"unscored":True})
