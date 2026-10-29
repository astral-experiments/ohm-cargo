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
parser.add_argument("--replacement", type=Path,required=True)
parser.add_argument("--poison",choices=["valid","malformed"],required=True)
parser.add_argument("--defaults-off", action="store_true")
parser.add_argument("--cold-state", choices=["absent", "valid", "malformed"])
parser.add_argument("--external-provider", action="store_true")
parser.add_argument("--stage-producer", choices=["provider", "app"])
parser.add_argument("--only-native-edit", action="store_true")
parser.add_argument("--cpus", help="optional comma-separated CPU numbers")
args = parser.parse_args()
assert args.external_provider and not args.stage_producer
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
    "Cargo.toml": '[workspace]\nmembers=["app"]\nresolver="2"\n',
    "app/Cargo.toml": '[package]\nname="app"\nversion="0.1.0"\nedition="2021"\n',
    "app/src/lib.rs": "pub fn value() -> i32 { 1 + 1 }\n",
    "app/tests/probe.rs": """#[test]
fn prints_choice() { println!("native-choice=17"); }
""",
}
for filename, contents in files.items():
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def install_prebuilt(which):
    sysdir = Path("/usr/lib/gcc/x86_64-linux-gnu/13")
    private = Path(os.environ["OHM_REPLAY_PRIVATE_INPUTS"]).resolve(strict=True)
    config = json.loads((private / "mount-identity.json").read_bytes())
    assert os.geteuid() == 1000 and os.readlink("/proc/self/ns/mnt") != config["initial"]
    p = sysdir / "libgcc_s.so"
    assert os.path.samefile(p,private/"private-libgcc-script")
    assert next(l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff:"))=="0000000000000000"
    assert p.is_file() and not p.is_symlink() and p.stat().st_uid==os.geteuid()
    material = (private / "materials" / (which + ".a")).read_bytes()
    if p.read_bytes()!=material:
        with p.open("r+b") as out:
            out.seek(0); out.write(material); out.truncate(); out.flush(); os.fsync(out.fileno())
    assert digest(p) == hashlib.sha256(material).hexdigest()

def exercise(name, which, lib):
    path = dest / name
    path.mkdir()
    edits = [("app/src/lib.rs", f"pub fn value() -> i32 {{ 1 + {lib} }}\n")]
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

assert not args.stage_producer and args.external_provider and not args.only_native_edit and not args.defaults_off
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
assert before["cargo"]["version"]==after["cargo"]["version"] and before["rustc"]==after["rustc"]
after_rows=[exercise("first-after-upgrade",which,2),exercise("repeat-after-upgrade",which,2),
            exercise("opposite-edit-after-upgrade",other,3),exercise("repeat-opposite",other,3),
            exercise("restored-after-upgrade","absent",1)]
record={"old":before,"new":after,"unchanged_target_and_source_snapshot":before_state,"poison":which,
        "rows":first+after_rows}
(dest/"upgrade-result.json").write_text(json.dumps(record,indent=2)+"\n")
print("preserved: %s" % before_state, flush=True)
