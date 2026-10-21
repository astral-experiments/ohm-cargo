#!/usr/bin/env python3
"""Resume unchanged compiled tests after fixing the runner's color environment."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

path = Path(__file__).resolve().with_name("validate_lazy_git.py")
spec = importlib.util.spec_from_file_location("lazy_git_validation", path)
assert spec and spec.loader
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
builds = validation.builds
root = builds.ROOT
builds.assert_original()
output = root / "work/benchmark/results/lazy-git-validation-resumed"
output.mkdir(exist_ok=False)
previous = json.loads((root / "work/benchmark/results/lazy-git-validation/report.json").read_text())
normal = json.loads((root / "work/binaries/cargo-pr175-lazy-git-normal.build.json").read_text())
assert previous["source_tree"] == normal["source_tree"]
executable = root / "work/cargo-build/release/deps/testsuite-af6fdb42b18789ae"
cargo = root / "work/cargo-build/release/cargo"
environment = builds.matched_environment()
for key in ("CARGO_TERM_COLOR", "CARGO_TERM_HYPERLINKS", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
    environment.pop(key, None)
environment.update(RUSTUP_TOOLCHAIN="1.99.0", CARGO_CONTAINER_TESTS="1",
                   CARGO_MANIFEST_DIR=str(builds.SOURCE), DOCKER_HOST="unix:///var/run/docker.sock")
record = {
    "started_at": builds.now(), "status": "running", "source_tree": previous["source_tree"],
    "reason": "The prior UI snapshot failure came from inherited CARGO_TERM_COLOR; no Rust source changed.",
    "previous_report": str(root / "work/benchmark/results/lazy-git-validation/report.json"),
    "runner_sha256": builds.sha(Path(__file__).read_bytes()),
    "artifacts": {str(p): builds.sha(p.read_bytes()) for p in (executable, cargo)},
    "environment": {key: environment[key] for key in ("RUSTUP_TOOLCHAIN", "CARGO_CONTAINER_TESTS", "DOCKER_HOST")},
    "commands": [],
}


def save():
    builds.write_json(output / "report.json", record)


def run(name, command, test=False):
    log = output / f"{len(record['commands']):02d}-{name}.log"
    entry = {"name": name, "command": command, "started_at": builds.now(), "log": str(log)}
    record["commands"].append(entry)
    save()
    print(f"{builds.now()} {name}", flush=True)
    with log.open("xb") as stream:
        result = subprocess.run(command, cwd=builds.SOURCE, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text(errors="replace")
    counts = [int(value) for value in re.findall(r"test result: ok\. (\d+) passed;", text)]
    entry.update(finished_at=builds.now(), returncode=result.returncode,
                 log_sha256=builds.sha(log.read_bytes()), passed_counts=counts)
    save()
    if result.returncode or (test and not any(counts)):
        print("\n".join(text.splitlines()[-45:]), flush=True)
        raise RuntimeError(f"Validation failed: {name}")
    return text


try:
    start = validation.INTEGRATION_TESTS.index("cargo_init::simple_git::case")
    for test in validation.INTEGRATION_TESTS[start:]:
        run(test.replace("::", "-"), [str(executable), test, "--exact", "--nocapture", "--test-threads=1"], test=True)
    run("local-docker-version", ["docker", "--host", environment["DOCKER_HOST"], "version", "--format", "{{json .Server.Version}}"])
    existing = run("local-docker-collision-check", ["docker", "--host", environment["DOCKER_HOST"], "ps", "--all", "--filter", "name=^/cargo_test_", "--format", "{{.Names}}"])
    if existing.strip():
        raise RuntimeError("Existing cargo_test_ containers prevent isolated HTTPS validation")
    for test in validation.HTTPS_TESTS:
        run(test.replace("::", "-"), [str(executable), test, "--exact", "--nocapture", "--test-threads=1"], test=True)
    builds.assert_original()
    record.update(status="passed", finished_at=builds.now())
    save()
    print(f"{builds.now()} remaining validation passed; original source is intact", flush=True)
except BaseException as error:
    record.update(status="failed", finished_at=builds.now(), error=str(error))
    save()
    raise
