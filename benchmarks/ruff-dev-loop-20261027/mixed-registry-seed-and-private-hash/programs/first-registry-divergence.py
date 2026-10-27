"""Audit every changed crates.io library after literal get-size-derive2 matching across toolchains."""
from pathlib import Path
import fcntl, hashlib, json, os, re, subprocess, sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,RUFF,FROZEN,load,dump,sha,env
from state import source_binds,source_clean
from namespace import skeleton,spawn_args
root=P/"mixed-registry-only-pilot";prior=root/"ordinary-reciprocal-matched-abc-v1";out=root/"cross-image-registry-root"
b=load(w/"runner-binding.json");pair=load(prior/"comparisons.json")["cold-A--cold-B"];keys=sorted(k for k in pair["different_library_bytes"] if k.startswith("registry+"))
def parse(text):
    h=re.search(r"^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)",text,re.M); assert h
    rows={}
    for l in text.split("=External Dependencies=")[1].strip().splitlines():
        m=re.fullmatch(r"(\d+) (\S+) hash (\w+) host_hash (.*?) kind (\S+) (\S+)(.*)",l);assert m
        rows[m[2]]=[m[3],m[4],m[5],m[6],m[7]]
    return {"private":h[1],"public":h[3],"stable":h[2],"deps":rows}
def run(label):
    rows=load(prior/("cold-"+label)/"all-rust-libraries.json");folder=out/label;folder.mkdir();saved={}
    for k in keys:
        row=rows[k];p=Path(row["file"]);assert sha(p)==row["sha256"]
        q=subprocess.run(["rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(p)],cwd=RUFF,env=env(),capture_output=True,check=True)
        name=row["file"].split("/")[-1]
        dest=folder/(name+".root.txt");dest.write_bytes(q.stdout);saved[k]={"root":parse(q.stdout.decode()),"library":row,"listing":sha(dest)}
    dump(folder/"headers.json",saved)
if len(sys.argv)>1:run(sys.argv[1]);sys.exit(0)
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);sindex=source_clean();out.mkdir(mode=0o700);mount=skeleton(out)
    for state,c in [("older-matched-workspace-cold","A"),("shared-b-v3","B")]:
        st=root/state/"physical";arm=b["arms"][c];cmd=spawn_args(mount,out,st,st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]));i=cmd.index("--")
        ro=[]
        for src,dst in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:
            ro+=["--ro-bind",str(src),str(dst)]
        cmd[i:i]=ro+source_binds(st)
        subprocess.run([*cmd,sys.executable,"-B",str(Path(__file__).resolve()),c],cwd=RUFF,check=True)
    a,z=(load(out/l/"headers.json") for l in "AB");res={}
    for k in keys:
        x0,x1=[e[k]["root"] for e in (a,z)]
        deps={n:[x0["deps"].get(n),x1["deps"].get(n)] for n in x0["deps"].keys()|x1["deps"].keys() if x0["deps"].get(n)!=x1["deps"].get(n)}
        res[k]={"public":[x0["public"],x1["public"]],"private":[x0["private"],x1["private"]],"stable":[x0["stable"],x1["stable"]],"changed_deps":deps}
        if x0["private"]!=x1["private"] and not deps:print("first-unexplained",k.split("|")[1],res[k]["private"],flush=True)
    dumps={n:r for n,r in res.items() if not r["changed_deps"] and len(set(r["private"]))>1}
    dump(out/"all.json",res);dump(out/"first.json",dumps);assert source_clean()==sindex
