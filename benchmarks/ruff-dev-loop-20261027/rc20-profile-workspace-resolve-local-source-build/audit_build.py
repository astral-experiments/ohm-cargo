"""Compare two real source-build kernel traces against the typed Cargo outputs."""
import argparse
import ast
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy

ROOT=Path(__file__).resolve().parent
NATIVE_DIGEST="6a2137f2fd5524af8ef9f2b771881a27571e707ae11d10bbaec1eb36b4367a68"


@lru_cache(None)
def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def audit(builds, traced, sdk, alias, decoder):
    if digest(decoder)!=NATIVE_DIGEST:
        raise ValueError("wrong published strace decoder")
    functions=runpy.run_path(str(decoder))
    native=functions["native_execs"]
    receipt=json.loads((builds/"build-receipt.json").read_bytes())
    sdk=sdk.resolve()
    tool=sdk/"bin/rustc"
    assert digest(tool)==receipt["sdk_rustc_sha256"]
    compressed=traced.suffix==".gz"
    with (gzip.open if compressed else open)(traced,"rb") as f:raw=f.read()
    rows=native(raw);lines=raw.decode().splitlines()
    def filename(row):
        line=lines[row["lines"][0]-1]
        m=re.search(r'execve(?:at)?\((?:[^,]+, )?("(?:[^"\\]|\\.)*")',line)
        if not m:raise ValueError("missing kernel executable name")
        return Path(ast.literal_eval(m[1]))
    def physical(path):
        return sdk/path.relative_to(alias) if alias is not None and path.is_relative_to(alias) else path
    args=receipt["common_build_args"]
    positions=[i for i,r in enumerate(rows) if r["program"]=="cargo" and r["cargo_args"]==args]
    assert len(positions)==2
    subjects=[]
    for arm,start in zip("AB",positions):
        stop=next(i for i in range(start+1,len(rows)) if rows[i]["program"]=="cargo" and
                  rows[i]["cargo_args"]==["-Vv"] and filename(rows[i]).parent.name=="current")
        group=rows[start:stop]
        assert group[0]["cargo_args"]==args and group[1]["cargo_args"]==args[1:]
        calls=[r for r in group if functions["is_compile"](r)]
        assert calls and all(digest(physical(filename(r)))==digest(tool) for r in calls)
        links=Counter()
        for row in group:
            if row["program"] not in ("ld","ld.bfd","ld.lld","rust-lld") or not row["output_argument"]: continue
            p=physical(filename(row)); rel=p.resolve()
            role="sdk/"+p.relative_to(sdk).as_posix() if p.is_relative_to(sdk) else "system/"+p.name
            links[(role,digest(rel))]+=1
        rawout=builds/arm/"stdout.jsonl"
        if rawout.exists():
            stream=rawout.read_bytes()
        else:
            with gzip.open(str(rawout)+".gz","rb") as f:stream=f.read()
        reports=[json.loads(line) for line in stream.splitlines()]
        assert reports[-1]=={"reason":"build-finished","success":True}
        product=[r for r in reports if r["reason"]=="compiler-artifact"]
        final,=[r for r in product if r["target"]["name"]=="cargo" and r["target"]["kind"]==["bin"] and r["executable"]]
        assert not final["fresh"]
        image=digest(builds/arm/"cargo")
        assert image==receipt["arms"][arm]["binary_sha256"]
        subjects.append({"arm":arm,"cargo":image,"rustc":len(calls),"typed_artifacts":len(product),
                         "arguments":sorted([r["crate"],r["argv_sha256"]] for r in calls),
                         "linkers":[{"role":k,"sha256":sha,"count":n} for (k,sha),n in sorted(links.items())]})
    a,b=subjects
    return {"arms":subjects,"common_compiler_arguments":sum((Counter(x[1] for x in a["arguments"]) &
            Counter(x[1] for x in b["arguments"])).values()), "same_native_tools":a["linkers"]==b["linkers"],
            "reported_full_version_equal":receipt["arms"]["A"]["version"]==receipt["arms"]["B"]["version"]}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("builds","trace","sdk"):p.add_argument("--"+n,required=True,type=Path)
    p.add_argument("--captured-sdk-alias",type=Path,help="literal original SDK alias, only if its private mount has ended")
    p.add_argument("--decoder",type=Path,default=ROOT.with_name("rc20-profile-workspace-resolve-wall")/"native_execs.py")
    x=p.parse_args();print(json.dumps(audit(x.builds,x.trace,x.sdk,x.captured_sdk_alias,x.decoder),indent=2,sort_keys=True))
