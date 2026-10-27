"""Read an explicit set of evidence files from the retained H3 pilots; exclude build targets and caches."""
from pathlib import Path
import collections, gzip, hashlib, json, os, re, shutil, sys

x=Path.home()/".cache/ohm-233-position-qualified-20261027"
p=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
j=p/"mixed-registry-only-pilot"; scripts=x/"mixed-registry-seed-programs-20261027"
frozen=scripts/"match-frozen-prereg"; output=p/"mixed-registry-ich-export"
output.mkdir(mode=0o700)
def digest(data):return hashlib.sha256(data).hexdigest()
def obj(p):return json.loads(p.read_bytes())
def dump(dst,value):
    dst=output/dst;dst.parent.mkdir(exist_ok=True,parents=True)
    dst.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def put(src,dst,*,compress=False):
    assert src.is_file() and not src.is_symlink(),src
    data=src.read_bytes();dst=output/Path(dst)
    if compress or (len(data)>100_000 and dst.suffix==".json"):
        dst=Path(str(dst)+".gz");data=gzip.compress(data,compresslevel=6,mtime=0)
    assert not dst.exists(),dst;dst.parent.mkdir(exist_ok=True,parents=True);dst.write_bytes(data)
def group(source,dest,pattern):
    for f in sorted(source.glob(pattern)):put(f,Path(dest)/f.relative_to(source))
def standard(source,dest,names):
    for f in names:
        if (source/f).is_file():put(source/f,Path(dest)/f,compress=f in ("stdout","stderr") and (source/f).stat().st_size>70_000)
put(frozen/"registry-match-registration.json","preregistration.json")
group(scripts,"programs","*.py");group(frozen,"programs/frozen","*.py")
for f in ["projection-b-first","projection-b-v2","winner-native-plugin"]:
    for suffix in ["stderr","stdout"]:
        put(scripts/(f+"."+suffix),"exclusions/"+f+"."+suffix)
for f in frozen.iterdir():
    if f.name in ["cross-natural.rc","cross-natural.reason"]:put(f,"exclusions/"+f.name)
obs=x/"mixed-registry-input-qualification-v1/scoped.json"
if obs.exists():put(obs,"exclusions/scoped.json")
# Retain the whole actual +ohm registry/feature provenance for all 3 independently rebuilt workspaces.
for arm,name in zip("ABC",["older-matched-workspace-cold","shared-b-v3","shared-c-v3"]):
    src=j/name
    for f in sorted(src.glob("*.json")):
        if f.name!="mount.json":put(f,"seed/"+arm+"/"+f.name)
    for f in ["stdout","stderr"]:put(src/"build"/f,"seed/"+arm+"/cargo."+f,compress=True)
sel=j/"older-authenticated-base/selection";standard(sel,"selection",["complete.json","all-attempts.json"])
for a in sorted(sel.glob("attempt-??")):
    standard(a,"selection/"+a.name,["producer.json","stdout","stderr"])
# Produce independent section/whole hashes for every original observed dylib available in its next private archive.
def sections(data):
    import struct
    assert data.startswith(b"\x7fELF") and struct.unpack_from("<H",data,16)[0]==3
    taboff=struct.unpack_from("<Q",data,40)[0];entsize,count,names=struct.unpack_from("<HHH",data,58)
    tab=[struct.unpack_from("<IIQQQQIIQQ",data,taboff+i*entsize) for i in range(count)]
    a=tab[names];ss=data[a[4]:a[4]+a[5]]
    return {ss[q[0]:ss.index(b"\0",q[0])].decode():digest(data[q[4]:q[4]+q[5]]) for q in tab if ss[q[0]:ss.index(b"\0",q[0])].decode() in [".text",".rustc",".rodata",".data.rel.ro"]}
variants={};all_attempts=obj(sel/"all-attempts.json")
for i,a in enumerate(all_attempts):
    if i+1<len(all_attempts):so,=(sel/f"attempt-{i+2:02d}/previous-target-unit/out").glob("libget_size_derive2-*.so")
    else:
        src=j/"older-matched-workspace-cold";so=src/"physical/target"/obj(src/"projected.json")["expected_proc_macro"]
    data=so.read_bytes();dg=digest(data);assert dg==a["entire_so_sha256"]
    variants.setdefault(dg,{"byte_length":len(data),"sections":sections(data),"attempts":[]})["attempts"].append(i+1)
dump("selection/native-sections.json",variants)
# Original regular archives are intentionally retained on H3, only whole and individual section receipts travel.
for studyname,folder in [("same-compiler","ordinary-reciprocal-bc-v1"),("three-images","ordinary-reciprocal-matched-abc-v1")]:
    src=j/folder;d=Path("mixed")/studyname
    for file in ["comparisons.json","complete.json","readers.json"]:put(src/file,d/file)
    group(src/"bridge-src",d/"bridge-src","*.rs")
    for f in ["cold-A","cold-B","cold-C","warm-B"]:
        if (src/f).is_dir():standard(src/f,d/f,["all-rust-libraries.json","receipt.json"])
for prefix,source in [("same-compiler-headers","residual-headers-bc"),("cross-image-headers","cross-image-registry-root")]:
    src=j/source;d=Path("mixed")/prefix;group(src,d,"*.json")
    for a in src.iterdir():
        if a.is_dir() and a.name!="secure-root":
            group(a,d/a.name,"*.json")
            # All three real mixed/parser or specifically first-diverging registry raw header listings.
            for f in sorted(a.glob("*.root.txt")):
                if prefix.startswith("same") or any(k in f.name for k in ["ref_cast","rustversion","serde_core","terminfo","thiserror"]):put(f,d/a.name/f.name)
src=j/"winner-native-plugin-and-leaves-v2";group(src,"matched-plugin","*.json");group(src,"matched-plugin","*.rs")
for arm in "ABC":standard(src/arm,Path("matched-plugin")/arm,["plugin.root.txt","conflict.stderr"])
src=j/"history-input-receipt-v1";group(src,"parser/source-and-flags","*.json")
src=j/"parser-ich-by-ast";group(src,"parser/controlled","*.json")
for v in obj(src/"variants.json"):
    state=v["name"];d=Path("parser/controlled")/state;z=src/state
    for f in ["parser.before.root","parser.after.root","ruff_wasm.after.root","ty_wasm.after.root","starting-ich-manifest.json"]:put(z/f,d/f)
    for f in ["stdout","stderr"]:put(z/f,d/f,compress=True)
    idx=v["actual_parser_argv"].index("--out-dir")+1
    logical=Path(v["actual_parser_argv"][idx]);target=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target")
    dest=z/"physical/target"/logical.relative_to(target);raw,=dest.glob("libruff_python_parser-*.rmeta")
    assert digest(raw.read_bytes())==v["parser_raw"]
    dest=Path("parser/raw")/(v["parser_raw"]+".rmeta")
    if not(output/Path(str(dest)+".gz")).exists():put(raw,dest,compress=True)
src=j/"parser-ich-callers-v2";std=Path("parser/readers");standard(src,std,["bridge.rs","caller.rs","complete.json","readers.json"])
for f in sorted(src.glob("*/argv.json")):put(f,std/f.relative_to(src))
for f in sorted(src.glob("*/stderr")):put(f,std/f.relative_to(src))
old=j/"parser-ich-callers";standard(old,"exclusions/parser-extern-basename",["bridge.rs","caller.rs","complete.json","readers.json"])
print("data files",sum(f.is_file() for f in output.rglob("*")),"bytes",sum(f.stat().st_size for f in output.rglob("*") if f.is_file()))
