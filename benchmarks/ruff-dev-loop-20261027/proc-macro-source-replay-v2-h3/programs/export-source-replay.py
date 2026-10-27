"""Seal selected input bytes and native outcome receipts, without copying build caches or user credentials."""
from pathlib import Path
import gzip, hashlib, json, os, shutil, sys

label=sys.argv[1]
assert label in {"v2","v3"}
X=Path.home()/".cache/ohm-233-position-qualified-20261027"
P=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027");J=P/"mixed-registry-only-pilot"
S=X/"mixed-registry-seed-programs-20261027"; W=X/"mixed-native-abc-protocol-h3-v2"
O=J/("public-macro-source-replay-"+label);O.mkdir(mode=0o700)
def sha(f):
    with f.open("rb") as h:return hashlib.file_digest(h,"sha256").hexdigest()
def dump(f,v):f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def put(f,rel):
    assert f.is_file(), f
    dest=O/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
def zipf(f,rel):
    dest=O/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    with f.open("rb") as fi,dest.open("wb") as fo,gzip.GzipFile(fileobj=fo,mode="wb",mtime=0,filename="") as gz:shutil.copyfileobj(fi,gz)
def topic(root,sub,files): 
    for n in files:put(root/n,Path(sub)/n)

imgs=P/("parse-source-replay-"+label)
for n in ("receipt.json","verified.sha","inputs.json","change.patch"):
    if (imgs/n).is_file():put(imgs/n,Path("image")/n)
dump(O/"image/binary.json",{"driver_sha256":sha(imgs/"candidate-driver.so"),"driver_bytes":(imgs/"candidate-driver.so").stat().st_size})
programs=["fixed-ruff-parser-source","audit-fixed-source-readers","inspect-fixed-parser-wire","repeat-fixed-parser","minimal-proc-source-hash-v2","minimal-transient-positions-v2","minimal-proc-hygiene-sites","run-source-replay-rmake","qualify-parsed-source","verify-macro-real-paths","check-parse-cache-upgrade","bracket-parse-programmatic-v2","bracket-hygiene-call-site","export-source-replay"]
for n in programs:put(S/(n+".py"),Path("programs")/(n+".py"))
for f in ("common.py","namespace.py","state.py","processes.py","runner-binding.json","plan.json","analyze.py","parser.patch"):put(W/f,Path("programs/workspace")/f)
for name in ("incremental-proc-macro-source-tracked-final","incremental-proc-macro-source-hygiene-final"):
    t=S/("rmake-"+name);topic(t,Path("run-make-fixtures")/name,["runner.json",*["fixture/"+p.name for p in sorted((t/"fixture").glob("*.rs"))]])
mini=[("source-hash","minimal-proc-source-hash-v2"),("byte-position","minimal-transient-positions-v2"),("hygiene","minimal-hygiene-sites")]
for title,stem in mini:
    source=J/("fixed-"+label+"-"+stem)
    assert (source/"evidence/results.json").is_file(),source
    for f in sorted((source/"evidence").rglob("*")):
        if not f.is_file():continue
        rel=Path("mini")/title/f.relative_to(source/"evidence")
        if f.suffix==".rlib" or f.name in {"app","user","caller"}:continue
        assert f.stat().st_size<750000,f
        put(f,rel)

for topicname,root in [("real-source-and-remap",J/("macro-real-path-control-"+label)),("upgrade",J/("parse-cache-upgrade-"+label))]:
    topic(root,topicname,["results.json","complete.json"])
    for d in root.iterdir():
        if d.is_dir() and (d/"status.json").exists():
            for name in ("argv.json","stdout","stderr","status.json","raw.rmeta"):
                if (d/name).is_file():put(d/name,Path(topicname)/d.name/name)

for root in [J/("parse-source-runmake-"+t) for t in ([label,"hygiene-final-"+label] if label=="v3" else [label])]:
    topic(root,Path("run-makes")/root.name,["results.json"])
    for d in root.iterdir():
        if d.is_dir():
            for name in ("runner.stdout","runner.stderr"):
                if (d/name).is_file():put(d/name,Path("run-makes")/root.name/d.name/name)
if label=="v2":
    for n in ("bracket-parsed-source-no-tsparse-parent-r2","bracket-parsed-source-no-tsparse-v2-r2","bracket-parsed-source-global-ctxt-v2","bracket-parsed-source-global-ctxt-parent"):
        root=J/n;topic(root,Path("brackets")/n,["results.json","complete.json"])
        for d in root.iterdir():
            if d.is_dir():
                for name in ("maker.rs","rmake.rs","producer.rs","bridge.rs","caller.rs","late.rs"):
                    if (d/name).is_file():put(d/name,Path("brackets")/n/d.name/name)

full=J/("fixed-source-ruff-"+label);read=J/("fixed-source-readers-"+label)
topic(full,"ruff",["results.json","subject.json"])
for f in ("complete.json",):
    if (full/f).is_file():put(full/f,Path("ruff")/f)
log=J/("fixed-source-ruff-"+label+"-launch.log")
if log.is_file():put(log,Path("ruff")/"launch.log")
topic(read,"ruff/readers",["readers.json","complete.json","bridge.rs","caller.rs"])
for d in read.iterdir():
    if d.is_dir() and (d/"decoded-images.json").is_file():
        topic(d,Path("ruff/readers")/d.name,["argv.json","decoded-images.json","stderr","stdout"])
for name in ["train","fresh","warm","empty"]:
    d=full/"records"/name;sub=Path("ruff/records")/name
    topic(d,sub,["result.json","argv.json","status.json","parser-header/stdout","parser-header/stderr"])
    zipf(d/"stdout",sub/"cargo.stdout.jsonl.gz");zipf(d/"stderr",sub/"cargo.stderr.gz")
    if name in {"warm","empty"}:
        zipf(d/"parser.rmeta",sub/"parser.rmeta.gz")
        topic(d,sub,["native-ruff/stdin","native-ruff/argv.json","native-ruff/status.json","native-ruff/stderr","native-ruff/stdout"])
if (repeat:=J/("fixed-source-ruff-"+label+"-repeat")).exists():
    topic(repeat,"ruff/same-history-repeats",["results.json","complete.json"])
    for name in ("warm","empty"):
        for which in ("original","repeat"):
            parent="archived-"+name+"-"+which
            topic(repeat/parent,Path("ruff/same-history-repeats")/parent,["result.json","sections.txt"])
            zipf(repeat/parent/"archived-lib.rmeta",Path("ruff/same-history-repeats")/parent/"archived-lib.rmeta.gz")
        d=repeat/"records"/name;topic(d,Path("ruff/same-history-repeats")/name,["result.json","argv.json","status.json","native-ruff/stdout"])
if (wire:=J/("fixed-source-ruff-"+label+"-wire")).exists():
    topic(wire,"ruff/wire",["results.json","inputs.json","classification.json"])
    for m in ("plain","stats"):
        for h in ("warm","empty"):
            d=wire/(m+"-"+h)/"process";topic(d,Path("ruff/wire")/(m+"-"+h),["stdout","stderr","argv.json","status.json"])
print(O,flush=True)
