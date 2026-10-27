"""Inspect independent workspace-cold graphs plus their real ordinary cross-crate callers, retaining every failure."""
import collections, fcntl, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

x=Path.home()/".cache/ohm-233-position-qualified-20261027"
w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P, TARGET, SHARED, CARGO_HOME, FROZEN, SONAME, RUFF, sha, dump, load, need, env
from state import source_binds, source_clean, recipes, gate_free
from namespace import skeleton, spawn_args
from processes import parse
from products import products,compare_context
from witness import audit_json

root=P/"mixed-registry-only-pilot"
out=root/"ordinary-reciprocal-bc-v1"
b=load(w/"runner-binding.json")
states={"cold-B":(root/"shared-b-v3/physical",root/"shared-b-v3/build","B"),
        "cold-C":(root/"shared-c-v3/physical",root/"shared-c-v3/build","C"),
        "warm-B":(hist/"state/build/B",hist/"receipts/build/B/first-edit","B")}

def anon_path(p):
    return "/".join("COMPILER-NAMESPACE" if s.startswith("v2-") and s.endswith("all-native-all") else s for s in Path(p).parts)

def inside(label):
    st,receipt,arm=states[label]
    p=out/label;p.mkdir()
    rows=[json.loads(s) for s in (receipt/"stdout").read_bytes().splitlines()]
    trace=parse(receipt,"build",{},recipes())
    j=audit_json(receipt/"stdout","build")
    prod=products(j,rows,True,True,out/"retained-mixed")
    library={}
    for q in rows:
        if q["reason"]!="compiler-artifact":continue
        for f in q["filenames"]:
            fn=Path(f)
            if fn.suffix not in (".rmeta",".so"):continue
            key=(q["package_id"],q["target"]["name"],anon_path(f))
            library["|".join(key)]={"file":f,"sha256":sha(fn),"fresh":q["fresh"],"features":q["features"],"profile":q["profile"]}
    dump(p/"all-rust-libraries.json",library)
    dump(p/"receipt.json",{"product":prod,"processes":trace,"cargo":b["arms"][arm],
                           "raw_source":str(receipt),"cargo_json":sha(receipt/"stdout")})

def namespace(st,arm,extras=()):
    subj=b["arms"][arm];q=spawn_args(mount,out,st,st/"registry-home",[],Path(subj["cargo"]),Path(subj["driver"]));i=q.index("--")
    binds=[]
    for f,logical in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:
        binds+=["--ro-bind",str(f),str(logical)]
    return [*q[:i],*binds,*source_binds(st),*extras,*q[i:]]

if len(sys.argv)>1:
    inside(sys.argv[1]);sys.exit(0)

with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    assert not out.exists() and all((root/f"shared-{r}-v3/complete.json").is_file() for r in "bc")
    out.mkdir(mode=0o700);mount=skeleton(out)
    index=source_clean();(out/"bridge-canonical").mkdir();(out/"libordinary_bridge_input.rlib").touch()
    shutil.copytree(hist/"bridge-src",out/"bridge-src")
    cfg=env();cfg["PATH"]=load(root/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
    for lab,(st,d,arm) in states.items():
        subprocess.run([*namespace(st,arm),sys.executable,"-B",str(Path(__file__).resolve()),lab],env=cfg,cwd=RUFF,check=True)
    graph={}
    for a,z in [("cold-B","cold-C"),("warm-B","cold-B"),("warm-B","cold-C")]:
        aroot=out/a;zroot=out/z
        ar,br=(load(k/"all-rust-libraries.json") for k in [aroot,zroot])
        need(ar.keys()==br.keys(), ("advertised crate evidence changed",a,z))
        diff={k:[ar[k],br[k]] for k in ar if ar[k]["sha256"]!=br[k]["sha256"]}
        va,vb=(load(k/"receipt.json") for k in [aroot,zroot])
        try:assessment=compare_context(va["product"],vb["product"])
        except ValueError as e:assessment={"mismatch":str(e)}
        mixed={name:{k:[va["product"]["mixed"][name][k],vb["product"]["mixed"][name][k]] for k in ("rmeta_sha256","private_svh","public_svh","stable_crate_id","embedded_object_sha256","normalized_archive_sha256")} for name in ("ruff_wasm","ty_wasm")}
        graph[a+"--"+z]={"library_outputs":len(ar),"different_library_bytes":diff,"full_qualified_or_first_mismatch":assessment,"mixed":mixed}
    dump(out/"comparisons.json",graph)
    sw=x/"mixed-registry-seed-programs-20261027/bridge-status-worker.py";readers=[]
    for crate in ("ruff_wasm","ty_wasm"):
        outputs={}
        def one(action,state_label,input_label=None):
            st,_,arm=states[state_label];d=out/(crate+"-"+action+"-"+state_label+("-from-"+input_label if input_label else ""));d.mkdir()
            extras=["--bind",str(d),str(out/"bridge-canonical")]
            if input_label:extras+=["--ro-bind",str(outputs[input_label]),str(out/"libordinary_bridge_input.rlib")]
            args=[*namespace(st,arm,extras),sys.executable,"-B",str(sw),"--root",str(out),"--action",action,"--crate",crate,"--arm",arm,
                  "--out",str(d/"receipt"),"--binding",str(w/"runner-binding.json"),"--details",str(out/state_label/"receipt.json"),"--flags",str(out/state_label/"receipt.json")]
            z=subprocess.run(args,cwd=RUFF,env=cfg,capture_output=True);(d/"outer.stderr").write_bytes(z.stderr)
            rec=d/"receipt";native=load(rec/"rustc-status.json")["rustc_status"]
            if action=="bridge":
                assert z.returncode==native==0
                outputs[state_label]=d/"libordinary_bridge.rlib"
            value=load(rec/"bridge.json")["runtime"] if z.returncode==0 else None
            readers.append({"crate":crate,"action":action,"state":state_label,"bridge_origin":input_label,"rustc_exit":native,"wrapper_exit":z.returncode,
                            "runtime":value,"argv":load(rec/"argv.json"),"stderr":(rec/"stderr").read_text(),"bridge_from_sha256":sha(outputs[input_label]) if input_label else None})
            dump(out/"readers.json",readers)
        for lab in states:one("bridge",lab)
        for lab in states:
            for source in states:one("caller",lab,source)
    assert source_clean()==index and gate_free(out,10*2**30)
    dump(out/"complete.json",{"source_index":index,"compared_graphs":len(graph),"readers":len(readers),"unexpected_failures":sum(r["rustc_exit"]!=0 for r in readers),
                              "scored":0,"comparison":sha(out/"comparisons.json"),"readers_sha256":sha(out/"readers.json")})
    for pair,v in graph.items():print(pair,len(v["different_library_bytes"]),v["full_qualified_or_first_mismatch"].get("mismatch","MATCHED"),flush=True)
    print("readers",len(readers),collections.Counter(r["rustc_exit"] for r in readers),flush=True)
