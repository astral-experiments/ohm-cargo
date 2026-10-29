"""Tie the changed path operands to their own on-disk serialized Rust link state and Cargo manifest."""
from pathlib import Path
import hashlib,json,os,stat,subprocess,sys
root=Path(sys.argv[1]).resolve();study=root/"native-ready-order19";sp=study/"reports";prefix="clock-v4-edit-nativeedit-trace-after-"
def take(p):
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as f:
        start=os.fstat(f.fileno()); b=f.read();end=os.fstat(f.fileno())
        assert stat.S_ISREG(start.st_mode) and len(b)==end.st_size and (start.st_dev,start.st_ino,start.st_ctime_ns,start.st_mtime_ns)==(end.st_dev,end.st_ino,end.st_ctime_ns,end.st_mtime_ns)
    return b
h=lambda b:hashlib.sha256(b).hexdigest()
x={};vs={}
for a in "AB":
    d=sp/(prefix+a);src=json.loads(take(d/"execs.json"))
    x[a]={Path(e["out"]).name:e["argv"] for e in src["events"] if e["role"]=="stock-wild"}
    vs[a]=json.loads(subprocess.check_output([sys.executable,"-IB",study/"native-order-lane.py","paths","qa",a]))
out={}
for n in sorted(x["A"]):
    pairs=[(a,b) for a,b in zip(x["A"][n],x["B"][n]) if a!=b and (a.endswith(".rcgu.o") or b.endswith(".rcgu.o"))]
    if not pairs:continue
    measures={}
    for side,arm in enumerate("AB"):
        names=[p[side] for p in pairs];parent=Path(names[0]).parent
        assert all(Path(p).parent==parent for p in names) and parent.name==n+".rlink-objects"
        physical=Path(vs[arm]["target"])/parent.parent.relative_to(root/"target")
        link=take(physical/(n+".rlink"));raw=take(physical/(n+".rlink-cache.json"));manifest=json.loads(raw)
        cached={row["path"] for row in manifest["objects"]};assert set(names)<=cached
        literal=sum(os.fsencode(name) in link for name in names)
        basename=sum(os.fsencode(Path(name).name) in link for name in names)
        measures[arm]={"held_rlink_sha256":h(link),"held_rlink_bytes":len(link),"cargo_manifest_sha256":h(raw),
                       "complete_manifest_object_names":len(cached),"changed_fields_present_in_manifest":len(names),
                       "changed_absolute_paths_present_in_rlink":literal,"changed_basenames_present_in_rlink":basename}
    out[n]=measures
print(json.dumps(out,sort_keys=True,separators=(",",":")))
