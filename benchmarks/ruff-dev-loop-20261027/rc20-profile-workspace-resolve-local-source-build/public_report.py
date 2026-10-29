"""Run the original per-command verifier and remove the verified private workspace prefix from serde stderr."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy


def data(p):
    return json.loads(p.read_bytes())


def stream_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def project(raw, reporter):
    checked=runpy.run_path(str(reporter))["project"](raw)
    view=Path(data(raw/"wall/replay-config.json")["scratch"])/"arena"
    digest = {}
    for mode, stream in checked["ordinary_streams"].items():
        stage=raw/"wall/results"/("toml-"+mode+"-v1")
        expected={}
        normalized=0
        for arm in "AB":
            if mode=="test":
                records=[json.loads(line) for line in (stage/arm/"99-terminal.jsonl").read_bytes().splitlines()]
                exe,=[Path(r["executable"]) for r in records if r["reason"]=="compiler-artifact" and r.get("executable") and r["target"]["name"]=="serde"]
                rel=exe.relative_to(view).as_posix()
                assert rel in checked["products"]["wall-test"]["files"] and exe.is_absolute()
                expected[arm]=(str(exe),"<workspace-view>/"+rel)
        for event,cmd in zip(checked["chronology"][mode],stream):
            arm=event["arm"]
            stem=stage/arm/(f'{event["pair"]:02}-'+event["phase"])
            native=data(stem.with_suffix(".json"))
            for name in ("stdout","stderr"):
                sha=stream_sha(cmd[name])
                assert native[name]==sha
                cmd[name+"_sha256"]=sha
            if mode=="test":
                before,after=expected[arm]
                lines=cmd["stderr"].splitlines(keepends=True)
                assert len(lines)==2 and lines[1]=="  Executable tests/serde.rs ("+before+")\n"
                cmd["stderr"]=lines[0]+"  Executable tests/serde.rs ("+after+")\n"
                normalized+=1
        digest[mode]={"verified_literal_path_substitutions":normalized, "occurrences":len(stream)}
    checked["public_stream_projection"]=digest
    if str(view) in json.dumps(checked):raise ValueError("unprojected view path")
    return checked


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("raw_output",type=Path)
    p.add_argument("--reporter",type=Path,default=Path(__file__).resolve().parent.with_name("rc20-profile-workspace-resolve-local-rerun")/"report.py")
    a=p.parse_args();print(json.dumps(project(a.raw_output,a.reporter),indent=2,sort_keys=True))
