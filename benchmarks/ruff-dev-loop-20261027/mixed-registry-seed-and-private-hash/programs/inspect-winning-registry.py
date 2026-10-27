"""Validate the actual selected plugin on each ordinary consumer and inventory compiler-tracked build-script source files."""
from pathlib import Path
import fcntl, hashlib, json, os, re, struct, subprocess, sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,load,dump,sha,env,need
from state import source_binds,source_clean
from namespace import spawn_args,skeleton
from archive_audit import elf
root=P/"mixed-registry-only-pilot";out=root/"winner-native-plugin-and-leaves"
reference=load(x/"mixed-registry-seed-programs-20261027/match-frozen-prereg/registry-match-registration.json")["fixed_reference"]
subject=load(w/"runner-binding.json");keys=load(root/"cross-image-registry-root/first.json")
def one(st,cmd,args):
    return subprocess.run([*cmd,*args],cwd=RUFF,env=env(),capture_output=True)
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);out.mkdir(mode=0o700);mount=skeleton(out);index=source_clean()
    (out/"conflict.rs").write_bytes((x/"mixed-h3-v2-rejected/registry-macro-v2/conflict.rs").read_bytes())
    reports={}
    for label,s in [("A","older-matched-workspace-cold"),("B","shared-b-v3"),("C","shared-c-v3")]:
        ds=root/s;st=ds/"physical";d=out/label;d.mkdir();proof=load(ds/"projected.json");records=[json.loads(line) for line in(ds/"build/stdout").read_bytes().splitlines()]
        ref=subject["arms"][label];cmd=spawn_args(mount,out,st,st/"registry-home",[],Path(ref["cargo"]),Path(ref["driver"]));i=cmd.index("--");ro=[]
        for src,dst in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:ro+=["--ro-bind",str(src),str(dst)]
        cmd[i:i]=ro+source_binds(st)
        logical=TARGET/proof["expected_proc_macro"];actual=st/"target"/proof["expected_proc_macro"]
        assert sha(actual)==reference["entire_shared_object_sha256"]
        getq=next(r for r in records if r.get("target",{}).get("name")=="get_size_derive2")
        assert getq["fresh"] and getq["filenames"]==[str(logical)]
        q=one(st,cmd,["rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(logical)]);assert q.returncode==0
        (d/"plugin.root.txt").write_bytes(q.stdout)
        assert reference["public_and_private_rust_hash"].encode() in q.stdout
        so=actual.read_bytes();tab=elf(so);t=hashlib.sha256(tab[".text"]["data"]).hexdigest();assert t==reference["text_sha256"]
        conflict_cmd=["rustc","+ohm","--edition=2024","--crate-name","demonstrate_conflict","--crate-type=lib","--emit=metadata","--error-format=json","--extern","get_size_derive2="+str(logical),str(out/"conflict.rs"),"-o",str(d/"conflict.rmeta")]
        q=one(st,cmd,conflict_cmd);(d/"conflict.stderr").write_bytes(q.stderr)
        errors=[j["message"] for line in q.stderr.splitlines() if (j:=json.loads(line)).get("level")=="error" and "aborting" not in j["message"]]
        assert q.returncode==1 and errors==[reference["expected_first_conflict"]]
        leaves={}
        for key in keys:
            pkg=key.split("|")[0];row=next(r for r in records if r["reason"]=="build-script-executed" and r["package_id"]==pkg)
            runs=Path(row["out_dir"]);phys=st/"target"/runs.relative_to(TARGET);generated={}
            for f in sorted(phys.rglob("*")):
                if f.is_file() and f.suffix in (".rs",".expr"):
                    assert not f.is_symlink();relative=f.relative_to(phys);generated[str(relative)]={"logical_path":str(runs/relative),"sha256":sha(f),"size":f.stat().st_size}
                    if f.stat().st_size<1024:generated[str(relative)]["source"]=f.read_text()
            crate=row["package_id"].split("#")[-1].split("@")[0]
            rawrow=next(r for r in records if r.get("reason")=="compiler-artifact" and r["package_id"]==pkg and r["target"]["name"]==key.split("|")[1])
            common=Path(rawrow["filenames"][0]).parent
            dep=st/"target"/common.relative_to(TARGET)
            depfiles={str(common/f.name):f.read_bytes() for f in dep.glob("*.d")}
            for g in generated.values():g["rustc_dep_files_containing_full_path"]=[k for k,v in depfiles.items() if os.fsencode(g["logical_path"]) in v]
            leaves[crate]={"package":pkg,"script_output_root":str(runs),"target":rawrow,"generated":generated,"real_dep_info":{k:hashlib.sha256(v).hexdigest() for k,v in depfiles.items()}}
        reports[label]={"actual_plugin_file":str(logical),"native_product_sha256":sha(actual),"text_sha256":t,
          "header_sha256":sha(d/"plugin.root.txt"),"source":proof["source_index"],"actual_cargo":ref["cargo_sha256"],"actual_driver":ref["driver_sha256"],
          "compiled_extern_receipt":getq,"independent_rustc_cmd":conflict_cmd,"compiler_exit":q.returncode,"diagnostic":errors,"leaves":leaves}
    dump(out/"all.json",reports);assert source_clean()==index
    for name in sorted(reports["A"]["leaves"]):
        a=reports["A"]["leaves"][name]["generated"];z=reports["B"]["leaves"][name]["generated"]
        print(name,[(k,v["sha256"]==z[k]["sha256"],len(v["rustc_dep_files_containing_full_path"]),len(z[k]["rustc_dep_files_containing_full_path"])) for k,v in a.items() if k in z],flush=True)
