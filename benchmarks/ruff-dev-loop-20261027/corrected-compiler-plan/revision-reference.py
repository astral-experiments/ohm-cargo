"""Compare the corrected #233 driver with its own cold output and the independent matched parent."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ref = load("reference_elf", "reference.py")
series = load("series", "revision-series.py")
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("name")
cli.add_argument("candidate", type=Path)
cli.add_argument("digest")
cli.add_argument("--inside", choices=["candidate-warm", "candidate-cold"])
cli.add_argument("--before", action="store_true")
args = cli.parse_args()
assert re.fullmatch(r"revision-[a-z0-9-]+", args.name) and re.fullmatch(r"[0-9a-f]{64}", args.digest)
ref.OUT = ref.ROOT / (args.name + "-elf-reference")
ref.SUBJECTS["candidate"] = args.digest
if args.inside:
    ref.run_inside(args.inside, args.before)
    sys.exit(0)

candidate = args.candidate.resolve()
assert ref.sha(candidate) == args.digest != series.PARENT_SHA
prior = ref.ROOT / "reference-parser-v3"
with (ref.ROOT / "native-measure.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    assert not series.git("status", "--porcelain") and series.git("rev-parse", "HEAD") == series.PIN
    for mode in ("build", "test"):
        measured = ref.ROOT / ("results-" + args.name + "-" + mode)
        assert json.loads((measured / "complete.json").read_bytes())["source_clean"]
        subjects = json.loads((measured / "plan.json").read_bytes())["subjects"]
        assert subjects["driver"] == {"candidate": args.digest, "parent": series.PARENT_SHA}
    assert json.loads((prior / "complete.json").read_bytes())["source_clean"]
    ref.OUT.mkdir()
    for file in sorted(prior.glob("parent-*-*-edited.json")):
        shutil.copyfile(file, ref.OUT / file.name)
    patch = ref.ROOT / "parser-assets/patches/parser-tstring.patch"
    assert ref.sha(patch) == series.PATCH_SHA
    index = Path(series.git("rev-parse", "--path-format=absolute", "--git-path", "index"))
    index_digest = ref.sha(index)
    names = [x.split("\t", 2)[2] for x in series.git("apply", "--numstat", patch).splitlines()]
    assert all(n.startswith("crates/") and ".." not in Path(n).parts for n in names)
    files = {n: ((ref.REPO/n).read_bytes(), (ref.REPO/n).stat()) for n in names}
    for cache in ("warm", "cold"):
        if cache == "warm":
            directory = ref.ROOT / (args.name + "-private-state")
            target, shared = directory / "target-candidate", directory / "shared-candidate"
            assert target.is_dir() and shared.is_dir()
        else:
            target, shared = ref.OUT / "candidate-cold-target", ref.OUT / "candidate-cold-shared"
            target.mkdir()
            shared.mkdir()
        assert shutil.disk_usage(ref.ROOT).free > (28 if cache == "cold" else 14) * 1024**3
        wrap = ["bwrap", "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev", "--bind", "/tmp", "/tmp",
                "--bind", str(ref.OUT), str(ref.OUT),
                "--bind", str(ref.ROOT/"rustup"), str(ref.ROOT/"rustup"), "--bind", str(ref.ROOT/"registry-home"), str(ref.ROOT/"registry-home"),
                "--bind", str(target), str(ref.TARGET), "--bind", str(shared), str(ref.SHARED),
                "--ro-bind", str(ref.ROOT/"subjects/parent"), str(ref.CARGO), "--ro-bind", str(candidate), str(ref.DRIVER),
                "--", sys.executable, str(Path(__file__).resolve()), args.name, str(candidate), args.digest, "--inside", "candidate-" + cache]
        if cache == "warm":
            subprocess.run([*wrap, "--before"], check=True)
        with series.edit(patch, files, index, index_digest):
            subprocess.run(wrap, check=True)
    ref.write(ref.OUT / "complete.json", dict(source_clean=True, index_sha256=index_digest,
              candidate_driver=args.digest, parent_reference="independent release-like parent from reference-parser-v3"))
    with (ref.OUT / "statistics.json").open("wb") as out:
        subprocess.run([sys.executable, HERE/"analyze-reference.py", ref.OUT], stdout=out, check=True)
