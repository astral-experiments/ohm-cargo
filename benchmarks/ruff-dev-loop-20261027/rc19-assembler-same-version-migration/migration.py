"""Train a wrong native executable, then replace only the same-version Cargo and retest it."""
from pathlib import Path
import argparse, ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys

here=Path(__file__).resolve().parent
def digest(p):
    with p.open("rb") as inp:
        return hashlib.file_digest(inp, "sha256").hexdigest()
def dump(p,data):
    with p.open("x") as out:
        json.dump(data,out,indent=2,sort_keys=True)
        out.write("\n")
def read(p):return json.loads(p.read_bytes())
assert digest(here/"asm-witness.py") == "131c5342c20800923a418bfef2ca0cf194f64acec938e46ce283b31cb365a85d"
spec=importlib.util.spec_from_file_location("asm_witness",here/"asm-witness.py")
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
arg=argparse.ArgumentParser(description=__doc__)
arg.add_argument("phase",choices=("train","upgrade"))
arg.add_argument("directory",type=Path)
arg.add_argument("sdk",type=Path)
arg.add_argument("cargo",type=Path)
arg.add_argument("--sha256",required=True)
arg.add_argument("--kind",choices=("bin","test"),required=True)
arg.add_argument("--poison",choices=("valid","missing"),required=True)
arg.add_argument("--new-flag",choices=("default","explicit-no"),required=True)
args=arg.parse_args()
assert os.geteuid()==1000 and Path("/").stat().st_uid==Path("/home").stat().st_uid==0
assert set(os.sched_getaffinity(0)) <= {8,9,10,11}
d=args.directory.resolve(); donor=args.sdk.resolve(strict=True)
parent=args.cargo.resolve(strict=True)
assert digest(parent)==args.sha256 and shutil.disk_usage(d.parent).free>30*2**30
sdk=d/"sdk";live=sdk/"bin/cargo";rh=d/"rustup";ws=d/"workspace"
target_path=(ws/"src/main.rs" if args.kind=="bin" else ws/"tests/reader.rs")
lib=ws/"src/lib.rs";asset=ws/"payload.bin"
environment={"HOME":str(d/"home"),"CARGO_HOME":str(d/"cargo-home"),"RUSTUP_HOME":str(rh),
             "PATH":str(Path(shutil.which("rustup")).parent)+":/usr/bin:/bin",
             "CARGO_NET_OFFLINE":"true","RUSTUP_AUTO_INSTALL":"0","LC_ALL":"C","LANG":"C",
             "CARGO_INCREMENTAL":"0"}
def version():
    return subprocess.check_output(["cargo","+ohm","-Vv"],cwd=ws,env=environment)
def switch():
    new=live.with_name("next-cargo")
    assert not new.exists()
    shutil.copyfile(parent,new);new.chmod(0o755);assert digest(new)==args.sha256
    os.replace(new,live);assert digest(live)==args.sha256

def setup():
    d.mkdir(mode=0o700)
    for sub in (ws/"src",ws/"tests",sdk/"bin",rh/"toolchains",d/"home",d/"cargo-home",d/"visits"):
        sub.mkdir(parents=True)
    for f in donor.iterdir():
        if f.name!="bin":(sdk/f.name).symlink_to(f,target_is_directory=f.is_dir())
    for f in (donor/"bin").iterdir():
        if f.name!="cargo":(sdk/"bin"/f.name).symlink_to(f)
    (rh/"toolchains/ohm").symlink_to(sdk,target_is_directory=True)
    manifest='[package]\nname="assembler_reader"\nversion="0.0.0"\nedition="2024"\nautobins=false\n'
    if args.kind=="bin":manifest+='\n[[bin]]\nname="reader"\npath="src/main.rs"\ntest=false\nbench=false\n'
    (ws/"Cargo.toml").write_text(manifest)
    (ws/"Cargo.lock").write_text('version = 4\n\n[[package]]\nname="assembler_reader"\nversion="0.0.0"\n')
    lib.write_bytes(w.ORIGINAL)
    if args.kind=="bin":
        body=w.READER.replace("#[test]\nfn reads_the_assembled_input()","fn main()").replace("RUST_VALUE","assembler_reader::observed(std::hint::black_box(3))")
    else:body=w.READER.replace("RUST_VALUE","0u8")
    target_path.write_text(body);asset.write_bytes(bytes([17]))
    dump(d/"environment.json",environment)

