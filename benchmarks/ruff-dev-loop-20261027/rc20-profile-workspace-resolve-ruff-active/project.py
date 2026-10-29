"""Project terminal native runs, resolving split execs before path redaction."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy

HERE = Path(__file__).resolve().parent
native_execs = runpy.run_path(str(HERE / "native_execs.py"))["native_execs"]
FULL = "resolve_with_registry:resolve_with_previous:register_patch_entries:"
HIT = "reusing the cached workspace resolution"
WILD = "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serialize(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def check(condition, description):
    if not condition:
        raise ValueError(str(description))


def write(path, value):
    value = serialize(value)
    path.write_bytes(gzip.compress(value, mtime=0) if path.suffix == ".gz" else value)


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def markers(stderr):
    return [i for i, line in enumerate(stderr.splitlines(), 1) if FULL in line], [
        i for i, line in enumerate(stderr.splitlines(), 1) if HIT in line
    ]


def capture(root, sdk, proxy_dir):
    view = str(root / "holdout-view")
    registry_alias = re.compile(r"(<arena>/cargo-home/registry/(?:src|cache|index)/)[^/\s\x22]+/")
    def scrub(s):
        s = s.replace(view, "<arena>").replace(str(sdk), "<sdk>").replace(str(proxy_dir), "<proxies>")
        s = s.replace(str(root / "active_ruff.py"), "<driver>/active_ruff.py")
        s = registry_alias.sub(r"\1<registry>/", s)
        check(str(root) not in s and str(proxy_dir) not in s, "unmapped private path")
        return s
    def process(record, version):
        row = read(record / "row.json")
        raw = {p.name:p.read_bytes() for p in record.iterdir() if p.name != "row.json"}
        check(sha(raw["stdout"]) == row["stdout"] and sha(raw["stderr"]) == row["stderr"]
              and sha(raw["exec"]) == row["trace"], record.name)
        check(native_execs(raw["exec"]) == row["events"], "native argv/line identities differ")
        lines = raw["exec"].decode().splitlines()
        for event in row["events"]:
            match = re.search(r'execve(?:at)?\((?:[^\x22,]+, )?(\x22(?:[^\x22\\]|\\.)*\x22)', lines[event["lines"][0]-1])
            check(match, event["lines"])
            actual = ast.literal_eval(match[1])
            if event["program"] == "ld.bfd":
                check(Path(actual).resolve(strict=True) == (sdk / WILD).resolve(strict=True), "other native linker")
            elif event["program"] == "rustc":
                check(actual == view + "/ru/toolchains/ohm/bin/rustc", "other compiler")
            elif event["program"] == "cargo":
                expected = str(proxy_dir / "cargo") if event["cargo_args"][:1] == ["+ohm"] else view + "/ru/toolchains/ohm/bin/cargo"
                check(actual == expected, "other cargo path")
        contents = {name:scrub(data.decode()) for name, data in raw.items()}
        full,hits=markers(contents["stderr"])
        if version==3:
            check((len(full),len(hits),bool(hits and not full)) ==
                  (row["full_workspace_resolutions"],row["cache_hits"],row["hit"]), "all resolver calls")
        check(serialize(row)==(record/"row.json").read_bytes(), "raw row JSON encoding")
        return {"row":row,"streams":contents,"full_lines":full,"hit_lines":hits}
    result={}
    index={}
    for version in (1,2,3):
        path=root/("active-ruff-v"+str(version))
        key="v"+str(version)
        index[key]={}
        for f in sorted(path.rglob("*")):
            if f.is_dir():
                continue
            check(f.is_file() and not f.is_symlink(), f.name)
            b=f.read_bytes()
            index[key][f.relative_to(path).as_posix()]={"bytes":len(b),"sha256":sha(b)}
        result[key]={}
        for arm_dir in sorted(path.glob("[AB]")):
            arm=arm_dir.name
            result[key][arm]={"commands":{d.parent.name:process(d.parent,version) for d in sorted(arm_dir.glob("*/row.json"))}}
            if (arm_dir/"worker.stderr").exists():
                result[key][arm]["worker_stderr"]=scrub((arm_dir/"worker.stderr").read_text())
    index["source_driver"]={"bytes":(root/"active_ruff.py").stat().st_size,"sha256":sha((root/"active_ruff.py").read_bytes())}
    return result,index


def typed_products(command):
    table={}
    products=command["row"]["products"]
    covered=set()
    for event in map(json.loads,command["streams"]["stdout"].splitlines()):
        if event["reason"]!="compiler-artifact":
            continue
        for filename in event["filenames"]:
            check(filename.startswith("<arena>/"),filename)
            identity=(event["package_id"],event["target"]["name"],tuple(event["target"]["kind"]),Path(filename).suffix)
            relative=filename.removeprefix("<arena>/")
            check(identity not in table and relative not in covered and relative in products,identity)
            covered.add(relative)
            table[identity]={"path":relative,"sha256":products[relative]}
    check(covered==products.keys(), "unbound or lost artifact")
    return table


def compare_products(data):
    cmds={a:d["commands"] for a,d in data["v3"].items()}
    result={}
    def pair(left,right):
        x,y=typed_products(cmds[left[0]][left[1]]),typed_products(cmds[right[0]][right[1]])
        check(x.keys()==y.keys(),(left,right))
        rows=[{"id":[k[0],k[1],list(k[2]),k[3]],"left":x[k],"right":y[k],"exact_bytes":x[k]["sha256"]==y[k]["sha256"]} for k in sorted(x)]
        result["/".join(left)+" :: "+"/".join(right)]=rows
    for name in cmds["A"]:
        pair(("A",name),("B",name))
    for arm in "AB":
        for mode in ("test","check"):
            for l,r in (("01-original","02-repeat"),("03-reverse","04-repeat"),("03-reverse","05-clean-edited"),
                        ("01-original","08-restored"),("08-restored","09-final")):
                pair((arm,mode+"-"+l),(arm,mode+"-"+r))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--captures",required=True,type=Path)
    p.add_argument("--sdk",required=True,type=Path)
    p.add_argument("--proxies",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    args.out.mkdir(exist_ok=False)
    data,index=capture(args.captures.resolve(),args.sdk.resolve(),args.proxies.resolve())
    write(args.out/"streams.json.gz",data)
    write(args.out/"raw-file-index.json.gz",index)
    write(args.out/"product-comparisons.json.gz",compare_products(data))
