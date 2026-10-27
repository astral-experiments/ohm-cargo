"""Project genuine registry units named by a completed native Cargo build; prove what the next real build accepts."""
from pathlib import Path
import argparse, collections, fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, tarfile, tomllib

x = Path.home() / ".cache/ohm-233-position-qualified-20261027"
w = x / "mixed-native-abc-protocol-h3-v2"
historical = x / "mixed-native-full-abc-h3-v2"
sys.path.insert(0, str(w))
from common import P, CARGO_HOME, FROZEN, RUFF, SHARED, TARGET, dump, env, load, need, sha
from namespace import skeleton, spawn_args
from processes import records
from state import seed, source_clean, source_binds, set_source, gate_free

parser = argparse.ArgumentParser()
parser.add_argument("arm", choices=["B","C","A"])
parser.add_argument("location")
parser.add_argument("--donor", choices=["A", "B"])
parser.add_argument("--prepare-only", action="store_true")
args = parser.parse_args()
assert re.fullmatch(r"[a-z0-9-]+", args.location)
location = P / "mixed-registry-only-pilot" / args.location
source_tag = args.donor or ("A" if args.arm == "A" else "B")
donor = historical / "state/build" / source_tag
old = historical / "receipts/build" / source_tag / "cold"
b = load(w / "runner-binding.json")
arm = b["arms"][args.arm]
origin = "registry+https://github.com/rust-lang/crates.io-index"
fixture = historical / "fixture"

def regulars(p):
    return sorted(f for f in p.rglob("*") if f.is_file() or f.is_symlink())

def unit_of(logical):
    f = Path(logical)
    if not f.is_relative_to(TARGET): return None
    rel = f.relative_to(TARGET)
    parts = rel.parts
    if len(parts) < 8 or parts[:3] != ("debug","build","workspaces") or parts[7] != "out": return None
    assert re.fullmatch("[0-9a-f]{16}", parts[3]) and re.fullmatch("v2-[0-9a-f]+-all-native-all", parts[4])
    assert re.fullmatch("[0-9a-f]{16}", parts[6])
    return Path(*parts[:7])

def units(stdout):
    reg, local, all_origins = {}, {}, []
    for line in stdout.read_bytes().splitlines():
        row = json.loads(line)
        if row["reason"] not in ("compiler-artifact", "build-script-executed"): continue
        package = row["package_id"]
        files = row.get("filenames") or [row["out_dir"]]
        all_origins.append([row["reason"], package, files])
        is_reg = package.startswith(origin + "#")
        assert is_reg or package.startswith("path+file:"), package
        for f in files:
            u = unit_of(f)
            if not u:
                assert not is_reg, (f,package)
                continue
            if is_reg:
                assert u.parts[-2] == package.split("#")[1].split("@")[0], (u,package)
            d = reg if is_reg else local
            assert d.get(u,package) == package
            d[u] = package
    assert not reg.keys() & local.keys() and len(reg) > 300 and local
    return reg, local, all_origins

def verify_packages(package_ids,registry):
    lock = tomllib.loads((RUFF/"Cargo.lock").read_text())
    locked = {(p["name"],p["version"]):p["checksum"] for p in lock["package"] if p.get("source")==origin}
    out={}
    for pid in sorted(package_ids):
        name,ver = pid.split("#")[1].split("@")
        req=locked[(name,ver)]
        archive, = (registry/"registry/cache").glob(f"*/{name}-{ver}.crate")
        root, = (registry/"registry/src").glob(f"*/{name}-{ver}")
        assert sha(archive)==req
        h=hashlib.sha256()
        files=0
        with tarfile.open(archive) as tf:
            for m in tf:
                if m.isdir(): continue
                assert m.isfile(), (pid,m.name)
                rel=Path(m.name).relative_to(root.name)
                assert ".." not in rel.parts
                extracted=root/rel
                assert extracted.is_file() and not extracted.is_symlink()
                dg=hashlib.file_digest(tf.extractfile(m),"sha256").hexdigest()
                assert sha(extracted)==dg,(pid,rel)
                h.update(os.fsencode(rel)+b"\0"+dg.encode()+b"\n");files+=1
        out[pid]={"crate_sha256":req,"extracted_files":files,"files_sha256":h.hexdigest()}
    return out

