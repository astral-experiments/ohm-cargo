"""Reproduce the synchronized checked-in Cargo integration test using a private Ohm SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


import hashlib
def fingerprint_state(paths):
    h=hashlib.sha256(); files=0
    for top in paths:
        for f in sorted(top.rglob("*")):
            if f.is_file():
                st=f.stat()
                with f.open("rb") as fd:
                    content=hashlib.file_digest(fd,"sha256").hexdigest()
                h.update(json.dumps([top.name,f.relative_to(top).as_posix(),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,content],separators=(",",":")).encode()+b"\n")
                files+=1
    return [files,h.hexdigest()]
def upgrade(alias, original, dest, states, receipt):
    assert alias.is_symlink() and alias.resolve()==original.resolve() and dest.is_dir()
    def images():
        bound={}
        for name in ("rustc","cargo"):
            with (alias/"bin"/name).open("rb") as fd:
                bound[name]=hashlib.file_digest(fd,"sha256").hexdigest()
        return bound
    before=images(); prior=fingerprint_state(states)
    assert prior[0]>8
    swap=alias.with_name("next-private-ohm")
    assert not swap.exists() and not swap.is_symlink()
    swap.symlink_to(dest.resolve(),target_is_directory=True)
    os.replace(swap,alias)
    assert alias.resolve()==dest.resolve() and fingerprint_state(states)==prior
    receipt.write_text(json.dumps({"before":before,"after":images(),"state_files":prior[0],"state_identity_and_digest":prior[1]},indent=2)+"\n")

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--rustup-home", type=Path, required=True)
parser.add_argument("--cargo-proxy", type=Path, default=Path.home() / ".cargo/bin/cargo")
parser.add_argument("--mode", choices=("default", "seeds-on", "seeds-off", "checksums-only"), default="default")
parser.add_argument("--replacement-sdk",type=Path,required=True)
args = parser.parse_args()
base = args.directory.resolve()
base.mkdir()
packet = Path(__file__).resolve().parent
app = base / "app"
wrapper = base / "wrapper"
shutil.copytree(packet / "fixture", app)
shutil.copytree(packet / "wrapper", wrapper)
source = app / "dep/src/lib.rs"
seed = source.read_bytes()
assert seed == b"pub const VALUE: i32 = 1;"
sdk = args.rustup_home.resolve() / "toolchains/ohm"
proxy = args.cargo_proxy.absolute()
environment = {k: v for k, v in os.environ.items() if not k.startswith(("CARGO", "RUST", "OHM_", "LD_", "GIT_"))}
environment.update(HOME=str(base / "home"), CARGO_HOME=str(base / "home/.cargo"),
    RUSTUP_HOME=str(args.rustup_home.resolve()), RUSTUP_TOOLCHAIN="ohm", RUSTUP_AUTO_INSTALL="0",
    CARGO_NET_OFFLINE="true", CARGO_INCREMENTAL="0", __CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS="nightly",
    PATH=f"{sdk}/bin:{proxy.parent}:/usr/local/bin:/usr/bin:/bin", LANG="C.UTF-8",
    __CARGO_TEMPORARY_BUILD_DIR_NEW_LAYOUT_OPT_OUT="1", CARGO_LOG="cargo::compiler::fingerprint=info")
(base / "home/.cargo").mkdir(parents=True)
# The release testsuite uses a project-local target and its matching legacy private build directory.
# A private CARGO_BUILD_BUILD_DIR is unnecessary when this fixture supplies no shared build setting.
flags = {"default": [], "seeds-on": ["-Zohm-worktree-seeds=yes"], "seeds-off": ["-Zohm-worktree-seeds=no"],
    "checksums-only": ["-Zohm-worktree-seeds=no", "-Zchecksum-freshness"]}[args.mode]
rows = {}
def run(name, cwd, cmd, variables):
    folder = base / name
    folder.mkdir()
    with (folder / "stdout").open("xb") as out, (folder / "stderr").open("xb") as err:
        proc = subprocess.run(["strace", "-f", "-qq", "-s", "16384", "-e", "trace=execve", "-o", folder / "exec.log", *cmd],
            cwd=cwd, env=environment | variables, stdout=out, stderr=err)
    rustcs = []
    for line in (folder / "exec.log").read_text().splitlines():
        if 'execve(' in line and line.endswith("= 0") and '/bin/rustc",' in line and '"--crate-name"' in line:
            m = re.search(r'"--crate-name", "(dep|app)"', line)
            if m:
                rustcs.append([m[1], re.search(r'"--crate-type", "([^"]+)"', line)[1]])
    rows[name] = {"exit": proc.returncode, "rustcs": rustcs, "errors": re.findall(r'error\[(E\d+)\]', (folder/"stderr").read_text()),
         "files": {s: digest(folder/s) for s in ("stdout", "stderr", "exec.log")}}
    return rows[name]
args0 = [proxy, "+ohm"]
assert run("make-wrapper", wrapper, [*args0, "-Zohm-defaults=no", "build"], {})["exit"] == 0
log = app / "conditional-pipeline.log"
variables = {"RUSTC_WRAPPER": str(wrapper / "target/debug/conditional-metadata-pipeline-wrapper"),
    "CONDITIONAL_PIPELINE_LOG": str(log)}
cmd = [*args0, *flags, "build", "-j3"]
assert run("prime", app, cmd, variables)["exit"] == 0
assert run("prime-program", app, [app / "target/debug/app"], {})["exit"] == 0
assert (base/"prime-program/stdout").read_bytes() == b"1\n"
fp, = (app/"target/debug/.fingerprint").glob("app-*/lib-app")
log.write_bytes(b"")
source.write_bytes(seed.replace(b"= 1;", b"= 2;"))
enabled = variables | {"CONDITIONAL_PIPELINE_CONTROL": str(app)}
assert run("forced-failure", app, cmd, enabled | {"CONDITIONAL_PIPELINE_PHASE": "committed-failure",
   "CONDITIONAL_PIPELINE_PARENT_FINGERPRINT": str(fp)})["exit"] == 101
assert (app/"parent-started-early").is_file() and (app/"dependency-failed").is_file() and not (app/"parent-timed-out").exists()
assert fp.stat().st_size == 16
dep_fp, = (app/"target/debug/.fingerprint").glob("dep-*/lib-dep"); assert dep_fp.stat().st_size == 0
source.write_bytes(seed)
upgrade(sdk,sdk.resolve(),args.replacement_sdk,[app/"src",app/"dep/src",app/"target"],base/"upgrade.json")
identity = (source.stat().st_dev, source.stat().st_ino, source.stat().st_mtime_ns, digest(source))
observed = run("reverted", app, cmd, enabled | {"CONDITIONAL_PIPELINE_PHASE": "unchanged"})
success = "reverted"
if observed["exit"] != 0:
    assert observed["exit"] == 101 and observed["errors"] == ["E0460"]
    assert run("untouched-1", app, cmd, enabled | {"CONDITIONAL_PIPELINE_PHASE": "unchanged"})["exit"] == 0
    success = "untouched-1"
assert identity == (source.stat().st_dev, source.stat().st_ino, source.stat().st_mtime_ns, digest(source))
assert run("final-program", app, [app/"target/debug/app"], {})["exit"] == 0
assert (base/"final-program/stdout").read_bytes() == b"1\n"
result = {"mode": args.mode, "cargo_sha256": digest(sdk/"bin/cargo"), "rustc_sha256": digest(sdk/"bin/rustc"),
    "first_success": success, "value": 1, "phases": rows}
(base/"result.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
print(args.mode, success, rows["reverted"]["rustcs"], flush=True)
