"""Replay an ordinary Cargo-declared transitive native provider on independent stores."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("sdk", type=Path)
parser.add_argument("dest", type=Path)
parser.add_argument("--defaults-off", action="store_true")
parser.add_argument("--replacement", type=Path, required=True)
parser.add_argument("--poison", choices=["valid","malformed"], required=True)
parser.add_argument("--cold-state", choices=["absent", "valid", "malformed"])
parser.add_argument("--external-provider", action="store_true")
parser.add_argument("--stage-producer", choices=["provider", "app"])
parser.add_argument("--only-native-edit", action="store_true")
parser.add_argument("--cpus", help="optional comma-separated CPU numbers")
args = parser.parse_args()
assert not (args.external_provider and args.stage_producer)
sdk = args.sdk.resolve()
dest = args.dest.resolve()
dest.mkdir(mode=0o700)
if args.cpus:
    os.sched_setaffinity(0, {int(i) for i in args.cpus.split(",")})
# A rustup proxy selects its command by argv[0]. Preserve the cargo basename.
proxy = Path(os.environ.get("RUSTUP_PROXY_CARGO", Path.home() / ".cargo/bin/cargo")).absolute()
assert proxy.is_file() and proxy.name=="cargo"
root = dest / "project"
(dest / "rustup/toolchains").mkdir(parents=True)
(dest / "rustup/toolchains/ohm").symlink_to(sdk, target_is_directory=True)
env = dict(HOME=str(dest / "home"), CARGO_HOME=str(dest / "home/.cargo"),
           RUSTUP_HOME=str(dest / "rustup"), RUSTUP_TOOLCHAIN="ohm", RUSTUP_AUTO_INSTALL="0",
           CARGO_TARGET_DIR=str(dest / "target"), CARGO_BUILD_BUILD_DIR=str(dest / "shared"),
           CARGO_NET_OFFLINE="true", LANG="C.UTF-8", TERM="dumb",
           PATH=f"{dest}/rustup/toolchains/ohm/bin:{proxy.parent}:/usr/bin:/bin")
files = {
    "Cargo.toml": '[workspace]\nmembers=["app","middle","provider"]\nresolver="2"\n',
    "app/Cargo.toml": '[package]\nname="app"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nmiddle={path="../middle"}\n',
    "middle/Cargo.toml": '[package]\nname="middle"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nprovider={path="../provider"}\n',
    "provider/Cargo.toml": '[package]\nname="provider"\nversion="0.1.0"\nedition="2021"\n',
    "app/src/lib.rs": "pub fn value() -> i32 { middle::base() + 1 }\n",
    "middle/src/lib.rs": "pub fn base() -> i32 { provider::base() }\n",
    "provider/src/lib.rs": "pub fn base() -> i32 { 1 }\n",
    "app/tests/probe.rs": """#[link(name = "choice", kind = "static")]
extern "C" { fn choice() -> i32; }
#[test]
fn prints_choice() { println!("native-choice={}", unsafe { choice() }); }
""",
    "provider/state": "absent\n",
    "provider/build.rs": """use std::{env, fs, io, path::Path, process::Command};
fn archive(dir: &Path, value: u32) {
    fs::write(dir.join("choice.c"), format!("int choice(void) {{ return {value}; }}")).unwrap();
    assert!(Command::new("cc").current_dir(dir).args(["-c", "choice.c", "-o", "choice.o"]).status().unwrap().success());
    assert!(Command::new("ar").current_dir(dir).args(["crs", "libchoice.a", "choice.o"]).status().unwrap().success());
}
fn main() {
    println!("cargo:rerun-if-changed=state");
    let out = std::path::PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let early = out.join("early");
    let fallback = out.join("fallback");
    fs::create_dir_all(&early).unwrap();
    fs::create_dir_all(&fallback).unwrap();
    archive(&fallback, 17);
    let name = early.join("libchoice.a");
    if let Err(err) = fs::remove_file(&name) { assert_eq!(err.kind(), io::ErrorKind::NotFound); }
    match fs::read_to_string("state").unwrap().trim() {
        "valid" => archive(&early, 29),
        "malformed" => fs::write(&name, b"not a valid ar archive").unwrap(),
        "absent" => (),
        other => panic!("unexpected state {other}"),
    }
    println!("cargo:rustc-link-search=native={}", early.display());
    println!("cargo:rustc-link-search=native={}", fallback.display());
}
""",
}
if args.external_provider:
    files["provider/build.rs"] = """use std::{env, path::PathBuf};
fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    let prefix = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap()).join("prebuilt");
    println!("cargo:rustc-link-search=native={}", prefix.join("early").display());
    println!("cargo:rustc-link-search=native={}", prefix.join("fallback").display());
}
"""
    files.pop("provider/state")
for filename, contents in files.items():
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def install_prebuilt(which):
    prefix = root / "provider/prebuilt"
    marker = prefix / "installed"
    if marker.exists() and marker.read_text() == which:
        return
    for dirname, number in [("fallback", 17), ("early", 29)]:
        libdir = prefix / dirname
        libdir.mkdir(parents=True, exist_ok=True)
        archive = libdir / "libchoice.a"
        if dirname == "fallback" and archive.exists():
            continue
        archive.unlink(missing_ok=True)
        if dirname == "early" and which == "absent":
            continue
        if dirname == "early" and which == "malformed":
            archive.write_bytes(b"not a valid ar archive")
            continue
        (libdir / "choice.c").write_text(f"int choice(void) {{ return {number}; }}\n")
        subprocess.run(["cc", "-c", "choice.c", "-o", "choice.o"], cwd=libdir, check=True)
        subprocess.run(["ar", "crs", "libchoice.a", "choice.o"], cwd=libdir, check=True)
    marker.write_text(which)

def exercise(name, which, lib):
    path = dest / name
    path.mkdir()
    edits = [("app/src/lib.rs", f"pub fn value() -> i32 {{ middle::base() + {lib} }}\n")]
    if args.only_native_edit:
        edits = []
    args0 = [proxy, "+ohm"]
    if args.defaults_off:
        args0.append("-Zohm-defaults=no")
    if args.external_provider:
        install_prebuilt(which)
    elif args.stage_producer and (root / "provider/state").read_text() != which + "\n":
        (root / "provider/state").write_text(which + "\n")
        prep = path / "prepare"
        prep.mkdir()
        with (prep / "stdout").open("wb") as so, (prep / "stderr").open("wb") as se:
            before = subprocess.run(["strace", "-qq", "-f", "-s", "2600", "-e", "trace=execve", "-o", prep / "exec.log",
                                     *args0, "build", "-p", args.stage_producer, "--lib", "-vv", "--message-format=json"],
                                    cwd=root, env=env, stdout=so, stderr=se, timeout=60)
        assert before.returncode==0, (name, before.returncode)
    else:
        edits.append(("provider/state", which + "\n"))
    for filename, value in edits:
        p = root / filename
        if p.read_text() != value:
            p.write_text(value)
    cmd = list(args0)
    cmd.extend(["test", "-p", "app", "--test", "probe", "--no-run", "-vv", "--message-format=json"])
    with (path / "stdout").open("wb") as stdout, (path / "stderr").open("wb") as stderr:
        build = subprocess.run(["strace", "-qq", "-f", "-s", "2600", "-e", "trace=execve", "-o",
                                path / "exec.log", *cmd], env=env, cwd=root, stdout=stdout, stderr=stderr, timeout=120)
    products = [j for line in (path / "stdout").read_bytes().splitlines() if line.startswith(b"{")
                for j in [json.loads(line)] if j.get("reason") == "compiler-artifact" and j.get("executable") and j["target"]["name"] == "probe"]
    jobs = [s for s in (path / "exec.log").read_text().splitlines() if re.search(r'\)\s+= 0$', s) and "execve(" in s]
    images = [re.search(r'execve\("([^"]+)"', s)[1] for s in jobs]
    row = dict(phase=name, state=which, lib=lib, cargo=build.returncode, sources={p:digest(root / p) for p in files},
               rustc=[m[1] for s in jobs if (m:=re.search(r'"--crate-name", "([^"]+)"',s)) and 'rustc"' in s],
               wild=sum("/wild-ld/" in image for image in images),
               build_script_ran=any(Path(image).name in {"build_script_build", "build-script-build"} for image in images))
    if build.returncode == 0:
        assert len(products) == 1, products
        elf = Path(products[0]["executable"])
        actual = subprocess.run([elf, "--exact", "prints_choice", "--nocapture"], env=env, capture_output=True, timeout=20)
        (path / "native.stdout").write_bytes(actual.stdout)
        (path / "native.stderr").write_bytes(actual.stderr)
        matches = re.findall(rb"native-choice=(\d+)", actual.stdout)
        row.update(elf=elf.name, hash=digest(elf), native_exit=actual.returncode,
                   value=int(matches[0]) if len(matches) == 1 else None, fresh=products[0]["fresh"])
    else:
        row["link_error"] = any(b"linking with" in s or b"unknown file format" in s for s in (path / "stdout").read_bytes().splitlines())
    row["outputs"] = {f.name:digest(f) for f in path.iterdir() if f.is_file()}
    print(json.dumps({k:v for k,v in row.items() if k not in {"outputs","sources"}}, sort_keys=True), flush=True)
    return row


assert args.stage_producer == "provider" and not args.external_provider and not args.only_native_edit and not args.defaults_off
which = args.poison
other = "malformed" if which == "valid" else "valid"
first = [exercise("initial","absent",1), exercise("poison",which,2), exercise("poison-confirm",which,2)]
assert all(j["cargo"] == 0 and j["value"] == 17 for j in first)
assert first[0]["hash"] == first[1]["hash"] == first[2]["hash"]
assert not first[1]["wild"] and not first[2]["rustc"]
def snapshot():
    h=hashlib.sha256(); count=0; size=0
    for name in ("project","target","shared"):
        for p in sorted((dest/name).rglob("*")):
            if p.is_file():
                m=p.stat()
                row=[str(p.relative_to(dest)),m.st_dev,m.st_ino,m.st_size,m.st_mtime_ns,digest(p)]
                h.update(json.dumps(row,separators=(",",":")).encode()+b"\n"); count+=1;size+=m.st_size
    return {"sha256":h.hexdigest(),"files":count,"bytes":size}
def identities(path):
    return {n:{"sha256":digest(path/"bin"/n),"version":subprocess.check_output([proxy.parent/n,"+ohm","-Vv"],env=env,text=True)}
            for n in ("cargo","rustc")}
alias=dest/"rustup/toolchains/ohm"
before=identities(sdk)
before_state=snapshot()
after_sdk=args.replacement.resolve(strict=True)
next_alias=alias.with_name("new-ohm")
next_alias.symlink_to(after_sdk,target_is_directory=True)
os.replace(next_alias, alias)
assert before_state==snapshot() and alias.resolve(strict=True)==after_sdk
after=identities(after_sdk)
after_rows=[exercise("first-after-upgrade",which,2),exercise("repeat-after-upgrade",which,2),
            exercise("opposite-edit-after-upgrade",other,3),exercise("repeat-opposite",other,3),
            exercise("restored-after-upgrade","absent",1)]
record={"old":before,"new":after,"unchanged_target_and_source_snapshot":before_state,"poison":which,
        "rows":first+after_rows}
(dest/"upgrade-result.json").write_text(json.dumps(record,indent=2)+"\n")
print("preserved: %s" % before_state, flush=True)
