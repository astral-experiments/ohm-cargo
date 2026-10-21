#!/usr/bin/env python3
"""Run existing integration tests against a frozen CLI, restoring the baked path."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "work/ohm-cargo"
RESULTS = ROOT / "work/production-build/results"
CLI = ROOT / "work/cargo-build/release/cargo"
HARNESS = ROOT / "work/cargo-build/release/deps/testsuite-af6fdb42b18789ae"
BACKUP = CLI.with_name(".cargo.before-build-output-production-validation")
TESTS = (
    "build_script::output_separate_lines_new",
    "build_script::output_separate_lines",
    "build_script::custom_build_script_rustc_flags_no_space",
    "build_script::custom_build_script_rustc_flags",
    "build_script::test_invalid_old_syntax",
    "build_script::rename_with_link_search_path",
    "build_script::test_invalid_new_syntax",
    "build_script::test_new_syntax_with_compatible_partial_msrv",
    "build_script::rebuild_continues_to_pass_env_vars",
    "build_script::test_new_syntax_with_old_msrv_and_reserved_prefix",
    "build_script::test_new_syntax_with_old_msrv",
    "build_script::test_new_syntax_with_old_msrv_and_unknown_prefix",
    "build_script::test_old_syntax",
    "build_script::test_old_syntax_with_old_msrv",
    "freshness::move_target_directory_with_path_deps",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def original_source():
    return subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--binary"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease-granted", action="store_true")
    parser.add_argument("--variant", choices=("candidate", "baseline"), default="candidate")
    parser.add_argument("--mode", choices=("ohm", "classic"), default="classic")
    args = parser.parse_args()
    name = "cargo-pr175-build-output-remap" if args.variant == "candidate" else "cargo-pr175"
    candidate = RESULTS / name
    command = [str(HARNESS), *TESTS, "--exact", "--nocapture", "--test-threads=1"]
    if not args.lease_granted:
        print(json.dumps({"candidate": str(candidate), "baked_cli_path": str(CLI),
                          "backup": str(BACKUP), "command": command}, indent=2))
        return

    output = ROOT / "work/benchmark/results" / f"build-output-production-{args.variant}-validation-{args.mode}"
    output.mkdir(exist_ok=False)
    prior = read(ROOT / "work/benchmark/results/lazy-git-validation-resumed/report.json")
    build = read(RESULTS / f"{name}.build.json")
    stripped = read(RESULTS / f"{name}.strip.json")
    expected = stripped["stripped_sha256"]
    expected_old = prior["artifacts"][str(CLI)]
    source_before = original_source()
    assert source_before == (ROOT / "work/patches/build-output-remap.patch").read_bytes()
    assert build["original_linker_output_sha256"] == stripped["source_sha256"]
    assert sha(candidate) == expected
    assert sha(HARNESS) == prior["artifacts"][str(HARNESS)]
    assert sha(CLI) == expected_old
    assert not CLI.is_symlink() and not BACKUP.exists()
    initial_stat = CLI.stat()
    record = {
        "started_at": now(), "status": "running", "variant": args.variant,
        "source_tree": build["observed_source_tree"], "cli_source_metadata": str(RESULTS / f"{name}.build.json"),
        "test_harness_compiled_source_tree": prior["source_tree"],
        "note": "Existing unchanged testsuite cases exercise the frozen production CLI at their baked executable path.",
        "command": command, "tests": list(TESTS), "backup": str(BACKUP),
        "mode": args.mode, "actual_cli_sha256": expected,
        "before_sha256": {str(p): sha(p) for p in (candidate, HARNESS, CLI)},
        "runner_sha256": sha(__file__), "restored": False,
    }

    def save():
        temporary = output / "report.json.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.replace(output / "report.json")

    environment = os.environ.copy()
    for key in ("CARGO_TERM_COLOR", "CARGO_TERM_HYPERLINKS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTUP_TOOLCHAIN"):
        environment.pop(key, None)
    # test_env removes RUSTC and prepends rustup's compiler when RUSTUP_TOOLCHAIN
    # is set. Select the published Ohm compiler through PATH instead.
    environment["PATH"] = str(ROOT / "work/ohm/bin") + os.pathsep + environment.get("PATH", "")
    environment.update(CARGO_HOME="/tmp/codex-cargo-home", CARGO_TARGET_DIR=str(ROOT / "work/cargo-build"),
                       CARGO_PROFILE_RELEASE_DEBUG="1",
                       CARGO_MANIFEST_DIR=str(SOURCE))
    record["environment_overrides"] = {k: environment[k] for k in (
        "CARGO_HOME", "CARGO_TARGET_DIR", "CARGO_PROFILE_RELEASE_DEBUG", "PATH", "CARGO_MANIFEST_DIR")}
    record["removed_environment_names"] = ["RUSTUP_TOOLCHAIN", "CARGO_TERM_COLOR", "CARGO_TERM_HYPERLINKS"]
    record["compiler_sha256"] = sha(ROOT / "work/ohm/bin/rustc")
    save()
    temporary = None
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def terminate(_signum, _frame):
        raise RuntimeError("validation received SIGTERM")

    signal.signal(signal.SIGTERM, terminate)
    installed_expected = expected
    try:
        descriptor, filename = tempfile.mkstemp(prefix=".cargo.production-validation-", dir=CLI.parent)
        os.close(descriptor)
        temporary = Path(filename)
        if args.mode == "ohm":
            shutil.copy2(candidate, temporary)
            assert sha(temporary) == expected
        else:
            # The existing harness forces a stable channel, which prevents the
            # supported inherited-defaults option from being read. Restore the
            # binary's actual dev channel before selecting classic defaults.
            launcher = ("#!/bin/sh\n"
                        "export __CARGO_TEST_CHANNEL_OVERRIDE_DO_NOT_USE_THIS=dev\n"
                        "export __CARGO_OHM_DEFAULTS=no\n"
                        f"exec {shlex.quote(str(candidate))} \"$@\"\n")
            temporary.write_text(launcher)
            temporary.chmod(0o755)
            installed_expected = sha(temporary)
            record.update(launcher=launcher, launcher_sha256=installed_expected,
                          effective_channel="dev", effective_ohm_defaults=False)
        os.link(CLI, BACKUP)
        record["backup_sha256"] = sha(BACKUP)
        save()
        os.replace(temporary, CLI)
        temporary = None
        assert sha(CLI) == installed_expected
        record["installed_test_entry_sha256"] = installed_expected
        save()
        print(f"{now()} running {len(TESTS)} exact tests against {expected}", flush=True)
        log = output / "tests.log"
        with log.open("xb") as stream:
            process = subprocess.Popen(command, cwd=SOURCE, env=environment, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = process.wait(timeout=300)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        text = log.read_text(errors="replace")
        selected = re.findall(r"^test (\S+) \.\.\.", text, re.MULTILINE)
        counts = re.findall(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;", text)
        record.update(returncode=returncode, executed_tests=selected, summary_counts=counts,
                      log_sha256=sha(log), tested_entry_sha256=sha(CLI),
                      tested_cli_sha256=sha(candidate))
        save()
        assert sha(CLI) == installed_expected, "Installed test entry changed during tests"
        if returncode or set(selected) != set(TESTS) or counts != [("15", "0", "0")]:
            print("\n".join(text.splitlines()[-80:]), flush=True)
            raise RuntimeError("The exact 15 production CLI tests did not all pass")
        record["status"] = "passed"
        record["passed_tests"] = selected
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if BACKUP.exists():
            assert sha(BACKUP) == expected_old, "Backup changed; preserve it for manual recovery"
            current = sha(CLI)
            if current not in (installed_expected, expected_old):
                unexpected = CLI.with_name(".cargo.unexpected-production-validation")
                assert not unexpected.exists(), "Preserve both unexpected binaries for manual recovery"
                os.link(CLI, unexpected)
                record["unexpected_cli_preserved"] = str(unexpected)
            os.replace(BACKUP, CLI)
        record["restored_cli_sha256"] = sha(CLI)
        assert record["restored_cli_sha256"] == expected_old
        final_stat = CLI.stat()
        assert (final_stat.st_ino, final_stat.st_mtime_ns, final_stat.st_mode) == (
            initial_stat.st_ino, initial_stat.st_mtime_ns, initial_stat.st_mode)
        assert original_source() == source_before
        record["after_sha256"] = {str(p): sha(p) for p in (candidate, HARNESS, CLI)}
        assert record["after_sha256"] == record["before_sha256"]
        record.update(restored=True, source_unchanged=True, finished_at=now())
        save()
        signal.signal(signal.SIGTERM, previous_sigterm)
    print(f"{now()} all 15 tests passed; original CLI and source restored", flush=True)


if __name__ == "__main__":
    main()
