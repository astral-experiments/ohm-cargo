"""Causally separate the existing parser incremental directory from the only differing direct AST metadata input."""
import collections, fcntl, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,SONAME,RUFF,load,dump,sha,need,env
from namespace import skeleton,spawn_args
from state import source_binds,source_clean,gate_free
from processes import records
root=P/"mixed-registry-only-pilot";out=root/"parser-ich-by-ast";donor=hist/"state/build/B";cold=root/"shared-b-v3/physical"
arm=load(w/"runner-binding.json")["arms"]["B"];view=load(root/"history-input-receipt-v1/inputs.json")
args=view["warm"]["actual_rustc"]["ruff_python_parser"];argument=args["argv"];assert argument==view["cold"]["actual_rustc"]["ruff_python_parser"]["argv"]
ex=args["externs"]["ruff_python_ast"]; ast=Path(ex["path"]).relative_to(TARGET)
assert ast.suffix==".rmeta" and sha(donor/"target"/ast)==ex["sha256"]!=sha(cold/"target"/ast)
write_root=Path(argument[argument.index("--out-dir")+1]).relative_to(TARGET)
native_md=next((donor/"target"/write_root).glob("libruff_python_parser-*.rmeta")).relative_to(donor/"target")
incremental=Path(args["incremental"][0].removeprefix("incremental=")).relative_to(TARGET)
private_fp=write_root.parent/"fingerprint/lib-ruff_python_parser"
assert sha(donor/"target"/native_md)!=sha(cold/"target"/native_md)
cfg=env();cfg["PATH"]=load(root/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
def source_bytes_in_ich(p):
    rows=[]
    for f in sorted(p.rglob("*")):
        if f.is_file():rows.append([str(f.relative_to(p)),f.stat().st_size,sha(f)])
    return rows
def credential(namespace, path):
    q=subprocess.run([*namespace,"rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(path)],env=cfg,cwd=RUFF,check=True,capture_output=True)
    m=re.search(r"^private hash (\w+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash (\w+)",q.stdout.decode(),re.M);assert m
    return q.stdout,{"private":m[1],"stable":m[2],"public":m[3]}
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);need(not out.exists(),out);out.mkdir(mode=0o700);mount=skeleton(out)
    index=source_clean();assert index==view["warm"]["source_index"]
    registry=load(root/"shared-b-v3/projected.json");shared_macro=Path(registry["expected_proc_macro"])
    variants=[]
    for inc,ast_source in [("retained","warm"),("empty","warm"),("retained","cold"),("empty","cold")]:
        name=inc+"-ich_"+ast_source+"-ast";d=out/name;d.mkdir();gate_free(d,8*2**30);need(shutil.disk_usage(x).free>107*2**30,"original root reserve")
        st=d/"physical"
        subprocess.run(["cp","-a","--reflink=auto","--",donor,st],check=True)
        assert sha(st/"target"/shared_macro)==registry["expected_sha"] and not (st/"target"/shared_macro).samefile(donor/"target"/shared_macro)
        for rel in (native_md,ast,private_fp):assert not (donor/"target"/rel).samefile(st/"target"/rel) and sha(donor/"target"/rel)==sha(st/"target"/rel)
        (st/"target"/private_fp).rename(d/"inactive-parser-fingerprint")
        ich,=(st/"target"/incremental).glob("ruff_python_parser-*")
        inc_manifest=source_bytes_in_ich(ich);assert inc_manifest
        if inc=="empty":ich.rename(d/"inactive-parser-ich")
        opts=spawn_args(mount,out,st,st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]));ix=opts.index("--");extra=source_binds(st)
        # The real parser used this separate metadata file as its sole AST extern. All other
        # inputs, including linker rlibs, retain their genuine private warm-state bytes.
        if ast_source=="cold":extra+=["--ro-bind",str(cold/"target"/ast),str(TARGET/ast)]
        opts[ix:ix]=extra
        before,header_before=credential(opts,TARGET/native_md);(d/"parser.before.root").write_bytes(before)
        _,ast_header=credential(opts,TARGET/ast)
        cmd=["cargo","+ohm","build","--locked","--offline","--message-format=json"]
        with(d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:
            z=subprocess.run([*opts,"strace","-ff","-qq","-s","1048576","-e","trace=execve,execveat,prctl","-o",str(d/"exec"),*cmd],cwd=RUFF,env=cfg,stdout=so,stderr=se)
        need(z.returncode==0,("ordinary full command",name,(d/"stderr").read_text()[-500:]))
        rows=[json.loads(line) for line in (d/"stdout").read_bytes().splitlines()]
        comp=[r for r in rows if r["reason"]=="compiler-artifact"]
        actual=[a for _,f,a in records(d) if Path(f).name=="rustc" and "--crate-name" in a and "--out-dir" in a]
        selected=[a for a in actual if a[a.index("--crate-name")+1]=="ruff_python_parser"]
        assert len(comp)==501 and selected==[argument] and all(r["fresh"] for r in comp if r["target"]["name"]=="ruff_python_ast")
        assert [r["fresh"] for r in comp if r["target"]["name"]=="ruff_python_parser"]==[False]
        after,header_after=credential(opts,TARGET/native_md);(d/"parser.after.root").write_bytes(after)
        mixed={}
        for n in ["ruff_wasm","ty_wasm"]:
            prod=next(r for r in comp if r["target"]["name"]==n and set(r["target"]["crate_types"])=={"cdylib","rlib"})
            pp=Path(next(f for f in prod["filenames"] if f.endswith(".rmeta")));s,h=credential(opts,pp);(d/(n+".after.root")).write_bytes(s)
            mixed[n]={"header":h,"sha256":sha(st/"target"/pp.relative_to(TARGET))}
        dsha=hashlib.sha256(json.dumps(inc_manifest,sort_keys=True).encode()).hexdigest();dump(d/"starting-ich-manifest.json",inc_manifest)
        result={"name":name,"ICH":inc,"AST":ast_source,"direct_AST_sha256":sha((cold if ast_source=="cold" else donor)/"target"/ast),"direct_AST_header":ast_header,"command":cmd,
                "before_parser":header_before,"after_parser":header_after,"parser_raw":sha(st/"target"/native_md),"source_index":index,"actual_parser_argv":selected[0],
                "starting_ich_sha256":dsha,"starting_ich_paths":len(inc_manifest),"fresh":sum(r["fresh"] for r in comp),"native_jobs":len(actual),"mixed":mixed}
        variants.append(result);dump(out/"variants.json",variants);print(name,header_after,[(k,v["header"]["private"]) for k,v in mixed.items()],flush=True)
    assert source_clean()==index and len({r["starting_ich_sha256"] for r in variants})==1,"identical cloned source/producer cache to start each arm"
    dump(out/"complete.json",{"rows":len(variants),"variants_sha256":sha(out/"variants.json"),"scored_commands":0})
