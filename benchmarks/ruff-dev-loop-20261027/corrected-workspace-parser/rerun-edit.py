"""Time one complete historical edit with the installed Ohm toolchain in a disposable Ruff worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("worktree", type=Path)
cli.add_argument("mode", choices=["build", "test"])
cli.add_argument("--target", type=Path, required=True)
cli.add_argument("--shared-build", type=Path, required=True)
cli.add_argument("--patch", type=Path, default=Path(__file__).parent / "patches/parser-tstring.patch")
args = cli.parse_args()
repo = args.worktree.resolve()
target = args.target.resolve()
shared = args.shared_build.resolve()
assert target != shared and not target.is_relative_to(shared) and not shared.is_relative_to(target)
env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared),
           CARGO_BUILD_JOBS=os.environ.get("CARGO_BUILD_JOBS","8"), CARGO_TERM_COLOR="never",
           CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all", CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
           GIT_OPTIONAL_LOCKS="0")


def git(*argv):
    return subprocess.check_output(["git", "--no-optional-locks", *argv], cwd=repo, env=env, text=True).strip()


assert git("rev-parse", "HEAD") == "93526150df078af7dd8fc4226cdcc469539d2001"
assert git("rev-parse", "--absolute-git-dir") != git("rev-parse", "--path-format=absolute", "--git-common-dir")
assert not git("status", "--porcelain")
index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index"))
index_digest = hashlib.sha256(index.read_bytes()).hexdigest()
patch = args.patch.resolve()
assert hashlib.sha256(patch.read_bytes()).hexdigest() == "08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff"
files = [row.split("\t", 2)[2] for row in git("apply", "--numstat", str(patch)).splitlines()]
originals = {name: ((repo / name).read_bytes(), (repo / name).stat()) for name in files}
command = ["cargo", "+ohm", args.mode]
if args.mode == "test":
    command.append("--no-run")
command += ["--locked", "--offline"]


def verify(expected_message):
    result = subprocess.check_output([*command, "--message-format=json"], cwd=repo, env=env)
    units = [row for line in result.splitlines() if (row := json.loads(line))["reason"] == "compiler-artifact"]
    assert len(units) == (501 if args.mode == "build" else 619) and all(row["fresh"] for row in units)
    (binary,) = {r["executable"] for r in units if r["target"]["name"] == "ruff" and r["target"]["kind"] == ["bin"]
                 and not r["profile"]["test"] and r["executable"]}
    oracle = subprocess.run([binary, "check", "--isolated", "--no-cache", "--target-version", "py314",
                             "--output-format", "json", "-"], cwd=repo, env=env, input=b"t'first' b'second'\n",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert oracle.returncode == 1 and not oracle.stderr
    assert expected_message in [r["message"] for r in json.loads(oracle.stdout)]


original = "Cannot mix t-string literals with string or bytes literals"
edited = "Bytes literal cannot be mixed with non-bytes literals"
subprocess.run(command,cwd=repo,env=env,check=True)
verify(original)
git("apply","--reverse","--check",str(patch))
git("apply","--reverse","--whitespace=nowarn",str(patch))
try:
    start = time.monotonic_ns()
    subprocess.run(command,cwd=repo,env=env,check=True)
    elapsed = (time.monotonic_ns()-start)/1e9
    verify(edited)
finally:
    for name,(data,stat) in originals.items():
        dest = repo / name
        dest.parent.mkdir(exist_ok=True,parents=True)
        dest.write_bytes(data)
        dest.chmod(stat.st_mode & 0o777)
        os.utime(dest,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert not git("status","--porcelain")
    assert hashlib.sha256(index.read_bytes()).hexdigest() == index_digest
subprocess.run(command,cwd=repo,env=env,check=True)
verify(original)
print(json.dumps({"command":command,"seconds":elapsed,"subsequent_all_fresh":True,"ruff_diagnostic_changed_and_restored":True}))
