"""Reconstruct the separately acquired, untimed resolver logging and actual native launches."""
import argparse
import collections
import json
from pathlib import Path
import re
import runpy

HERE=Path(__file__).resolve().parent
P=runpy.run_path(str(HERE/"project.py"))
N=P["NATIVE"]
FULL="resolve_with_registry:resolve_with_previous:register_patch_entries:"
HIT="reusing the cached workspace resolution"
TAGS=("00-prepare","01-edited","02-restored","03-settled","04-reverse","05-repeat","06-restore","07-repeat","99-terminal")
EDITS={"01-edited","02-restored","04-reverse","06-restore"}


def require(condition,description):
    if not condition:
        raise ValueError(str(description))


def capture(root):
    directory=root/"h8-rows-v1"
    archive=P["verify_archive"](root/"h8-native-v1.tgz",directory)
    require((directory/"exit").read_text().strip()=="0" and not (directory/"worker.stderr").read_bytes(),"native mechanism execution")
    source=(directory/"bench.py").read_bytes()
    require(source==(root/"bench.py").read_bytes() and (directory/"design.md").read_bytes()==(root/"design.md").read_bytes(),"mechanism design/worker")
    output={"archive":archive,"worker_sha256":P["sha"](source),"design_sha256":P["sha"]((root/"design.md").read_bytes()),"modes":{},
            "index":{p.relative_to(directory).as_posix():P["sha"](p.read_bytes()) for p in sorted(directory.rglob("*")) if p.is_file()}}
    for mode in ("build","test"):
        p=directory/("toml-"+mode+"-v1")
        terminal=P["json_file"](p/"terminal.json")
        data={"terminal":terminal,"commands":{}}
        for q in sorted(p.glob("*/*.jsonl")):
            arm=q.parent.name
            tag=q.stem
            d=q.parent
            env=P["json_file"](d/"enrollment.json")["env"]
            view=str(Path(env["RUSTUP_HOME"]).parent)
            raw=P["json_file"](d/(tag+".json"))
            tb=(d/(tag+".exec")).read_bytes()
            err=(d/(tag+".stderr")).read_bytes()
            clean=lambda txt:P["normal"](txt,view)
            data["commands"][arm+"/"+tag]={"full":raw["full"],"hits":raw["hits"],"files":raw["files"],"oracle":raw["oracle"],
                    "events":N["native_execs"](tb),"stdout":clean(q.read_text()),"stderr":clean(err.decode()),
                    "stderr_sha256":P["sha"](err),"trace_sha256":P["sha"](tb),"stdout_sha256":P["sha"](q.read_bytes())}
        output["modes"][mode]=data
    return output


def verify(data,wall):
    out={}
    require(data["archive"]["members"]==len(data["index"]),"all independent mechanism archive members")
    for mode,m in data["modes"].items():
        cmds=m["commands"]
        roster_set={"C/00-prepare","C/00-frozen"}|{a+"/"+s for a in "AB" for s in TAGS}
        require(set(cmds)==roster_set,"all distinct mechanism calls")
        controls=[]
        total=collections.Counter()
        fids=cmds["C/00-frozen"]["files"]
        baseline=wall["modes"][mode]["controls"]["C/00-frozen"]
        require(fids.keys()==baseline["files"].keys(),"same named products between the independent logging and wall runs")
        for label,item in cmds.items():
            arm,stage=label.split("/")
            rawid="toml-"+mode+"-v1/"+label
            for ext,field in ((".stderr","stderr_sha256"),(".exec","trace_sha256"),(".jsonl","stdout_sha256")):
                require(data["index"][rawid+ext]==item[field],"mechanism raw binding")
            lines=item["stderr"].splitlines()
            full=[i for i,l in enumerate(lines,1) if FULL in l]
            hits=[i for i,l in enumerate(lines,1) if HIT in l]
            require((len(full),len(hits))==(item["full"],item["hits"]) and (full or hits),"all observed resolver calls")
            if stage in EDITS:
                require((len(full)>0)==(arm=="A"),"all genuine edits select the expected resolver path")
                total[arm+"_edited_commands"]+=1
                total[arm+"_edited_full"]+=len(full)
                total[arm+"_edited_hits"]+=len(hits)
            elif stage in {"03-settled","05-repeat","07-repeat","99-terminal","00-frozen"}:
                require(not full and hits,"settled lookup")
            total["commands"]+=1
            typed=list(map(json.loads,item["stdout"].splitlines()))
            require(typed[-1]=={"reason":"build-finished","success":True},"native verdict")
            acts=[j for j in typed if j["reason"]=="compiler-artifact"]
            require({x.removeprefix("<arena>/") for a in acts for x in a["filenames"]}==item["files"].keys() and item["files"]==fids and item["oracle"]==baseline["oracle"], "complete within-run files and real caller")
            es=item["events"]
            workers=(sum(N["is_compile"](e) for e in es),sum(N["is_link"](e) for e in es))
            expect=((1,0) if mode=="build" else (15,6)) if label=="C/00-prepare" else (0,0)
            require(workers==expect and all(a["fresh"]==(label!="C/00-prepare") for a in acts),"actual native work")
            if label!="C/00-prepare":
                require([v["program"] for v in es]==["cargo","cargo"],"no other native child")
            if arm!="C" and stage not in ("00-prepare","99-terminal"):
                controls.append({"arm":arm,"tag":stage,"full":len(full),"hits":len(hits)})
        require(sorted(controls,key=lambda o:(o["arm"],o["tag"]))==sorted(m["terminal"]["controls"],key=lambda o:(o["arm"],o["tag"])),"authentic controller's complete controls")
        total=dict(total)
        total["different_product_sha256_between_independent_common_warmups"]={
            path:{"wall":baseline["files"][path],"logging":h} for path,h in fids.items() if h!=baseline["files"][path]}
        out[mode]=total
    return out


if __name__=="__main__":
    q=argparse.ArgumentParser(description=__doc__)
    q.add_argument("--capture",type=Path)
    q.add_argument("--output",type=Path)
    args=q.parse_args()
    if args.capture:
        require(args.output is not None and not args.output.exists(),"new mechanism projection required")
        P["emit"](args.output,capture(args.capture.resolve()))
    else:
        import gzip
        load=lambda name:json.loads(gzip.decompress((HERE/name).read_bytes()))
        print(json.dumps(verify(load("native-mechanism.json.gz"),load("wall-native.json.gz")),sort_keys=True,indent=2))
