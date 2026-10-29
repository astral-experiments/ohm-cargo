"""Classify already-completed build and test commands without invoking a compiler."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re
import sys


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def select(directory):
    native=json.loads((directory/"native.json").read_bytes())
    status=json.loads((directory/"status.json").read_bytes())
    assert native["root_exit"]==status["rc"]==0 and not any(native["process_exit"].values())
    assert digest(directory/"stderr")==status["stderr_sha256"]
    assert digest(directory/"cargo.jsonl")==status["stdout_sha256"]
    messages=[json.loads(row) for row in (directory/"cargo.jsonl").read_bytes().splitlines()]
    assert messages[-1]=={"reason":"build-finished","success":True}
    assets=[x for x in messages if x["reason"]=="compiler-artifact"]
    compiled=[];links=[];counts=Counter()
    for event in native["events"]:
        argv=event["argv"];role=event["role"];counts[role]+=1
        assert hashlib.sha256(b"\0".join(a.encode() for a in argv)+b"\0").hexdigest()==event["argv_sha256"]
        if role in ("rustc-full","rustc-link-only"):
            compiled.append(dict(crate=event["target"],mode=role,
                                 types=[argv[i+1] for i,v in enumerate(argv) if v=="--crate-type"],
                                 test="--test" in argv,stem=next((v.split("=",1)[1] for v in argv if v.startswith("extra-filename=")),""),
                                 src=next((v[v.index("crates/"):] for v in argv if (v.startswith("crates/") or "/crates/" in v) and v.endswith(".rs")),None),
                                 argv_sha256=event["argv_sha256"]))
        elif role=="stock-wild":
            assert argv[argv.index("-o")+1]==event["out"]
            links.append(dict(output=Path(event["out"]).name,argv_sha256=event["argv_sha256"]))
    assert counts["gcc"]==counts["collect2"]==counts["stock-wild"]==len(links)
    text=(directory/"stderr").read_text()
    raw_dirty=[l for l in text.splitlines() if "fingerprint:     dirty: " in l]
    reasons=Counter()
    qualified=[]
    for l in raw_dirty:
        pkg,target=re.search(r'package_id=([\w-]+) .*?target="([^"]+)"',l).groups()
        tail=l.split("fingerprint:     dirty: ",1)[1]
        item=None
        if (m:=re.search(r"FsStatusOutdated\(StaleDepFingerprint \{ unit: UnitIndex\((\d+)\) \}\)",tail)):
            item=dict(kind="StaleDepFingerprint",dependency_unit=int(m[1]))
        elif (m:=re.search(r'FsStatusOutdated\(StaleItem\(MissingFile \{ path: "[^"]*/([^/]+\.d/ohm-foreign-span-bytes)" \}\)\)',tail)):
            item=dict(kind="MissingForeignSpanSentinel",sentinel=m[1])
        if item:
            qualified.append(dict(package=pkg,target=target,**item));reasons[item["kind"]]+=1
        else:
            reasons[tail.split(" ",1)[0]]+=1
    sample={name:[x["fresh"] for x in assets if x["target"]["name"]==name] for name in ("ruff_python_ast","ruff_python_index","ron")}
    return dict(raw_sha256={name:digest(directory/name) for name in ("native.json","cargo.jsonl","stderr","status.json")},
                cargo_roles=counts,typed=dict(total=len(assets),fresh=sum(x["fresh"] for x in assets)),
                typed_known_units=sample,dirty_categories=reasons,dirty_rows=qualified,
                rustcs=compiled,wild_outputs=links,
                newer_dependency_log_mentions=len(re.findall(r"dependency on `[^\n]+` is newer than we are",text)),
                all_physical_processes_succeeded=True)


def main():
    root,out=map(Path,sys.argv[1:])
    report={}
    for mode in ("build","test"):
        directory=root/("qualified-native-"+mode)
        report[mode]={n:select(directory/n) for n in ("unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2",
                                                            "child-edit","child-unchanged-1","child-unchanged-2")}
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")


if __name__=="__main__":
    main()
