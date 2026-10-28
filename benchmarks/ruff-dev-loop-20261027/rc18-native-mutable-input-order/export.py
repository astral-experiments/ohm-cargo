"""Reopen each actual native program, verify its full SHA and run it again outside the worker."""
import argparse,gzip,hashlib,io,json,os,re,subprocess,tarfile
from pathlib import Path
pa=argparse.ArgumentParser();pa.add_argument("parent",type=Path);pa.add_argument("destination",type=Path);a=pa.parse_args()
orig=a.parent/"opposed-native-query-v1"; sync=a.parent/"opposed-native-stock-barrier-v2"
assert not a.destination.exists()
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
def encode(v):return (json.dumps(v,sort_keys=True,indent=2)+"\n").encode()
def put(name,b):
    info=tarfile.TarInfo(name);info.mode=0o644;info.size=len(b);info.mtime=0;tar.addfile(info,io.BytesIO(b))
files={}; runs={}
deny=re.compile(bytes.fromhex("6f70656e61695b2e5d286f72677c636f6d7c696e7465726e616c297c61727469666163746f72795b2e5d7c617574686f72697a6174696f6e3a206265617265727c6769746875625f7061745f7c6768705f5b412d5a612d7a302d395d7b31367d"),re.I)
def take(label,path):
    raw=path.read_bytes(); row={"sha256":hashbytes(raw),"bytes":len(raw),"stored":label}
    if deny.search(raw):
        # Exec process info is already environment-free; keep selected raw native lines if unrelated lookups name private paths.
        if path.name=="trace":
            lines=raw.splitlines(keepends=True);clean=[l for l in lines if not deny.search(l)]
            masked=[(i+1,hashbytes(l))for i,l in enumerate(lines)if deny.search(l)]
            raw=b"".join(l if not deny.search(l)else (b"[private unrelated pathname line SHA256 "+hashbytes(l).encode()+b"]\n")for l in lines)
            row["withheld_line_digests"]=masked;row["public_sha256"]=hashbytes(raw);assert len(clean)+len(masked)==len(lines)
        else:raise ValueError(label)
    put(label,raw);files[label]=row
def runit(key,path,exp,expectedsha):
    raw=path.read_bytes();dig=hashbytes(raw);assert dig==expectedsha
    res=subprocess.run([str(path.resolve())],capture_output=True,timeout=5)
    assert res.returncode==0 and not res.stderr and int(res.stdout)==exp
    label="programs/"+dig+".elf"
    already=any(v.get("body")==label for v in runs.values());can=not deny.search(raw)
    if not already and can:put(label,raw)
    runs[key]={"path":str(path),"sha256":dig,"bytes":len(raw),"body":label if can else None,"exit":res.returncode,"expected":exp,"stdout":res.stdout.decode(),"stderr":res.stderr.decode(),"private_string_in_original_elf":not can}
with tarfile.open(a.destination,"w:gz") as tar:
    for fname in ("opposite-order.py","native-states.json","impossible-hit.json","batch2.c","build2.json","study.stdout","study.stderr"):
        take("original/"+fname,orig/fname)
    for fp in sorted((orig/"case/workspace").rglob("*")):
        if fp.is_file():take("fixture/"+str(fp.relative_to(orig/"case/workspace")),fp)
    for fp in sorted((orig/"case/native").glob("value-*")):
        if fp.is_file():take("native/"+fp.name,fp)
    for n,r in json.loads((orig/"native-states.json").read_bytes()).items():
        for f in ("stdout","stderr","trace"):take(f"original/{n}/{f}",orig/n/f)
        runit(n,orig/"case"/(n+"-target")/"debug/native-router",r["runtime"],r["sha256"])
    for f in ("actual.py","gate.c","synchronized.json","study.stdout","study.stderr"):take("synchronized/"+f,sync/f)
    for n,r in json.loads((sync/"synchronized.json").read_bytes())["rows"].items():
        for f in ("kernel.tsv","receipt.json","stderr","stdout"):take(f"synchronized/{n}/{f}",sync/n/f)
        runit(n,sync/r["physical_rel"],r["value"],r["elf_sha256"])
    before=a.parent/"opposed-native-stock-barrier-v1"
    for f in ("study.stderr","gate.c"):take("initial-compile-only/"+f,before/f)
    put("reopened.json",encode(runs));put("original-sha256.json",encode(files))
print(hashbytes(a.destination.read_bytes()),len(files),len(runs))
