"""Verify both exact Ruff revisions, their lockfile, and the complete semantic manifest difference."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

old="716260bf10d7ae1d965ed9b22653e57fbc960582"
new="2d6ce561250a464e1fa231ef30e54d0f029f76a4"
def git(repo,*args):
    return subprocess.check_output(["git","-C",repo,*args])
def flatten(data,trail=()):
    if isinstance(data,dict):
        for k,v in data.items():
            yield from flatten(v,(*trail,k))
    elif isinstance(data,list) and data and isinstance(data[0],dict):
        for i,v in enumerate(data):
            yield from flatten(v,(*trail,v.get("name",str(i))))
    else:
        yield ".".join(trail),data
def subject(repo):
    assert git(repo,"rev-parse",new+"^").decode().strip() == old
    paths=git(repo,"diff","--name-only",old,new).decode().splitlines()
    assert len(paths) == 30 and paths.count(".github/workflows/ci.yaml") == 1
    lock=git(repo,"show",old+":Cargo.lock")
    assert git(repo,"show",new+":Cargo.lock") == lock
    rows=[]
    for path in paths:
        a,b=[git(repo,"show",rev+":"+path) for rev in (old,new)]
        if path==".github/workflows/ci.yaml":
            continue
        assert Path(path).name=="Cargo.toml"
        first,second=[dict(flatten(tomllib.loads(t.decode()))) for t in (a,b)]
        edits={k:[first.get(k),second.get(k)] for k in sorted(first|second) if first.get(k)!=second.get(k)}
        assert edits and set(edits) <= {"lib.test","lib.doctest","workspace.metadata.cargo-shear.ignored","package.metadata.cargo-shear.ignored"}
        rows.append({"path":path,"old":hashlib.sha256(a).hexdigest(),"new":hashlib.sha256(b).hexdigest(),"edits":edits})
    selected=[r for r in rows if any(k in r["edits"] for k in ("lib.test","lib.doctest"))]
    assert len(rows)==29 and len(selected)==27
    return {"parent":old,"commit":new,"paths":paths,"lock_sha256":hashlib.sha256(lock).hexdigest(),
            "source_tree_sha256":{rev:hashlib.sha256(git(repo,"ls-tree","-r","--full-tree",rev)).hexdigest() for rev in (old,new)},
            "selected_manifests":len(selected),"manifests":rows}
if __name__=="__main__":
    value=subject(Path(sys.argv[1]))
    if "--emit" in sys.argv:
        print(json.dumps(value,sort_keys=True,indent=2))
    else:
        assert value==json.loads(Path(__file__).with_name("subject.json").read_bytes())
        print("Verified both complete Ruff trees, the unchanged Cargo.lock, and selection changes in 27 of 29 manifests.")