admission={"kind":args.kind,"poison":args.poison,"new_flag":args.new_flag,
           "runtime":digest(donor/"bin/rustc"),"wild":digest(donor/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"),
           "shim":digest(Path(shutil.which("cargo"))),"study":digest(Path(__file__))}
def sig(file):
    s=file.stat()
    return {"sha":digest(file),"size":s.st_size,"inode":s.st_ino,"device":s.st_dev,
            "mtime_ns":s.st_mtime_ns,"ctime_ns":s.st_ctime_ns}

def run(label,*,mode="native",lane=None,explicit=False):
    if lane is None:lane="state-"+mode
    root=d/lane
    lookup={"native":(["build","--bin","reader"] if args.kind=="bin" else ["test","--no-run","--test","reader"]),
            "check":["check","--all-targets"],"lib":["build","--lib"]}
    cmd=["cargo","+ohm",*(["-Zrelink-only=no"] if explicit else []),*lookup[mode],"--locked","--offline","-j2","--message-format=json"]
    ev=d/"visits"/label;ev.mkdir()
    env=environment|{"CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"shared")}
    real_rustc=sig(sdk/"bin/rustc")
    listing=["strace","-ff","-qq","-s","131072","-e","trace=execve,open,openat,openat2,clone,clone3,fork,vfork","-o",ev/"trace",*cmd]
    with (ev/"stdout").open("xb") as out,(ev/"stderr").open("xb") as err:
        proc=subprocess.run(listing,cwd=ws,env=env,stdout=out,stderr=err,timeout=120)
    typed=[json.loads(line) for line in (ev/"stdout").read_bytes().splitlines()]
    assert typed[-1]=={"reason":"build-finished","success":proc.returncode==0}
    assert not any(z["reason"]=="build-script-executed" for z in typed)
    arts=[z for z in typed if z["reason"]=="compiler-artifact"]
    processes,reads,incrementals,_,depinfo=w.trace_info(ev,asset)
    # The installed bin has no suffix before uplift. The earlier integration-test
    # study only selected output names beginning with reader-.
    if args.kind=="bin":
        for trace in sorted(ev.glob("trace.*")):
            for line in trace.read_text(errors="replace").splitlines():
                m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',line)
                if not m:continue
                image=Path(ast.literal_eval(m[1]))
                if image.name not in ("ld","ld.bfd","ld.lld","rust-lld"):continue
                argv=ast.literal_eval(m[2])
                if "-o" in argv and Path(argv[argv.index("-o")+1]).name=="reader":
                    processes.append({"type":"linker","pid":int(trace.name.split(".")[-1]),"name":image.name,
                                      "exe":digest(image),"line":hashlib.sha256(line.encode()).hexdigest()})
    assert not incrementals
    assert all(z["exe"]==admission["runtime"] and not z.get("incremental") for z in processes if z["type"]=="rustc")
    assert all(z["exe"]==admission["wild"] for z in processes if z["type"]=="linker")
    record={"mode":mode,"argv":cmd,"status":proc.returncode,"cargo":digest(live),
            "rustc":real_rustc["sha"],"configuration_sha":digest(ws/"Cargo.toml"),
            "processes":processes,"asset_opens":reads,"depinfo":depinfo,
            "asset":digest(asset) if asset.exists() else None,"library_source":digest(lib),
            "consumer_source":digest(target_path),"label":label,"source_inputs":{
            "Cargo.toml":digest(ws/"Cargo.toml"),"Cargo.lock":digest(ws/"Cargo.lock")},
            "typed":[[z["target"]["name"],z["target"]["kind"],z["profile"]["test"],z["fresh"]] for z in arts],
            "incbin_diagnostic":b'payload.bin' in (ev/"stdout").read_bytes()+(ev/"stderr").read_bytes()}
    execute=[Path(z["executable"]) for z in arts if z.get("executable") and z["target"]["name"]=="reader"]
    if mode=="native" and proc.returncode==0:
        p,=execute;assert p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root)
        qa=[p] if args.kind=="bin" else [p,"--exact","reads_the_assembled_input","--nocapture"]
        result=subprocess.run(qa,cwd=ws,env=env,capture_output=True,timeout=10)
        assert result.returncode==0 and (args.kind=="bin" or b"1 passed" in result.stdout)
        (ev/"program.stdout").write_bytes(result.stdout)
        vals,=re.findall(rb"native-value=(\d+),rust-value=(\d+)",result.stdout)
        record["native"],record["rust"]=map(int,vals)
        record["elf"]=digest(p);record["logical_output"]=str(p.relative_to(root))
    record["raw"]={f.name:digest(f) for f in ev.iterdir() if f.is_file()}
    dump(ev/"result.json",record)
    print(label,mode,record["status"],record.get("native"),record.get("rust"),[(t.get("unit",t.get("name")),t.get("link_only")) for t in processes],len(reads),flush=True)
    return record

def pristine(j):
    assert j["status"]==0 and all(x[-1] for x in j["typed"]) and not j["processes"] and not j["asset_opens"],(j["label"],j["typed"],j["processes"])
def assembly(j,missing=False):
    assert any(o["nearest_compiler"]=="reader" and o["missing" if missing else "open_successful"] for o in j["asset_opens"]),j["label"]
    assert any(v.get("unit")=="reader" and not v["link_only"] for v in j["processes"]),j["label"]
    if missing:assert j["status"]==101 and j["incbin_diagnostic"],j["label"]
def lineage(rel):
    root=d/"state-native"
    paths=[root/rel,lib,target_path,ws/"Cargo.lock",ws/"Cargo.toml",sdk/"bin/rustc",d/"environment.json"]
    if asset.exists():paths.append(asset)
    for ext in (".rlink",".rlink-cache.json"):
        p=(root/rel).with_name((root/rel).name+ext)
        if p.is_file():paths.append(p)
    return {str(p.relative_to(d)):sig(p) for p in paths}

if args.phase=="train":
    setup();switch()
    oldversion=version();(d/"old.version").write_bytes(oldversion)
    original=run("01-original");assembly(original);assert original["native"]==17
    pristine(run("02-original-repeat"))
    lib.write_bytes(w.PRIVATE if args.kind=="bin" else w.PUBLIC)
    if args.poison=="missing":asset.unlink()
    else:asset.write_bytes(bytes([29]))
    poisoned=run("03-actual-edit-poison")
    assert poisoned.get("native")==17 and not poisoned["asset_opens"],poisoned
    assert any(z.get("unit")=="reader" and z["link_only"] for z in poisoned["processes"]),poisoned
    assert any(z["type"]=="linker" for z in poisoned["processes"])
    if args.kind=="bin":assert (original["rust"],poisoned["rust"])==(6,10)
    clean=run("04-independent-clean",lane="old-clean")
    assembly(clean,args.poison=="missing")
    if args.poison=="valid":assert clean["native"]==29
    for k in ("check","lib"):
        run("05-train-"+k,mode=k);pristine(run("06-settled-"+k,mode=k))
    repeated=run("07-wrong-fresh-repeat");pristine(repeated);assert repeated["elf"]==poisoned["elf"]
    prior=lineage(repeated["logical_output"]);oldstat=sig(live);switch()
    assert oldstat["inode"]!=live.stat().st_ino and version()==oldversion and lineage(repeated["logical_output"])==prior
    same=run("08-identical-Cargo-replacement");pristine(same);assert same["elf"]==poisoned["elf"]
    dump(d/"trained.json",admission|{"old":args.sha256,"version":digest(d/"old.version"),"old_cargo":sig(live),
                                   "lineage":lineage(same["logical_output"]),"output":same["logical_output"],
                                   "poisoned":poisoned["elf"],"clean":clean.get("elf")})
    sys.exit(0)

old=read(d/"trained.json");assert all(old[k]==v for k,v in admission.items())
assert digest(live)==old["old"] and old["old"]!=args.sha256 and lineage(old["output"])==old["lineage"]
switch()
newversion=version();(d/"new.version").write_bytes(newversion)
assert newversion==(d/"old.version").read_bytes(),"full Cargo -Vv changed; this cannot exercise a same-version state upgrade"
assert old["old_cargo"]["inode"]!=live.stat().st_ino and lineage(old["output"])==old["lineage"]
dump(d/"swap.json",{"old":old["old_cargo"],"new":sig(live),"old_version":old["version"],
                   "new_version":digest(d/"new.version"),"lineage_before":old["lineage"],"lineage_after":lineage(old["output"])})
for k in ("check","lib"):pristine(run("09-upgrade-unaffected-"+k,mode=k))
explicit=args.new_flag=="explicit-no"
r=run("10-first-unchanged-upgrade",explicit=explicit)
assembly(r,args.poison=="missing")
assert [z["unit"] for z in r["processes"] if z["type"]=="rustc"]==["reader"]
if args.poison=="valid":
    assert r["native"]==29 and r["elf"]==old["clean"]
else:
    again=run("11-unchanged-missing",explicit=explicit);assembly(again,True)
    asset.write_bytes(bytes([29]))
    healed=run("12-provide-missing",explicit=explicit);assembly(healed);assert healed["native"]==29
pristine(run("13-new-settled",explicit=explicit))
asset.write_bytes(bytes([41]));lib.write_bytes(w.ORIGINAL)
new_edit=run("14-normal-source-edit",explicit=explicit);assembly(new_edit);assert new_edit["native"]==41
if args.kind=="bin":assert new_edit["rust"]==6
pristine(run("15-subsequent-noop",explicit=explicit))
clean=run("16-empty-new-source",explicit=explicit,lane="new-clean");assembly(clean)
assert clean["native"]==new_edit["native"] and clean["elf"]==new_edit["elf"]
results={p.parent.name:digest(p) for p in sorted((d/"visits").glob("*/result.json"))}
dump(d/"terminal.json",{"inputs":admission,"old":old["old"],"new":args.sha256,
    "same_full_version":digest(d/"new.version"),"raw":results,"all_passed":True})