def filtered_argv_set(reg, origins):
    compiled={unit_of(p) for reason,pkg,files in origins if reason=="compiler-artifact" and pkg.startswith(origin+"#") for p in files}
    run_dirs={unit_of(p) for reason,pkg,files in origins if reason=="build-script-executed" and pkg.startswith(origin+"#") for p in files}
    out={};helpers=[]
    for _, img, qa in records(old):
        if Path(img).name!="rustc" or "--crate-name" not in qa or "--out-dir" not in qa:continue
        u=unit_of(qa[qa.index("--out-dir")+1])
        if u not in reg: continue
        role=qa[qa.index("--crate-name")+1]
        srcs=[x for x in qa if x.endswith(".rs") and not x.startswith("-")]
        if u in run_dirs and u not in compiled:
            assert "-" in qa or srcs,(role,qa)
            assert all(Path(p).is_relative_to(CARGO_HOME/"registry/src") or Path(p).is_relative_to(TARGET/u/"out") for p in srcs),(u,srcs)
            helpers.append({"crate_name":role,"package":reg[u],"build_script_run":str(u),"argv":qa})
            continue
        assert u in compiled,("unattributed rustc",u,role)
        assert srcs and all(Path(s).is_relative_to(CARGO_HOME/"registry/src") for s in srcs),(role,srcs)
        for i,x in enumerate(qa[:-1]):
            if x!="--extern" or "=" not in qa[i+1]:continue
            n,p=qa[i+1].split("=",1)
            if Path(p).is_absolute():
                assert unit_of(p) in reg,("registry-to-non-registry extern",u,n,p)
        out[str(u)]={"crate_name":role,"argv":qa}
    assert len(out)>300 and any(v["crate_name"]=="get_size_derive2" for v in out.values())
    return {"compilation":out,"registered_build_script_rustc_probes":helpers}

def project(reg, out, source):
    inv={}
    for u,pid in sorted(reg.items()):
        d=out/u;src=source/u;assert not d.exists() and src.is_dir() and not src.is_symlink()
        d.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp","-a","--reflink=auto","--",src,d],check=True)
        for f in regulars(src):
            q=d/f.relative_to(src); key=str(q.relative_to(out))
            assert key not in inv
            if f.is_symlink():
                assert q.is_symlink() and q.readlink()==f.readlink() and not f.readlink().is_absolute()
                assert f.resolve().is_relative_to(src) and q.resolve().is_relative_to(d), (u, f, q)
                inv[key]={"package":pid,"link":os.readlink(f)}
            else:
                a,aa=f.stat(),q.stat(); h=sha(f)
                assert (a.st_size,a.st_mtime_ns,a.st_mode)==(aa.st_size,aa.st_mtime_ns,aa.st_mode) and not f.samefile(q) and sha(q)==h
                inv[key]={"package":pid,"size":a.st_size,"mtime_ns":a.st_mtime_ns,"sha256":h,"independent_inode":True}
    assert set(inv)=={str(p.relative_to(out)) for p in regulars(out)}
    return inv

