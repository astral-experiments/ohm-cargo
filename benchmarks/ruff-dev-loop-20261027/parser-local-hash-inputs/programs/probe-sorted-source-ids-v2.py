"""Read the real optimized #233 hasher at the actual exported macro-span query without changing the compiler image."""
from pathlib import Path
import collections,fcntl,hashlib,json,os,re,subprocess,sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";hist=x/"mixed-native-full-abc-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,RUFF,FROZEN,load,dump,env,sha,need
from state import gate_free,source_binds,source_clean,set_source
from namespace import spawn_args,skeleton
j=P/"mixed-registry-only-pilot";comp=j/"parser-incremental-components";out=j/"native-source-ids-readback-v2";results=load(comp/"results.json")["A"];ref=load(w/"runner-binding.json")["arms"]["A"]
cfg=env();cfg["PATH"]=load(j/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
expected="dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f";driver=Path(ref["driver"]);assert sha(driver)==expected and (j/"parser-component-open-audit/A/complete.json").is_file()
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);out.mkdir(mode=0o700);mount=skeleton(out);idx=source_clean();subject=comp/"A/train-original/physical"
    c=Path(__file__).with_name("observe-frozen-source-ids-v2.c");dest=out/"observe.so"
    cc=["cc","-O2","-fPIC","-shared","-Werror","-Wall","-Wextra",str(c),"-ldl","-o",str(dest)];subprocess.run(cc,check=True)
    obj=subprocess.run(["objdump","-dC","--start-address=0x5d8405d","--stop-address=0x5d840c9",str(driver)],check=True,capture_output=True)
    (out/"caller.disasm").write_bytes(obj.stdout);assert b"freeze_and_get_read_spans" in obj.stdout and b"0x150(%rsp),%rbx" in obj.stdout
    dump(out/"probe.json",{"cc":cc,"interposer":sha(dest),"source":sha(c),"driver":sha(driver),"offset":"0x5d84079","return_offset":"0x5d8407f"})
    official=results["all"]["rustc_argv"];rmeta=Path(results["all"]["rmeta"]);arg=["rustc","+ohm",*official[1:]];baseline=[];allvals={}
    deps=subject/"target"/rmeta.parent.relative_to(TARGET);actual,=deps.glob("ruff_python_parser-*.d")
    depsenv={}
    for line in actual.read_text().splitlines():
        if line.startswith("# env-dep:") and "=" in line:
            k,v=line.removeprefix("# env-dep:").split("=",1);depsenv[k]=v
    # The real complete dependency file records rustc-observed Cargo env! inputs.
    cfg.update(depsenv);dump(out/"input-flags.json",{"argv":official,"annotated_env_dep":depsenv,"crate_dep_info_sha":sha(actual)})
    for name in ["all","empty"]:
        d=out/name;d.mkdir();st=d/"physical";gate_free(d,8*2**30);subprocess.run(["cp","-a","--reflink=auto","--",str(subject),str(st)],check=True)
        set_source(st,hist/"fixture",True);assert sha(st/"target"/rmeta.relative_to(TARGET))==sha(subject/"target"/rmeta.relative_to(TARGET))
        inc,=[Path(e.removeprefix("incremental=")).relative_to(TARGET) for e in official if e.startswith("incremental=")]
        idir,=(st/"target"/inc).glob("ruff_python_parser-*")
        if name=="empty":idir.rename(d/"disabled-session")
        opts=spawn_args(mount,out,st,st/"registry-home",[],Path(ref["cargo"]),driver);i=opts.index("--");opts[i:i]=source_binds(st)
        argenv=dict(cfg,LD_PRELOAD=str(dest),OHM_SCOUT_SPAN_LOG=str(d/"raw.jsonl"))
        q=subprocess.run([*opts,"env","LD_PRELOAD="+str(dest),"OHM_SCOUT_SPAN_LOG="+str(d/"raw.jsonl"),"OHM_SCOUT_FILE_SORT_LOG="+str(d/"files.jsonl"),*arg],cwd=RUFF,env=cfg,capture_output=True)
        (d/"stdout").write_bytes(q.stdout);(d/"stderr").write_bytes(q.stderr)
        assert q.returncode==0,(q.returncode,q.stderr.decode()[-2000:]);md=st/"target"/rmeta.relative_to(TARGET)
        read=subprocess.run([*opts,"rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(rmeta)],cwd=RUFF,env=cfg,capture_output=True,check=True);(d/"rmeta.root.txt").write_bytes(read.stdout)
        wanted=results[name];raw=[json.loads(line) for line in (d/"raw.jsonl").read_text().splitlines()]
        assert sha(md)==wanted["rmeta_sha256"] and wanted["parser_header"]["private"].encode() in read.stdout and len(raw)==1,(name,sha(md),raw)
        source_vec=[json.loads(line) for line in (d/"files.jsonl").read_text().splitlines()];assert len(source_vec)==1
        allvals[name]={"source_ids":source_vec[0],"observed":raw[0],"output_rmeta":sha(md),"output_private":wanted["parser_header"]["private"],"driver":sha(driver)};dump(out/"results.json",allvals)
        print(name,allvals[name]["source_ids"]["entries"],allvals[name]["output_private"],flush=True)
    a=allvals["all"]["source_ids"]["stable_source_ids_le"];b=allvals["empty"]["source_ids"]["stable_source_ids_le"]
    diff={"warm_only":sorted(set(a)-set(b)),"cold_only":sorted(set(b)-set(a)),"identical":len(set(a)&set(b)),"warm_count":len(a),"cold_count":len(b)}
    dump(out/"source-id-difference.json",diff);print(diff,flush=True)
    assert source_clean()==idx;dump(out/"complete.json",{"source_index":idx,"commands":2,"instrumented":True,"scored":0,"results":sha(out/"results.json")})
