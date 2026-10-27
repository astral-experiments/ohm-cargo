"""Follow raw metadata differences through the actual compiler-decoded private and public credentials."""
import fcntl, hashlib, json, os, re, subprocess, sys
from pathlib import Path
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(w))
from common import P, TARGET, SHARED, CARGO_HOME, FROZEN, RUFF, SONAME, load, dump, sha, env, need
from state import source_binds, source_clean
from namespace import skeleton,spawn_args

root=P/"mixed-registry-only-pilot"; prior=root/"ordinary-reciprocal-bc-v1"; hist=x/"mixed-native-full-abc-h3-v2"
out=root/"residual-headers-bc";binding=load(w/"runner-binding.json");base=load(prior/"comparisons.json")
def parsed(text):
    parts=text.split("=External Dependencies=");assert len(parts)==2
    h=re.search(r"^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)",parts[0],re.M)
    assert h
    deps={}
    for line in parts[1].strip().splitlines():
        m=re.fullmatch(r"(\d+) (\S+) hash (\w+) host_hash (.*?) kind (\S+) (\S+)(.*)",line);assert m,line
        deps[m[2]]={"ord":int(m[1]),"hash":m[3],"host":m[4],"kind":m[5],"visibility":m[6],"tail":m[7]}
    return {"private":h[1],"stable":h[2],"public":h[3],"dependencies":deps}
def inside(label):
    rows=load(prior/label/"all-rust-libraries.json")
    keys=sorted({k for v in base.values() for k in v["different_library_bytes"]})
    d=out/label;d.mkdir();col={}
    for key in keys:
        p=Path(rows[key]["file"]);assert p.suffix==".rmeta" and sha(p)==rows[key]["sha256"]
        q=subprocess.run(["rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(p)],env=env(),cwd=RUFF,capture_output=True,check=True)
        dest=d/(p.stem+".root.txt");dest.write_bytes(q.stdout)
        col[key]={"native_rmeta":rows[key],"listing_sha":sha(dest),"header":parsed(q.stdout.decode())}
    dump(d/"headers.json",col)
if len(sys.argv)>1:
    inside(sys.argv[1]);sys.exit(0)
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);sindex=source_clean()
    out.mkdir(mode=0o700);mount=skeleton(out)
    states={"cold-B":(root/"shared-b-v3/physical","B"),"cold-C":(root/"shared-c-v3/physical","C"),"warm-B":(hist/"state/build/B","B")}
    for lab,(st,arm) in states.items():
        a=binding["arms"][arm];cmd=spawn_args(mount,out,st,st/"registry-home",[],Path(a["cargo"]),Path(a["driver"]))
        ix=cmd.index("--");binds=[]
        for src,dst in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:
            binds+=["--ro-bind",str(src),str(dst)]
        cmd[ix:ix]=binds+source_binds(st)
        subprocess.run([*cmd,sys.executable,"-B",str(Path(__file__).resolve()),lab],check=True)
    pairs={}
    for left,right in [("cold-B","cold-C"),("warm-B","cold-B")]:
        a,b=(load(out/k/"headers.json") for k in (left,right));res={}
        for key in a:
            a1,b1=a[key],b[key];hh,ii=a1["header"],b1["header"]
            d0,d1=hh["dependencies"],ii["dependencies"]
            cd={k:[d0.get(k),d1.get(k)] for k in d0.keys()|d1.keys() if d0.get(k)!=d1.get(k)}
            res[key]={"raw_equal":a1["native_rmeta"]["sha256"]==b1["native_rmeta"]["sha256"],"private":[hh["private"],ii["private"]],"public":[hh["public"],ii["public"]],"stable":[hh["stable"],ii["stable"]],"changed_deps":cd}
            print(left,right,key.split("|")[1],"raw",res[key]["raw_equal"],"private",hh["private"]==ii["private"],"public",hh["public"]==ii["public"],"deps",sorted(cd),flush=True)
        pairs[left+"--"+right]=res
    dump(out/"differences.json",pairs);need(source_clean()==sindex,"source")