with (P/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    need(not location.exists(),location)
    location.mkdir(parents=True,mode=0o700)
    gate_free(location,15*2**30)
    assert shutil.disk_usage(x).free>107*2**30
    idx=source_clean();assert idx==b["host"]["source_index_sha256"]
    assert all(sha(Path(arm[key])) == arm[key+"_sha256"] for key in ("cargo","driver"))
    reg,local,origins=units(old/"stdout")
    dump(location/"origins.json",origins)
    dump(location/"registry-reported-units.json",{str(k):v for k,v in reg.items()})
    dump(location/"excluded-workspace-units.json",{str(k):v for k,v in local.items()})
    dump(location/"registry-unit-argv.json",filtered_argv_set(reg,origins))
    mount=skeleton(location)
    st=seed(location/"physical",fixture,CARGO_HOME)
    set_source(st,fixture,True)
    verified=verify_packages(set(reg.values()), st/"registry-home")
    dump(location/"verified-registry-packages.json",verified)
    inventory=project(reg,st/"target",donor/"target")
    dump(location/"projected-inventory.json",inventory)
    assert all(not (st/"target"/i).exists() for i in local) and not any((st/"shared").iterdir())
    expected=next(f for f,info in inventory.items() if f.endswith(".so") and "/get-size-derive2/" in f)
    expected_sha=inventory[expected]["sha256"]
    configs=[p for p in regulars(donor/"target") if p.name=="config.log" and "/tikv-jemalloc-sys/" in str(p)]
    assert len(configs)==1, configs
    path_lines=[line.removeprefix("PATH: ") for line in configs[0].read_text(errors="strict").splitlines() if line.startswith("PATH: ")]
    assert path_lines[0]==str(CARGO_HOME/"bin") and len(path_lines)>4, path_lines
    original_path=os.pathsep.join(path_lines[1:])
    command_env=env()
    dump(location/"matched-environment.json",{"donor_configure_log":str(configs[0]),"configure_sha256":sha(configs[0]),
        "inherited_PATH":command_env["PATH"],"actual_donor_inherited_PATH":original_path,"cargo_child_PATH":path_lines})
    command_env["PATH"]=original_path
    print("PROJECTED",len(reg),len(verified),len(inventory),sum(v.get("size",0) for v in inventory.values()),expected,expected_sha,flush=True)
    dump(location/"projected.json",{"source_index":idx, "donor_arm":source_tag,"arm":args.arm,"expected_proc_macro":expected,"expected_sha":expected_sha,
          "packages":len(verified),"registry_units":len(reg),"excluded_workspace_units":len(local),"included_files":len(inventory),
          "previous_workspace_artifacts":0,"previous_shared_files":0,"three_project_files":load(fixture/"manifest.json"),"inventory_sha256":sha(location/"projected-inventory.json")})
    dump(location/"mount.json", mount)
    if args.prepare_only: sys.exit(0)
    options = spawn_args(mount, location, st, st/"registry-home",[],Path(arm["cargo"]),Path(arm["driver"]))
    ix=options.index("--");options[ix:ix]=source_binds(st)
    d=location/"build";d.mkdir()
    cmd=["cargo","+ohm","build","--locked","--offline","--message-format=json"]
    if any(v for v in os.environ if v.startswith("CARGO_PROFILE_") or v in ("RUSTC","RUSTC_WRAPPER","RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS")):raise ValueError("inherited override")
    jobs=[]
    with(d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:
        run = subprocess.Popen([*options,"strace","-ff","-qq","-s","1048576","-e","trace=execve,execveat,prctl","-o",str(d/"exec"),*cmd],
                               cwd=RUFF,env=command_env,stdout=subprocess.PIPE,stderr=se,start_new_session=True)
        try:
            for raw in run.stdout:
                so.write(raw);so.flush();row=json.loads(raw)
                if row["reason"]!="compiler-artifact":continue
                jobs.append(row)
                if row["package_id"].startswith(origin+"#"):
                    for file in row["filenames"]:
                        u=unit_of(file)
                        need(u in reg,("different Cargo authenticated namespace or new registry unit",file))
                if row["package_id"].startswith("path+file:"):
                    need(not row["fresh"],("unexpected local workspace reuse",row["package_id"],row["target"]))
                if row["target"]["name"]=="get_size_derive2":
                    need(row["fresh"] and row["filenames"]==[str(TARGET/expected)] and sha(st/"target"/expected)==expected_sha,
                         ("ordinary Cargo rejected authentic producer",row["fresh"],row["filenames"],str(TARGET/expected),sha(st/"target"/expected)))
                    print("MATERIALIZED",args.arm,expected_sha,flush=True)
            need(run.wait()==0,"whole native build failed")
        except BaseException:
            if run.poll() is None:
                os.killpg(run.pid,signal.SIGTERM);run.wait(timeout=30)
            raise
    decoded={}
    for _,f,a in records(d):
        if Path(f).name=="rustc" and "--crate-name" in a and "--out-dir" in a:
            crate=a[a.index("--crate-name")+1]
            decoded.setdefault(crate,[]).append(a)
    assert len(jobs)==501 and "get_size_derive2" not in decoded and "ruff_wasm" in decoded and "ty_wasm" in decoded
    assert source_clean()==idx and gate_free(location,10*2**30) and shutil.disk_usage(x).free>107*2**30
    dump(location/"complete.json",{"units":len(jobs),"fresh_registry_units":sum(r["fresh"] for r in jobs),
         "workspace_compiler_units":sum(r["package_id"].startswith("path+file:") for r in jobs),"fresh_workspace_units":0,
         "actual_compiler_commands":sum(map(len,decoded.values())),"root_sha":expected_sha,"subject":arm,
         "whole_compiler_crates":{k:len(v) for k,v in decoded.items()},"scored_commands":0})
    print("UNSCORED_COMPLETE",load(location/"complete.json"),flush=True)
