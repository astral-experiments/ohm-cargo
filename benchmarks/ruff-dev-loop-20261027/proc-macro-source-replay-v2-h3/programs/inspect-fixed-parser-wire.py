"""Replay the actual Ruff rustc from immutable full-Cargo inputs. Gate diagnostic attribution on its exact metadata."""
from pathlib import Path
import hashlib, sys
label = sys.argv[1]
program = Path(__file__).with_name("fixed-ruff-parser-source.py")
P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
driver = P / ("parse-source-replay-"+label) / "candidate-driver.so"
with driver.open("rb") as f: expected=hashlib.file_digest(f,"sha256").hexdigest()
sys.argv = [str(program), "--driver",str(driver),"--sha",expected,"--label",label+"-wire"]
exec(compile(program.read_text().split("with (P/'native-measure.lock')")[0],str(program),"exec"))
old = J / ("fixed-source-ruff-"+label)
original = load(old/"results.json")
ref=original["warm"]
assert ref["parser"]==original["empty"]["parser"] and ref["externs"]==original["empty"]["externs"]
train = old/"state/training"; edit=old/"state/warm"
args=ref["parser"]; outdir=Path(args[args.index("--out-dir")+1]); md=Path(ref["rmeta"])
inc,=[Path(s.removeprefix("incremental=")) for s in args if s.startswith("incremental=")]
idir,=(train/"target"/inc.relative_to(TARGET)).glob("ruff_python_parser-*")
deps=phys(train,md).parent
depfile,=deps.glob("ruff_python_parser-*.d")
depsenv={}
for line in depfile.read_text().splitlines():
    if line.startswith("# env-dep:") and "=" in line:
        k,v=line.removeprefix("# env-dep:").split("=",1);depsenv[k]=v
cfg.update(depsenv)
with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX); ix=source_clean();gate_free(J,2*2**30)
    O.mkdir(mode=0o700); skeleton_base=skeleton(O)
    dump(O/"inputs.json",dict(driver=expected,argv=args,source=load(fixture/"manifest.json"),externs=ref["externs"],cargo_env_dep=depsenv,dep_info_sha256=sha(depfile),macro_sha256=ref["get_size_sha256"],raw_reference={n:original[n]["rmeta_sha256"] for n in ("warm","empty")}))
    assert all(sha(phys(train,Path(x["logical"])))==x["sha256"] for x in ref["externs"].values())
    rows={}
    for method in ["plain","stats"]:
        for history in ["warm","empty"]:
            dn=method+"-"+history; d=O/dn;d.mkdir();wi=d/"inc";wi.mkdir();wd=d/"out";wd.mkdir()
            if history=="warm":subprocess.run(["cp","-a","--reflink=auto","--",str(idir),str(wi/idir.name)],check=True)
            op=spawn_args(skeleton_base,O,train,train/"registry-home",[],cargo,driver);i=op.index("--")
            mounts=source_binds(edit)
            for fr,to in [(train/"target",TARGET),(train/"shared",SHARED),(train/"registry-home",CARGO_HOME),(train/"rustup",P/"rustup")]:
                mounts+=["--ro-bind",str(fr),str(to)]
            mounts+=["--bind",str(wd),str(outdir),"--bind",str(wi),str(inc)]
            op[i:i]=mounts
            cmd=["rustc","+ohm",*args[1:]]
            if method=="stats":cmd+=["-Zmeta-stats"]
            q=invoke(d/"process",op,cmd);assert q.returncode==0,(dn,q.stderr.decode()[-1500:])
            got=wd/md.name; assert got.is_file()
            sh=sha(got); want=original[history]["rmeta_sha256"]; sections={}
            msg=q.stderr.decode()
            for st in msg.splitlines():
                z=re.fullmatch(r"meta-stats\s+(.+?)\s+([0-9,_]+)\s+\(\s*[0-9.]+%\)",st)
                if z:sections[z[1].strip()]=int(z[2].replace(",","").replace("_",""))
            rows[dn]={"raw_metadata":sh,"bytes":got.stat().st_size,"exact_full_cargo_reference":sh==want,"sections":sections}
            dump(O/"results.json",rows);print(dn,got.stat().st_size,sh,sh==want,len(sections),flush=True)
    exact=all(v["exact_full_cargo_reference"] for v in rows.values())
    wa,ea=[rows["stats-"+h]["sections"] for h in ("warm","empty")]
    diff={k:[wa.get(k),ea.get(k)] for k in sorted(wa.keys()|ea.keys()) if wa.get(k)!=ea.get(k)}
    dump(O/"classification.json",{"all_four_raw_exact":exact,"observed_stats_deltas":diff,
        "eligible_for_wire_attribution":bool(exact and wa and ea),"original_cargo_study_unmodified":True,"timings":0})
    print("eligible",bool(exact and wa and ea),"sections",diff,flush=True)
    assert source_clean()==ix and exact
