"""Read native outcome receipts from a finished private fixture. Does not launch a compiler."""
import json,hashlib,sys
from pathlib import Path
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def one(f):
    p=f.parent;subject=json.loads((p/"subjects.json").read_bytes())
    rows=json.loads(f.read_bytes())
    for row in rows:
        d=p/row["phase"]
        jobfile=d/"jobs.jsonl"; raw=[json.loads(l) for l in jobfile.read_text().splitlines()] if jobfile.exists() else []
        assert [v[0] for v in raw]==row["true_compilers"]
        assert not any("-Zlink-only" in args for _, args in raw)
        dep=d/"rustc.d";assert (b"ohm-foreign-span-bytes" in dep.read_bytes())==row["marker"]
        art=[j for l in (d/"stdout").read_text().splitlines() if (j:=json.loads(l)).get("reason")=="compiler-artifact"]
        assert next(x["fresh"] for x in art if x["target"]["name"]=="app")==row["fresh"]
        row["raw_sha256"]={"rustc_depinfo":sha(dep),"cargo_stdout":sha(d/"stdout"),"cargo_stderr":sha(d/"stderr"),"rustc_job_argv":sha(jobfile) if jobfile.exists() else None}
        row["cargo_artifact_fresh"]={x["target"]["name"]:x["fresh"] for x in art}
        if row["phase"]=="synchronized":
            row["replacement"]=json.loads((d/"replacement.json").read_text())
    variant=p.name.split("-")[1]
    n=p/"native.log"; apps=sum(row["true_compilers"].count("app") for row in rows)
    forced=None
    if p.name.endswith("-inc"):
        forced=json.loads((p/"forced-same-operand/result.json").read_text());apps+=1
    markers=[line.split()[1:] for line in n.read_text().splitlines()]
    assert len(markers)==apps and all(v==[variant,subject["delta"][2:]] for v in markers)
    return {"subjects":subject,"rows":rows,"forced_same_operand":forced,"actually_loaded_app_diagnostic":len(markers)}
def main(root):
    return {f.parent.name:one(f) for f in sorted(Path(root).glob("*/results.json"))}
if __name__=="__main__":print(json.dumps(main(sys.argv[1]),indent=2))
