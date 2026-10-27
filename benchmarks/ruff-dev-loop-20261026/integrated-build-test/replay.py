"""Repeat one registered endpoint with an independently warmed Linux dependency snapshot."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
WRAPPER = '''#!/bin/sh
case " $* " in
 *" --crate-name ${OHM_PACKAGE:-} "*)
  export LD_LIBRARY_PATH="$OHM_DRIVER_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  set -- "$@" --sysroot "$OHM_SYSROOT";;
esac
exec "$@"
'''


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_states(repo, mode, inputs):
    states = {}
    patch = HERE / ("cli-seven-lines.patch" if mode == "build" else "formatter-historical.patch")
    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory)
        for rel in inputs["source"][mode + "-original"]:
            path = staged / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, path)
        subprocess.run(["git", "apply", "--no-index", "--reverse", str(patch)], cwd=staged, check=True)
        for rel in inputs["source"][mode + "-original"]:
            current = (repo / rel).read_bytes()
            reversed_bytes = (staged / rel).read_bytes()
            before, after = (reversed_bytes, current) if mode == "build" else (current, reversed_bytes)
            assert hashlib.sha256(before).hexdigest() == inputs["source"][mode + "-original"][rel]
            assert hashlib.sha256(after).hexdigest() == inputs["source"][mode + "-edited"][rel]
            states[repo / rel] = {"original": before, "changed": after}
    return states


def proof_inventory(home):
    return {
        directory.name: {file.name: sha(file) for file in sorted(directory.iterdir()) if file.is_file()}
        for directory in home.iterdir()
        if directory.name in {".ohm-registry-json-v1", ".ohm-registry-json-v2", ".ohm-git-index-sha1dc-v1"}
    }


def normalized_terminal(text, sdk):
    lines = []
    for line in text.splitlines():
        if line.startswith(f"WARNING: cannot find {sdk}/") and line.endswith("libdynamorio.so: is this an incomplete installation?"):
            continue
        if line.startswith(f"WARNING: {sdk}/") and line.endswith(" does not appear to be a valid DynamoRIO root"):
            continue
        if "Finished `" in line:
            line = re.sub(r" in (?:[0-9]+m )?[0-9]+(?:\.[0-9]+)?s$", " in ELAPSED", line)
        lines.append(line)
    return sorted(lines)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "measure"))
    parser.add_argument("mode", choices=("build", "test"))
    parser.add_argument("--backend", type=Path, required=True, help="Directory with the pinned Wild reproduction helpers")
    parser.add_argument("--ruff", type=Path, required=True, help="Clean, disposable Ruff worktree at the registered revision")
    parser.add_argument("--paths", type=Path, required=True, help="JSON containing runtime, registry and parent/candidate cargo/driver/wild paths")
    parser.add_argument("--state", type=Path, required=True, help="Per-endpoint private state under trusted ancestors")
    parser.add_argument("--output", type=Path, required=True, help="Per-endpoint receipts directory")
    parser.add_argument("--cpus", default="0,1,2,3", help="The four logical CPUs reserved for this run")
    parser.add_argument("--drrun", type=Path, required=True)
    parser.add_argument("--pidcounter", type=Path, required=True)
    return parser.parse_args()


def main():
    args = arguments()
    os.umask(0o077)
    cpus = {int(cpu) for cpu in args.cpus.split(",")}
    assert len(cpus) == 4
    os.sched_setaffinity(0, cpus)
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    repo = args.ruff.resolve(strict=True)
    git = ["git", "--no-optional-locks", "-C", str(repo)]
    assert subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() == PIN
    assert not subprocess.check_output(git + ["status", "--porcelain"])
    index = Path(subprocess.check_output(git + ["rev-parse", "--path-format=absolute", "--git-path", "index"], text=True).strip())
    index_digest = sha(index)
    plan = json.loads((HERE / "plan.json").read_bytes())
    inputs = json.loads((HERE / "exact-inputs.json").read_bytes())
    paths = json.loads(args.paths.read_bytes())
    sdk_client = args.pidcounter.resolve(strict=True)
    assert sha(sdk_client) == inputs["counters"]["DynamoRIO-client"]["sha256"]
    assert sha(args.drrun.resolve(strict=True)) == inputs["counters"]["DynamoRIO-launcher"]["sha256"]
    assert sha(Path(shutil.which("clang"))) == inputs["counters"]["clang"]["sha256"]
    states = source_states(repo, args.mode, inputs)
    saved = {path: (path.read_bytes(), path.stat()) for path in states}
    helper = load("prior_integrated", args.backend / "reproduce-integrated.py")
    mixed = helper.mixed
    native = mixed.n
    json_capture = native.capture
    verifier = load("analyzer", HERE / "verify.py")

    class Study(mixed.Study):
        def __init__(self, options):
            super().__init__(options)
            self.contents = states[self.source]
            self.env["CARGO"] = str(self.runtime / "bin/cargo")

        def invoke(self, label, arm, edit, count):
            for path, versions in states.items():
                if path != self.source and path.read_bytes() != versions[edit]:
                    assert path.read_bytes() in versions.values()
                    path.write_bytes(versions[edit])
            assert sha(index) == index_digest
            return super().invoke(label, arm, edit, count)

        def measure(self):
            self.load_oracles()
            completed = []
            arm_inventories = {}
            arm_terminals = {}
            with (self.out / "registered-observations.jsonl").open("x", buffering=1) as raw:
                for block, order in enumerate(plan["schedule"][self.mode]):
                    pair = {"order": order.split(",")}
                    for position, role in enumerate(pair["order"]):
                        arm = "parent" if role == "parent" else "stack"
                        tag = f"registered-{block:02}-{position}-{role}"
                        reset, _ = self.invoke(tag + "-reset", arm, "original", "native")
                        self.assert_oracle("original", reset, tag)
                        assert reset["dirty"] in ([], [self.unit])
                        expected = self.oracle["changed"]

                        def plain_capture(workspace, env, command, directory, state, prefix=()):
                            home = Path(env["CARGO_HOME"])
                            before = proof_inventory(home)
                            required = ".ohm-registry-json-v" + ("1" if role == "parent" else "2")
                            assert len(before[required]) >= 300
                            assert before == arm_inventories.setdefault(role, before)
                            assert shutil.disk_usage(state).free >= 24 * 1024**3
                            if role == "candidate":
                                assert len(before[".ohm-git-index-sha1dc-v1"]) == 1
                            directory.mkdir()
                            with (directory / "stdout").open("wb") as stdout, (directory / "stderr").open("wb") as stderr:
                                subprocess.run([*prefix, "cargo", "+ohm", *command, "--locked", "--offline"], cwd=workspace, env=env, stdout=stdout, stderr=stderr, check=True)
                            assert not (directory / "stdout").stat().st_size
                            terminal = (directory / "stderr").read_text()
                            assert len(re.findall(r"^\s*Compiling\s", terminal, re.M)) == 1
                            assert "Finished `" in terminal
                            lines = normalized_terminal(terminal, args.drrun.resolve().parents[1])
                            assert lines == arm_terminals.setdefault(role, lines)
                            if self.mode == "test":
                                assert len(re.findall(r"^\s*Executable\s", terminal, re.M)) == 84
                            assert all(sha(Path(target["file"])) == target["sha256"] for target in expected["outputs"].values())
                            assert proof_inventory(home) == before and sha(index) == index_digest
                            # A successful all-fresh JSON pass independently validates the complete graph.
                            verify_env = {k: v for k, v in env.items() if k not in {"OHM_COUNT_OUT", "OHM_HYBRID_OUT"}}
                            fresh = json_capture(workspace, verify_env, command, directory.with_name(directory.name + "-fresh"), state)
                            assert fresh["dirty"] == [] and not native.compare(expected, fresh)
                            assert proof_inventory(home) == before
                            return dict(fresh, dirty=[self.unit])

                        if role not in arm_terminals:
                            native.capture = plain_capture
                            try:
                                reference, _ = self.invoke(tag + "-native-terminal", arm, "changed", "native")
                            finally:
                                native.capture = json_capture
                            self.assert_oracle("changed", reference, tag)
                            assert reference["dirty"] == [self.unit]
                            repeated, _ = self.invoke(tag + "-repeat-reset", arm, "original", "native")
                            self.assert_oracle("original", repeated, tag)
                            assert repeated["dirty"] == [self.unit]
                        native.capture = plain_capture
                        try:
                            observation, counts = self.invoke(tag, arm, "changed", "full")
                        finally:
                            native.capture = json_capture
                        self.assert_oracle("changed", observation, tag)
                        counts["wild"] = counts.pop("ld.bfd")
                        pair[role] = counts
                    completed.append(pair)
                    print(json.dumps(pair, sort_keys=True), file=raw)
            assert arm_terminals["parent"] == arm_terminals["candidate"]
            print(json.dumps(verifier.statistics_for(completed), indent=2))

    helper.mixed.Study = Study
    common = inputs["common"][args.mode]
    runtime = Path(paths["runtime"]).resolve(strict=True)
    assert all(sha(runtime / rel) == digest for rel, digest in common.items())
    arms = {}
    for arm in ("parent", "candidate"):
        fields = {}
        for role in ("cargo", "driver", "wild"):
            path = Path(paths[arm][role]).resolve(strict=True)
            digest = inputs["per_arm"][arm][role]
            assert sha(path) == digest
            fields[role] = {"path": str(path), "sha256": digest}
        arms["stack" if arm == "candidate" else "parent"] = fields
    with tempfile.TemporaryDirectory() as temp:
        wrapper = Path(temp) / "compiler-wrapper"
        wrapper.write_text(WRAPPER)
        wrapper.chmod(0o755)
        spec = Path(temp) / "inputs.json"
        spec.write_text(json.dumps({"runtime": str(runtime), "registry": str(Path(paths["registry"]).resolve(strict=True)), "rustc_commit": "f1a7cf9d20b2cae39e991b178b56ba06b43dc8fa", "common_hashes": common, "wrapper": {"path": str(wrapper), "sha256": sha(wrapper)}, "arms": arms, "seeds": {"build": 1947632, "test": 1947633}}))
        sys.argv = ["reproduce-integrated.py", args.action, args.mode, str(repo), str(spec), str(args.state.resolve()), str(args.output.resolve()), "--drrun", str(args.drrun.resolve(strict=True)), "--pidcounter", str(sdk_client)]
        try:
            helper.main()
        finally:
            for path, (contents, stamp) in saved.items():
                if path.read_bytes() != contents:
                    assert path.read_bytes() in states[path].values()
                    path.write_bytes(contents)
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert sha(index) == index_digest and not subprocess.check_output(git + ["status", "--porcelain"])


if __name__ == "__main__":
    main()
