"""Export the allowlisted component experiments and separate dyn-loader witness. No native targets are copied."""
from pathlib import Path
import gzip,hashlib,json
p=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027");j=p/"mixed-registry-only-pilot";s=Path.home()/".cache/ohm-233-position-qualified-20261027/mixed-registry-seed-programs-20261027"
out=p/"parser-components-export";out.mkdir(mode=0o700)
comp=j/"parser-incremental-components"
def put(src,dest,compress=False):
    d=out/dest;v=src.read_bytes();assert src.is_file() and not src.is_symlink()
    if compress or (len(v)>90_000 and src.suffix != ".gz"):
        d=Path(str(d)+".gz");v=gzip.compress(v,6,mtime=0)
    d.parent.mkdir(parents=True,exist_ok=True);assert not d.exists();d.write_bytes(v)
def obj(f):return json.loads(f.read_bytes())
for f in ["bracket-parser-components.py","component-hash-readers.py","component-reader-open-audit.py","inspect-parser-graph.py","inspect-parser-graph-v2.py","inspect-parser-graph-v3.py","parser-graph-kinds.json","collect-parser-components.py"]:
    put(s/f,"programs/"+f)
for f in ["parser-graph.stderr","parser-graph-v2.stderr","parser-components.stdout","parser-components.stderr","parser-graph-v3.stdout","parser-graph-v3.stderr"]:put(s/f,"run-logs/"+f)
for f in ["design.json","results.json","complete.json"]:put(comp/f,"cargo/"+f)
for a in ("A","B"):
    d=comp/a;root=Path("cargo")/a;rows=obj(comp/"results.json")[a]
    for state in ["train-original",*rows.keys()]:
        for file in ["result.json","parser.root.txt","session.json","stdout","stderr"]:
            f=d/state/file
            if f.exists():put(f,root/state/file,compress=file in ("stdout","stderr"))
        if state=="train-original":continue
        r=rows[state];logical=Path(r["rmeta"]);phys=d/state/"physical/target"/logical.relative_to(p/"native-target");assert hashlib.sha256(phys.read_bytes()).hexdigest()==r["rmeta_sha256"]
        raw=Path("raw-rmeta")/(r["rmeta_sha256"]+".rmeta")
        if not (out/Path(str(raw)+".gz")).exists():put(phys,raw,compress=True)
    for d,base in [(j/"parser-component-callers"/a,Path("ordinary")/a),(j/"parser-component-open-audit"/a,Path("syscall-audit")/a)]:
        for file in ["complete.json","readers.json","bridge.rs","caller.rs"]:put(d/file,base/file)
        for f in sorted(d.iterdir()):
            if not f.is_dir() or not(f/"argv.json").is_file():continue
            for n in ["argv.json","stderr","stdout","decoded-images.json","observed-paths.json","selected-syscalls.json","rmeta.root.txt","rlib.root.txt"]:
                if(f/n).exists():put(f/n,base/f.name/n)
gr=j/"parser-component-graph-edges-v3";put(gr/"comparison.json","graph/comparison.json")
for f in sorted(gr.glob("*.json.gz")):put(f,"graph/"+f.name)
print(sum(p.is_file() for p in out.rglob("*")),sum(p.stat().st_size for p in out.rglob("*") if p.is_file()))
