"""Ask an ordinary newly compiled bridge and caller to choose each experimentally observed private parser hash."""
from pathlib import Path
import fcntl,json,os,re,subprocess,sys
x=Path.home()/".cache/ohm-233-position-qualified-20261027";w=x/"mixed-native-abc-protocol-h3-v2";sys.path.insert(0,str(w))
from common import P,TARGET,SHARED,CARGO_HOME,FROZEN,RUFF,load,dump,sha,env,need
from state import source_binds,source_clean
from namespace import skeleton,spawn_args
root=P/"mixed-registry-only-pilot";label=sys.argv[1];study=root/("fixed-source-ruff-"+label)
out=root/("fixed-source-readers-"+label);subject=load(study/"subject.json");arm={"cargo":subject["cargo"],"driver":subject["driver"],"driver_sha256":subject["driver_sha256"]}
results_by_state=load(study/"results.json");args=results_by_state["warm"]["parser"]
canonical_dir=Path(args[args.index("--out-dir")+1]);rlib=Path(results_by_state["warm"]["rlib"]);linux=FROZEN/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld"
cfg=env();cfg["PATH"]=load(root/"shared-b-v3/matched-environment.json")["actual_donor_inherited_PATH"]
with(P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);assert set(results_by_state) >= {"warm","empty"} and not out.exists();out.mkdir(mode=0o700);mount=skeleton(out);srcindex=source_clean()
    (out/"base").mkdir();(out/"libordinary_parser_bridge_input.rlib").touch()
    (out/"bridge.rs").write_text("pub fn observed() -> String { match ruff_python_parser::parse_module(\"t'first' b'second'\\n\") { Err(err) => err.to_string(), Ok(_) => panic!(\"invalid parser fixture\") } }\n")
    (out/"caller.rs").write_text('fn main() { println!("{}", ordinary_parser_bridge::observed()); }\n')
    search=[p for i,x in enumerate(args[:-1]) if x=="-L" for p in ["-L",args[i+1]]]
    results=[];bridge={}
    def invoke(state,source=None):
        st=study/"state"/state;action="bridge" if source is None else "caller";d=out/(state+"-"+action+("-"+source if source else ""));d.mkdir()
        opts=spawn_args(mount,out,st,st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]));idx=opts.index("--");ro=[]
        for a,t in [(st/"target",TARGET),(st/"shared",SHARED),(st/"registry-home",CARGO_HOME),(st/"rustup",P/"rustup")]:ro+=["--ro-bind",str(a),str(t)]
        extra=[*ro,*source_binds(st),"--bind",str(d),str(out/"base")]
        if source:extra+=["--ro-bind",str(bridge[source]),str(out/"libordinary_parser_bridge_input.rlib")]
        opts[idx:idx]=extra
        cmd=["rustc","+ohm","--sysroot",str(FROZEN),"--edition=2024","-C","link-arg=-B"+str(linux),"-L","dependency="+str(canonical_dir),*search]
        if not source:cmd+=["--crate-name","ordinary_parser_bridge","--crate-type","rlib",str(out/"bridge.rs"),"--extern","ruff_python_parser="+str(rlib),"-o",str(out/"base/libordinary_parser_bridge.rlib")]
        else:cmd+=["--crate-name","ordinary_parser_user",str(out/"caller.rs"),"--extern","ordinary_parser_bridge="+str(out/"libordinary_parser_bridge_input.rlib"),"-o",str(out/"base/user")]
        trace=out/"base/trace"
        z=subprocess.run([*opts,"strace","-ff","-yy","-qq","-s","65535","-e","trace=openat,openat2,mmap","-o",str(trace),*cmd],env=cfg,cwd=RUFF,capture_output=True)
        lines=[];realpaths={}
        for tracefile in sorted(d.glob("trace.*")):
            for line in tracefile.read_text(errors="replace").splitlines():
                if ("libruff_python_parser-" not in line and "libordinary_parser_bridge" not in line) or ' = -1' in line:continue
                lines.append((tracefile.name,line))
                for name in re.findall(r"<([^>]+)>",line):
                    if not name.startswith("/"):continue
                    path=Path(name)
                    if not (path.name.startswith("libruff_python_parser-") or path.name=="libordinary_parser_bridge_input.rlib"):continue
                    if path.is_relative_to(TARGET):physical=st/"target"/path.relative_to(TARGET)
                    elif path==out/"libordinary_parser_bridge_input.rlib" and source:physical=bridge[source]
                    else:continue
                    if path.suffix not in (".rlib",".rmeta") or not physical.is_file():continue
                    fs=physical.stat()
                    if name not in realpaths:realpaths[name]={"sha256":sha(physical),"dev":fs.st_dev,"ino":fs.st_ino,"size":fs.st_size,"mmaps":0,"opens":0}
                    if line.startswith("mmap("):realpaths[name]["mmaps"]+=1
                    if line.startswith(("openat(","openat2(")):realpaths[name]["opens"]+=1
        dump(d/"observed-paths.json",realpaths);dump(d/"selected-syscalls.json",lines)
        assert lines,"no parser/path observed under syscall audit"
        class_expected=results_by_state[state]
        image_headers={}
        for fld in ("rmeta","rlib"):
            logical=Path(class_expected[fld]);physical=st/"target"/logical.relative_to(TARGET)
            rs=subprocess.run([*opts,"rustc","+ohm","--sysroot",str(FROZEN),"-Zls=root",str(logical)],cwd=RUFF,env=cfg,capture_output=True,check=True)
            raw=rs.stdout.decode();assert "private hash "+class_expected["header"]["private"] in raw
            (d/(fld+".root.txt")).write_bytes(rs.stdout)
            image_headers[str(logical)]={"sha":sha(physical),"private":class_expected["header"]["private"],"stable":class_expected["header"]["stable"],"public":class_expected["header"]["public"]}
        dump(d/"decoded-images.json",image_headers)
        parserpaths={k:v for k,v in realpaths.items() if Path(k).name.startswith("libruff_python_parser-")}
        admitted={v["sha"] for v in image_headers.values()}; assert parserpaths and all(v["sha256"] in admitted for v in parserpaths.values()),(source,state,parserpaths,image_headers)
        assert any(v["mmaps"]>0 for v in parserpaths.values()),("parser not mapped",state,source,parserpaths)
        if source:
            assert any("libordinary_parser_bridge" in k and v["sha256"]==sha(bridge[source]) and v["mmaps"] for k,v in realpaths.items()),("bridge not mapped",state,source,realpaths)

        (d/"stderr").write_bytes(z.stderr);(d/"stdout").write_bytes(z.stdout);dump(d/"argv.json",cmd)
        value=None
        if not source:
            assert z.returncode==0;bridge[state]=d/"libordinary_parser_bridge.rlib"
        elif z.returncode==0:
            run=subprocess.run([*opts,str(out/"base/user")],env=cfg,cwd=RUFF,capture_output=True,check=True)
            value=run.stdout.decode().strip();assert not run.stderr and "Bytes literal cannot be mixed with non-bytes literals" in value,value
        result={"recipient":state,"bridge":source,"kind":action,"compiler_exit":z.returncode,"runtime":value,"diagnostics":z.stderr.decode(),"argv_sha":sha(d/"argv.json"),
                "mapped":realpaths,"actual_driver":arm["driver_sha256"],"target_rlib_sha":sha(st/"target"/rlib.relative_to(TARGET)),"bridge_sha":sha(bridge[source]) if source else sha(bridge[state])}
        results.append(result);dump(out/"readers.json",results)
        if source==state: assert z.returncode==0, z.stderr.decode()
        if source is not None:
            same=results_by_state[source]["header"]["private"]==results_by_state[state]["header"]["private"]
            result["expected_same_private_hash"]=same;dump(out/"readers.json",results)
    states=["warm","empty"];assert set(states)<=results_by_state.keys()
    for s in states:invoke(s)
    for s in states:
        for t in states:invoke(s,t)
    count=sum(r["compiler_exit"]!=0 for r in results)
    assert source_clean()==srcindex
    dump(out/"complete.json",{"arm":label,"source_index":srcindex,"commands":len(results),"failed":count,"timed_samples":0,"rows_sha256":sha(out/"readers.json")})
    for r in results:print(r["kind"],r["bridge"],r["recipient"],r["compiler_exit"],r["runtime"],flush=True)
