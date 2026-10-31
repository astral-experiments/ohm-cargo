"""Compare the signed parent and proposed Cargo on the same Linux runner and test filesystem."""
from pathlib import Path
import json,os,re,subprocess
root=Path(os.environ["GITHUB_WORKSPACE"])
scratch=Path(os.environ["RUNNER_TEMP"])
def invoke(argv,**kwargs):
    return subprocess.run(argv,text=True,**kwargs)
def output(argv,**kwargs):
    return subprocess.check_output(argv,text=True,**kwargs).strip()
locations={"default":None,"runner":scratch/"gc-fixtures","shm":Path("/dev/shm")/"ohm-gc-fixtures"}
for key,loc in locations.items():
    loc=loc or Path(os.environ.get("TMPDIR","/tmp"));loc.mkdir(parents=True,exist_ok=True)
    print("QA-MOUNT",key,loc,output(["findmnt","-T",str(loc),"-n","-o","TARGET,SOURCE,FSTYPE"]),output(["stat","-f","-c","%T %t",str(loc)]),flush=True)
print("QA-KERNEL",output(["uname","-sr"]),os.getuid(),flush=True)
for role,sha in (("baseline","2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c"),("candidate","3871cbf823b811d3d5d9f59b87fb9df8d6cb9148")):
    work=root/role
    assert output(["git","rev-parse","HEAD"],cwd=work)==sha
    src=work/"src/workspace/build_cache_gc/mod.rs";old=src.read_text()
    end="        Ok(summary)\n    }\n\n    struct Cache {"
    assert old.count(end)==1
    src.write_text(old.replace(end,'        eprintln!("QA-GC dry={} files={} bytes={} retained={} busy={} skipped={:?} locks={:?}", dry_run, summary.counts.files, summary.counts.bytes, summary.retained, summary.busy, summary.skipped, summary.blocking_locks);\n'+end))
    env={**os.environ,"CARGO_TARGET_DIR":str(scratch/"gc-qa-target")}
    args=["cargo","+1.99.0","test","--locked","-p","cargo","--lib","--no-run","--message-format=json"]
    built=invoke(args,cwd=work,env=env,stdout=subprocess.PIPE,check=True)
    bins=[x["executable"] for line in built.stdout.splitlines() if (x:=json.loads(line)).get("reason")=="compiler-artifact" and x.get("executable") and x.get("target",{}).get("kind")==["lib"]]
    assert len(bins)==1,bins
    for key,loc in locations.items():
        trial=dict(env)
        if loc is not None:trial["TMPDIR"]=str(loc)
        args=[bins[0],"workspace::build_cache_gc","--nocapture"]
        run=invoke(args,cwd=work,env=trial,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        results=run.stdout.splitlines();print("QA-RESULT",role,key,run.returncode,next((s for s in results if s.startswith("test result:")),"no summary"),flush=True)
        if run.returncode:
            skipped=list(dict.fromkeys(re.sub(r'/[^" ]*?\.tmp\w+','/TEMPDIR',s) for s in results if "QA-GC" in s and "files=0" in s and "skipped=[]" not in s));print("QA-REASONS",role,key,skipped[:12],flush=True)
            print("QA-FAILURES",role,key,[s.strip() for s in results if s.startswith("    workspace::")][:20],flush=True)
        out=scratch/"ohm-22-gc-qualification-logs";out.mkdir(exist_ok=True)
        (out/(role+"-"+key+".log")).write_text(run.stdout)
