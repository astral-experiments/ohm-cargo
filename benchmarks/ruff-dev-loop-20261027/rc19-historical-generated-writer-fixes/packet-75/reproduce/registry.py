"""Run the original remote-registry writer in a private offline Cargo home."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess
from pathlib import Path

def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source,"sha256").hexdigest()

def dump(path, obj):
    with path.open("x") as fd:
        json.dump(obj,fd,indent=2,sort_keys=True)
        fd.write("\n")

p=argparse.ArgumentParser()
p.add_argument("directory",type=Path)
p.add_argument("sdk",type=Path)
p.add_argument("index",type=Path)
p.add_argument("archive",type=Path)
p.add_argument("--expect",choices=["follows","protected"],required=True)
p.add_argument("--without-writer",action="store_true")
a=p.parse_args()
root=a.directory.resolve()
root.mkdir(mode=0o700)
sdk=a.sdk.resolve(strict=True)
here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("watcher",here/"watch-relink-entry.py")
watcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(watcher)
for name in ("project/src","rustup/toolchains","home","target","build"):
    (root/name).mkdir(parents=True)
(root/"rustup/toolchains/ohm").symlink_to(sdk,target_is_directory=True)
source=root/"project"
(source/"Cargo.toml").write_text('[package]\nname="native_registry_reader"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nitoa="=1.0.18"\n')
registry=a.index.name
raw=(a.index/".cache/it/oa/itoa").read_bytes()
entry,=[json.loads(x) for x in raw.split(b"\0") if x.startswith(b'{"name":"itoa","vers":"1.0.18"')]
assert a.archive.name=="itoa-1.0.18.crate" and entry["cksum"]==sha(a.archive)
dest=root/"home/registry/index"/registry
(dest/".cache/it/oa").mkdir(parents=True)
(dest/".cache/it/oa/itoa").write_bytes(raw)
shutil.copyfile(a.index/"config.json",dest/"config.json")
cache=root/"home/registry/cache"/registry
cache.mkdir(parents=True)
shutil.copyfile(a.archive,cache/a.archive.name)
env={"PATH":os.environ["PATH"],"HOME":str(root),"CARGO_HOME":str(root/"home"),"RUSTUP_HOME":str(root/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","RUSTUP_AUTO_INSTALL":"0","CARGO_NET_OFFLINE":"true","CARGO_TARGET_DIR":str(root/"target"),"CARGO_BUILD_BUILD_DIR":str(root/"build"),"CARGO_INCREMENTAL":"0","LC_ALL":"C"}
cmd=[shutil.which("cargo"),"+ohm","build","--offline","-j1","--message-format=json"]
rows=[];record=None
for phase, value in [("cold",17),("during",29),("before",31),("repeat",31)]:
    if phase!="repeat":
        (source/"src/main.rs").write_text(f'fn main() {{ println!("{{}}", itoa::Buffer::new().format({value})); }}\n')
    sentinel=root/f"{phase}-owned-sentinel"
    initial=f"{phase} unrelated file\n".encode();sentinel.write_bytes(initial);inode=sentinel.stat().st_ino
    watch=None
    if record is not None and phase in ("during","before"):
        # Remove only the verified successful fingerprint in this disposable
        # fixture to force Cargo to run the immutable remote registry crate again.
        fingerprint=record.with_name("lib-itoa");assert fingerprint.is_file() and not fingerprint.is_symlink()
        fingerprint.unlink()
        if phase=="during":
            assert not record.is_symlink();watch=watcher.watch_directory(record.parent)
        else:
            record.unlink();record.symlink_to(sentinel)
    proc=subprocess.Popen(cmd,cwd=source,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        if watch is not None:watcher.install_after_delete(watch,record,sentinel,proc)
        stdout,stderr=proc.communicate(timeout=90)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if watch is not None:os.close(watch)
    (root/(phase+".stdout")).write_bytes(stdout);(root/(phase+".stderr")).write_bytes(stderr)
    assert proc.returncode==0,(phase,stderr[-800:])
    messages=list(map(json.loads,stdout.splitlines()))
    assert messages[-1].get("success") is True
    arts=[m for m in messages if m["reason"]=="compiler-artifact"]
    lib,=[m for m in arts if m["target"]["name"]=="itoa"]
    assert lib["package_id"].startswith("registry+https://github.com/rust-lang/crates.io-index#itoa@1.0.18")
    exe,=[x["executable"] for x in arts if x.get("executable")]
    native=subprocess.run([exe],env=env,capture_output=True,check=True)
    assert native.stdout==f"{value}\n".encode()
    records=[path for d in ("build","target") for path in (root/d).rglob("ohm-message-provenance-*")]
    if phase=="cold" and not a.without_writer:
        record,=records
        assert record.name=="ohm-message-provenance-lib-itoa" and not record.is_symlink()
    assert all("native_registry_reader" not in path.name for path in records)
    if a.without_writer:assert not records
    changed=initial!=sentinel.read_bytes()
    assert changed==(not a.without_writer and phase=="during" and a.expect=="follows")
    assert (sentinel.stat().st_ino!=inode)==changed
    if record:
        assert record.is_symlink()==changed
        assert isinstance(json.loads(record.read_text())["version"],int)
        assert lib["fresh"]==(phase=="repeat")
    if phase=="repeat":assert all(x["fresh"] for x in arts)
    rows.append({"phase":phase,"cargo_exit":proc.returncode,"program":value,"program_sha256":sha(Path(exe)),"record":sha(record) if record else None,"replaced_owned_sentinel":changed,"sentinel_inode_preserved":inode==sentinel.stat().st_ino,"sentinel_sha256":sha(sentinel),"stdout":sha(root/(phase+".stdout")),"stderr":sha(root/(phase+".stderr")),"cargo_units":[[m["target"]["name"],m["fresh"]] for m in arts]})
dump(root/"result.json",{"case":"registry-provenance","compiler":sha(sdk/"bin/rustc"),"cargo":sha(sdk/"bin/cargo"),"archive":entry["cksum"],"lock":sha(source/"Cargo.lock"),"index":sha(a.index/".cache/it/oa/itoa"),"expected":a.expect,"origin_writer":not a.without_writer,"rows":rows})
print([(x["phase"],x["replaced_owned_sentinel"],x["program"]) for x in rows])
