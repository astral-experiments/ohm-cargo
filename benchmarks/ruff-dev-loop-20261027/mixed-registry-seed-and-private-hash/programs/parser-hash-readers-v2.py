"""Ask an ordinary newly compiled bridge and caller to choose each experimentally observed private parser hash."""
from pathlib import Path
import fcntl,json,os,re,subprocess,sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,load,dump,sha,env,need
from state import source_binds,source_clean
from namespace import skeleton,spawn_args
root=P/"mixed-registry-only-pilot";study=root/"parser-ich-by-ast";out=root/"parser-ich-callers-v2";arm=load(w/"runner-binding.json")["arms"]["B"]
args=load(root/"history-input-receipt-v1/inputs.json")["warm"]["actual_rustc"]["ruff_python_parser"]["argv"]
canonical_dir=Path(args[args.index("--out-dir")+1]);phys=study/"retained-ich_warm-ast/physical/target"/canonical_dir.relative_to(TARGET)
rlib=canonical_dir/next(phys.glob("libruff_python_parser-*.rlib")).name;linux=FROZEN/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld"
cfg=env();cfg["PATH"]=load(root/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);assert (study/"complete.json").is_file() and not out.exists();out.mkdir(mode=0o700);mount=skeleton(out);srcindex=source_clean()
    (out/"base").mkdir();(out/"libordinary_parser_bridge_input.rlib").touch()
    (out/"bridge.rs").write_text("pub fn observed() -> String { match ruff_python_parser::parse_module(\"t'first' b'second'\\n\") { Err(err) => err.to_string(), Ok(_) => panic!(\"invalid parser fixture\") } }\n")
    (out/"caller.rs").write_text('fn main() { println!("{}", ordinary_parser_bridge::observed()); }\n')
    search=[p for i,x in enumerate(args[:-1]) if x=="-L" for p in ["-L",args[i+1]]]
    results=[];bridge={}
    def invoke(state,source=None):
        st=study/state/"physical";action="bridge" if source is None else "caller";d=out/(state+"-"+action+("-"+source if source else ""));d.mkdir()
        opts=spawn_args(mount,out,st,st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]));idx=opts.index("--");ro=[]
        for a,t in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:ro+=["--ro-bind",str(a),str(t)]
        extra=[*ro,*source_binds(st),"--bind",str(d),str(out/"base")]
        if source:extra+=["--ro-bind",str(bridge[source]),str(out/"libordinary_parser_bridge_input.rlib")]
        opts[idx:idx]=extra
        cmd=["rustc","+ohm","--sysroot",str(FROZEN),"--edition=2024","-C","link-arg=-B"+str(linux),"-L","dependency="+str(canonical_dir),*search]
        if not source:cmd+=["--crate-name","ordinary_parser_bridge","--crate-type","rlib",str(out/"bridge.rs"),"--extern","ruff_python_parser="+str(rlib),"-o",str(out/"base/libordinary_parser_bridge.rlib")]
        else:cmd+=["--crate-name","ordinary_parser_user",str(out/"caller.rs"),"--extern","ordinary_parser_bridge="+str(out/"libordinary_parser_bridge_input.rlib"),"-o",str(out/"base/user")]
        z=subprocess.run([*opts,*cmd],env=cfg,cwd=RUFF,capture_output=True)
        (d/"stderr").write_bytes(z.stderr);(d/"stdout").write_bytes(z.stdout);dump(d/"argv.json",cmd)
        value=None
        if not source:
            assert z.returncode==0;bridge[state]=d/"libordinary_parser_bridge.rlib"
        elif z.returncode==0:
            run=subprocess.run([*opts,str(out/"base/user")],env=cfg,cwd=RUFF,capture_output=True,check=True)
            value=run.stdout.decode().strip();assert not run.stderr and "Bytes literal cannot be mixed with non-bytes literals" in value,value
        result={"recipient":state,"bridge":source,"kind":action,"compiler_exit":z.returncode,"runtime":value,"diagnostics":z.stderr.decode(),"argv_sha":sha(d/"argv.json"),
                "target_rlib_sha":sha(st/"target"/rlib.relative_to(TARGET)),"bridge_sha":sha(bridge[source]) if source else sha(bridge[state])}
        results.append(result);dump(out/"readers.json",results)
        if source==state: assert z.returncode==0, z.stderr.decode()
    states=[v["name"] for v in load(study/"variants.json")];assert len(states)==4
    for s in states:invoke(s)
    for s in states:
        for t in states:invoke(s,t)
    count=sum(r["compiler_exit"]!=0 for r in results)
    assert source_clean()==srcindex
    dump(out/"complete.json",{"source_index":srcindex,"commands":len(results),"failed":count,"timed_samples":0,"rows_sha256":sha(out/"readers.json")})
    for r in results:print(r["kind"],r["bridge"],r["recipient"],r["compiler_exit"],r["runtime"],flush=True)
