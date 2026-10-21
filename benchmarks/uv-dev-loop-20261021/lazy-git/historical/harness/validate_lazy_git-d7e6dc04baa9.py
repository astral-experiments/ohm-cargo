#!/usr/bin/env python3
"""Run focused lazy-Git validation after both normal binaries are frozen.

This wraps existing Cargo tests and the small SSL environment comparison; it
does not define another test framework or run any performance measurements.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess

_build_spec = importlib.util.spec_from_file_location(
    "ohm_matched_builds", Path(__file__).resolve().with_name("build_normal_followups.py")
)
assert _build_spec is not None and _build_spec.loader is not None
builds = importlib.util.module_from_spec(_build_spec)
_build_spec.loader.exec_module(builds)


ROOT = builds.ROOT
SOURCE = builds.SOURCE
BASELINE = ROOT / "work/binaries/cargo-pr175-baseline-normal"
CANDIDATE = ROOT / "work/binaries/cargo-pr175-lazy-git-normal"
CARGO_TEST = ["cargo", "+1.99.0", "test", "--release", "--locked", "-p", "cargo", "-j16"]
INTEGRATION_TESTS = [
    "git::cargo_compile_simple_git_dep",
    "git::cargo_compile_git_dep_branch",
    "git::dep_with_submodule",
    "git::dep_with_relative_submodule",
    "git::dep_with_cached_submodule",
    "git::fetch_downloads",
    "git::fetch_downloads_with_git2_first_then_with_gitoxide_and_vice_versa",
    "git::corrupted_checkout",
    "registry::simple_git",
    "registry::simple_http",
    "cargo_init::simple_git::case",
    "cargo_init::auto_git::case",
    "cargo_init::git_autodetect::case",
    "fix::warns_if_no_vcs_detected",
    "fix::warns_about_dirty_working_directory",
    "fix::does_not_warn_about_clean_working_directory",
    "fix::fixes_extra_mut",
    "ohm_worktree::creates_a_worktree_without_a_previous_build",
    "ohm_worktree::existing_branches_can_be_selected_by_basename_or_operand",
    "ohm_worktree::git_failure_preserves_an_existing_destination",
    "git_auth::https_something_happens",
    "git_auth::http_auth_offered",
    "git_auth::ssh_something_happens",
]
HTTPS_TESTS = ["https::self_signed_should_fail", "https::self_signed_with_cacert"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-granted", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "work/benchmark/results/lazy-git-validation")
    parser.add_argument("--skip-https", action="store_true", help="Record an explicit skip of the Docker HTTPS tests")
    args = parser.parse_args()
    if not args.lease_granted:
        print(json.dumps({"status": "prepared; explicit parent lease required", "normal_binaries_first": True,
                          "compile": CARGO_TEST + ["--lib", "--bin", "cargo", "--test", "testsuite", "--no-run"],
                          "units": ["util::git::tests::", "cli::git_policy_tests::", "context::tests::disables_multiplexing"],
                          "integration_tests": INTEGRATION_TESTS, "https_tests": HTTPS_TESTS,
                          "ssl_cases": ["unset", "valid", "invalid"]}, indent=2))
        return

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = builds.matched_environment()
    environment["CARGO_TERM_COLOR"] = "never"
    if not args.skip_https:
        # cargo-test-macro reads this with option_env! when it is compiled.
        environment["CARGO_CONTAINER_TESTS"] = "1"
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(key, None)
    environment["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    record = {"started_at": builds.now(), "runner_sha256": builds.sha(Path(__file__).read_bytes()),
              "build_runner_sha256": builds.sha(Path(builds.__file__).read_bytes()),
              "patch_sha256": builds.sha(builds.LAZY_GIT.read_bytes()), "commands": [], "status": "running"}

    def save():
        builds.write_json(output / "report.json", record)

    def run(name, command, *, expected_tests=False, timeout=900):
        log = output / f"{len(record['commands']):02d}-{name}.log"
        entry = {"name": name, "command": command, "cwd": str(SOURCE), "started_at": builds.now(), "log": str(log)}
        record["commands"].append(entry)
        save()
        print(f"{builds.now()} {name}", flush=True)
        with log.open("xb") as stream:
            process = subprocess.Popen(command, cwd=SOURCE, env=environment, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                entry.update(finished_at=builds.now(), status="timeout", returncode=process.returncode)
                save()
                raise RuntimeError(f"Timed out: {name}; the owned process group was stopped")
        text = log.read_text(errors="replace")
        counts = [int(count) for count in re.findall(r"test result: ok\. (\d+) passed;", text)]
        entry.update(finished_at=builds.now(), returncode=status, log_sha256=builds.sha(log.read_bytes()),
                     passed_counts=counts)
        save()
        if status or (expected_tests and not any(counts)):
            print("\n".join(text.splitlines()[-45:]), flush=True)
            raise RuntimeError(f"Validation failed or selected zero tests: {name}; inspect {log}")
        return text

    try:
        frozen = {}
        for name in ("cargo-pr175-loader-v2-normal", "cargo-pr175-lazy-git-normal"):
            binary = ROOT / "work/binaries" / name
            metadata = json.loads(binary.with_name(name + ".build.json").read_text())
            strip_metadata = json.loads((binary.parent / "stripped" / (name + ".json")).read_text())
            actual_sha = builds.sha(binary.read_bytes())
            if actual_sha != metadata["sha256"] or actual_sha != strip_metadata["source_sha256"]:
                raise RuntimeError(f"Frozen binary verification failed: {name}")
            frozen[name] = {"sha256": actual_sha, "source_tree": metadata["source_tree"],
                            "stripped_sha256": strip_metadata["stripped_sha256"]}
        record["frozen_normal_binaries"] = frozen
        save()
        with builds.patched_source((builds.UPSTREAM, builds.LAZY_GIT)):
            record["source_tree"] = builds.source_snapshot()["tree"]
            save()
            run("compile-tests", CARGO_TEST + ["--lib", "--bin", "cargo", "--test", "testsuite", "--no-run"], timeout=1800)
            run("git-once-unit-tests", CARGO_TEST + ["--lib", "util::git::tests::", "--", "--nocapture", "--test-threads=1"], expected_tests=True)
            run("binary-cli-and-policy-tests", CARGO_TEST + ["--bin", "cargo", "--", "--nocapture", "--test-threads=1"], expected_tests=True)
            run("curl-compatibility-unit-test", CARGO_TEST + ["--lib", "context::tests::disables_multiplexing", "--", "--exact", "--nocapture", "--test-threads=1"], expected_tests=True)
            run("ssl-child-environments", [
                "python3", str(ROOT / "work/benchmark/validate_ssl_environment.py"),
                "--baseline", str(BASELINE), "--candidate", str(CANDIDATE),
                "--rustc", str(ROOT / "work/ohm/bin/rustc"),
                "--cert-file", "/etc/ssl/certs/ca-certificates.crt", "--cert-dir", "/usr/lib/ssl/certs",
                "--output", str(output / "ssl-environments"),
            ])
            for test in INTEGRATION_TESTS:
                run(test.replace("::", "-"), CARGO_TEST + ["--test", "testsuite", test, "--", "--exact", "--nocapture", "--test-threads=1"], expected_tests=True)
            if args.skip_https:
                record["https_skipped"] = "Explicit --skip-https"
                save()
            else:
                run("local-docker-version", ["docker", "--host", environment["DOCKER_HOST"], "version", "--format", "{{json .Server.Version}}"], timeout=30)
                existing = run("local-docker-collision-check", ["docker", "--host", environment["DOCKER_HOST"], "ps", "--all", "--filter", "name=^/cargo_test_", "--format", "{{.Names}}"], timeout=30)
                if existing.strip():
                    raise RuntimeError("Existing cargo_test_ containers prevent isolated HTTPS validation")
                environment["CARGO_CONTAINER_TESTS"] = "1"
                for test in HTTPS_TESTS:
                    run(test.replace("::", "-"), CARGO_TEST + ["--test", "testsuite", test, "--", "--exact", "--nocapture", "--test-threads=1"], expected_tests=True)
        record.update(status="passed_with_skips" if args.skip_https else "passed", finished_at=builds.now())
        save()
        print(f"{builds.now()} validation passed; original source restored; report: {output / 'report.json'}", flush=True)
    except BaseException as error:
        record.update(status="failed", finished_at=builds.now(), error=str(error))
        save()
        raise


if __name__ == "__main__":
    main()
