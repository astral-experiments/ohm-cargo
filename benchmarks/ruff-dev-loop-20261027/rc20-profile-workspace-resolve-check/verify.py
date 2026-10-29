"""Recompute the paired scores and cross-check the native evidence in records.tgz."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tarfile
import tempfile
import tomllib

HERE=Path(__file__).resolve().parent
EXEC=runpy.run_path(str(HERE/"native_execs.py"))
sha=lambda b: hashlib.sha256(b).hexdigest()
parse=lambda p: json.loads(p.read_bytes())
subjects=parse(HERE/"subjects.json")
ARTIFACT="c33b1d5ffd2965e44df1c03f6746e98579be549601a576bf999aec3988e29a13"
TYPED="8754fa52d61cadd35e2ac62ed52d8904158e47eb79de0dffff7f8f243559a79d"
MESSAGE="unresolved import `ruff_text_size::OhmNonexistentProfileInput`"


def must(ok, reason):
    if not ok:
        raise ValueError(reason)


def subjects_ok():
    manifest=gzip.decompress((HERE/"ruff-Cargo.toml.gz").read_bytes())
    lock=gzip.decompress((HERE/"ruff-Cargo.lock.gz").read_bytes())
    hunk=b"[profile.dev.package.salsa]\nopt-level = 3\n\n"
    must(sha(manifest)==subjects["original_manifest_sha256"] and manifest.count(hunk)==1,"original manifest")
    must(sha(manifest.replace(hunk,b""))==subjects["edited_manifest_sha256"],"edited manifest")
    must(sha(lock)==subjects["lock_sha256"] and len(lock)==138994 and len(tomllib.loads(lock.decode())["package"])==553,"lockfile")
    must(sha((HERE/"records.tgz").read_bytes())==subjects["normalized_inputs_sha256"],"archive")
    for path,key in [("historical.patch","patch_sha256"),("design.md","design_sha256"),("reported-statistics.json","original_results_sha256")]:
        must(sha((HERE/path).read_bytes())==subjects[key],path)


def extract(tmp):
    index=json.loads(gzip.decompress((HERE/"original-file-index.json.gz").read_bytes()))
    all_members=index["complete_private_archive"]
    published=index["published_members"]
    must(len(all_members)==446 and len(published)==439,"member counts")
    with tarfile.open(HERE/"records.tgz") as archive:
        seen=set()
        for member in archive:
            parts=Path(member.name).parts
            must(member.isfile() and 1<=len(parts)<=3 and parts[0]=="toml-check-v1" and ".." not in parts,"member path")
            must(member.name not in seen and member.name in published and member.size<3_000_000,"member identity")
            seen.add(member.name)
            raw=archive.extractfile(member).read()
            orig,shown=published[member.name]
            must(orig==all_members[member.name] and sha(raw)==shown,"member hash")
            if re.search(r"/\d\d-(edit|repeat)\.(stderr|stdout|json)$",member.name) or member.name.endswith("/terminal.json"):
                must(orig==shown,"unmodified measured streams or terminal")
            p=tmp/member.name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(raw)
    must(seen==set(published),"archive inventory")


def verify_native(root):
    folder=root/"toml-check-v1"
    hashes=subjects["build"]
    for arm,tool in [("A",hashes["baseline_binary"]),("B",hashes["cargo_sha256"]),("C",hashes["baseline_binary"])]:
        data=parse(folder/arm/"enrollment.json")
        must(data["cargo"]==tool and data["orig"]==subjects["original_manifest_sha256"] and data["edit"]==subjects["edited_manifest_sha256"],"arm enrollment")
        must(data["lock"]==subjects["lock_sha256"] and data["units"]==1 and data["argv"]==["check","-p","ruff_text_size","--locked","--offline"],"graph")
    counters=Counter()
    for trace in sorted(folder.glob("*/*.exec")):
        stem=trace.with_suffix("")
        row=parse(stem.with_suffix(".json"))
        events=EXEC["native_execs"](trace.read_bytes())
        src=[e for e in events if EXEC["is_compile"](e)]
        links=[e for e in events if EXEC["is_link"](e)]
        cold=trace.relative_to(folder).as_posix()=="C/00-prepare.exec"
        if cold:
            must([e["crate"] for e in src]==["ruff_text_size"] and not links,"cold compiler")
        else:
            must([e["program"] for e in events]==["cargo","cargo"] and not links,"unchanged native work")
        counters.update(controls=1,compiles=len(src),links=len(links),execs=len(events))
        lines=[json.loads(s) for s in stem.with_suffix(".jsonl").read_text().splitlines()]
        artifacts=[a for a in lines if a["reason"]=="compiler-artifact"]
        must(len(artifacts)==1 and lines[-1]=={"reason":"build-finished","success":True},"compiler records")
        a=artifacts[0]
        must(a["target"]["kind"]==["lib"] and a["target"]["name"]=="ruff_text_size" and a["fresh"]== (not cold),"artifact freshness")
        must(len(a["filenames"])==1 and row["files"]=={str(Path(a["filenames"][0]).relative_to("/replay")):ARTIFACT},"metadata file")
        must(row["oracle"]==[TYPED,[["E0432",MESSAGE]]],"positive and negative type-checking")
    must(counters=={"controls":12,"compiles":1,"links":0,"execs":27},"full control inventory")
    return dict(counters)


def scores(root):
    cp=subprocess.run([sys.executable,"-IB",HERE/"analyze.py",root,"check"],capture_output=True)
    must(cp.returncode==0,"pair, raw time, stream, or native admission")
    must(cp.stdout==(HERE/"reported-statistics.json").read_bytes(),"all statistics")


def corruptions(root):
    folder=root/"toml-check-v1"
    def change(path, mutate, guard, label):
        raw=path.read_bytes()
        try:
            path.write_bytes(mutate(raw))
            try: guard(root)
            except (ValueError,AssertionError): return
            raise RuntimeError("accepted mutation: "+label)
        finally:
            path.write_bytes(raw)
    change(folder/"A/00-edit.stderr",lambda b:b+b"changed\n",scores,"wall stream")
    change(folder/"B/30-edit.json",lambda b:b.replace(b'"ns": ',b'"ns": 1'),scores,"raw clock")
    def reorder(b):
        t=json.loads(b);t["events"][0],t["events"][1]=t["events"][1],t["events"][0]
        return json.dumps(t).encode()
    change(folder/"terminal.json",reorder,scores,"time or arm order")
    change(folder/"B/02-restored.json",lambda b:b.replace(ARTIFACT.encode(),b"0"*64),verify_native,"metadata contents")
    change(folder/"A/99-terminal.json",lambda b:b.replace(b"E0432",b"E0000"),verify_native,"incorrect invalid consumer")
    change(folder/"C/00-prepare.exec",lambda b:b.replace(b"--crate-name",b"--false-name"),verify_native,"original compiler")


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--self-test",action="store_true")
    args=cli.parse_args()
    subjects_ok()
    with tempfile.TemporaryDirectory(prefix="ohm-ruff-check-") as d:
        work=Path(d)
        extract(work)
        print(verify_native(work))
        scores(work)
        if args.self_test:
            corruptions(work)
            print("Rejected six changes to timing, metadata, the invalid verdict and native work.")
    print("Verified 128 whole-command times, the complete 32-pair schedule and all three paired intervals.")
