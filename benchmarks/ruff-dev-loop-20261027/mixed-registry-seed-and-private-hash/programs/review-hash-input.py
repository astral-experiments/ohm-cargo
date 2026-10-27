"""Save the true warm and clean compiler argv, source histories, fixed inputs and stable Rust decoder output."""
from pathlib import Path
import difflib, hashlib, json, os, sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P, CARGO_HOME, TARGET, SHARED, RUFF, sha, load, dump
from state import FILES, source_clean
from processes import records
root=P/"mixed-registry-only-pilot";prev=root/"ordinary-reciprocal-bc-v1";out=root/"history-input-receipt-v1";out.mkdir()
fixture=hist/"fixture";src={}
for label,st,d in [("warm",hist/"state/build/B",hist/"receipts/build/B/first-edit"),("cold",root/"shared-b-v3/physical",root/"shared-b-v3/build")]:
    ret={}
    for rel in FILES:
        f=st/"inputs"/rel;g=RUFF/rel
        ret[str(rel)]={"live_mounted":sha(f) if f.exists() else None,"underlying_unedited":sha(g),"prerecorded_edited":load(fixture/"manifest.json")["edited"][str(rel)],"previous_unedited":sha(fixture/"original"/rel)}
        assert ret[str(rel)]["live_mounted"]==ret[str(rel)]["prerecorded_edited"] and ret[str(rel)]["underlying_unedited"]==ret[str(rel)]["previous_unedited"]
    args={}
    for _,e,argv in records(d):
        if Path(e).name!="rustc" or "--crate-name" not in argv:continue
        n=argv[argv.index("--crate-name")+1]
        if n not in ("ruff_wasm","ty_wasm","ruff_python_parser"): continue
        assert n not in args
        source=next(t for t in argv if t.endswith("/lib.rs") or t.endswith("src/lib.rs"))
        refs={}
        for i,a in enumerate(argv[:-1]):
            if a!="--extern" or "=" not in argv[i+1]: continue
            name,f=argv[i+1].split("=",1);p=Path(f)
            if not p.is_absolute():continue
            real=st/("target" if p.is_relative_to(TARGET) else "shared")/p.relative_to(TARGET if p.is_relative_to(TARGET) else SHARED)
            if real.is_file():refs[name]={"path":f,"sha256":sha(real)}
        args[n]={"argv":argv,"source_arg":source,"externs":refs,"metadata":[t for t in argv if t.startswith("metadata=")],"incremental":[t for t in argv if t.startswith("incremental=")]}
    assert len(args)==3
    src[label]={"registered_source":load(fixture/"manifest.json"),"current_view":ret,"actual_rustc":args,"source_index":source_clean(),"cargo_json":sha(d/"stdout")}
histories={}
for d in sorted((hist/"receipts/build/B").iterdir()):
    if (d/"receipt.json").is_file():
        row=load(d/"receipt.json");histories[d.name]={k:row[k] for k in ("arm","state","mode","phase","status")}
histories["prospective_cold_B"]={"state":"edited","workspace_units_preexisting":0,"registry_units_fresh":433,"workspace_compiler_units":68}
dump(out/"history.json",histories)
dump(out/"inputs.json",src)
diff={}
for n in ("ruff_python_parser","ruff_wasm","ty_wasm"):
    a,c=(src[k]["actual_rustc"][n] for k in ["warm","cold"])
    op=[(tag,a["argv"][i:j],c["argv"][k:l]) for tag,i,j,k,l in difflib.SequenceMatcher(None,a["argv"],c["argv"],autojunk=False).get_opcodes() if tag!="equal"]
    refs={k:[a["externs"].get(k),c["externs"].get(k)] for k in a["externs"].keys()|c["externs"].keys() if a["externs"].get(k)!=c["externs"].get(k)}
    diff[n]={"argv_differences":op,"changed_direct_inputs":refs,"source_equal":src["warm"]["current_view"]==src["cold"]["current_view"],"source_arg":a["source_arg"]};print(n,op,sorted(refs))
dump(out/"summary.json",diff)
