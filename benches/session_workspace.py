#!/usr/bin/env python3
r"""Benchmark mixed commands in an isolated snapshot of a real Cargo workspace.

The default fixture is this repository's cargo-platform package, including its
serde_core dependency, integration tests, and doctests. No source in the original
checkout is changed. All commands, samples, logs, and source identities are kept
under --work-dir; no samples are removed from the statistics.

Example (run after building the Cargo binary under test):
  python3 benches/session_workspace.py --cargo /path/to/cargo \
    --rustc /path/to/toolchain/bin/rustc --rounds 20 \
    --work-dir /run/user/1000/cargo-workspace-benchmark --require-reuse

Use --parent-cargo to include an older fixed-check session as an additional check
baseline, or --baseline-cargo to compare an existing workspace daemon across all
selected commands. --repository, --revision, --manifest-path, --package, and --source can
select another Git workspace. Manifest/source paths are relative to its root.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "session_benchmark", Path(__file__).with_name("session.py")
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_dont_write_bytecode = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    _spec.loader.exec_module(_helpers)
finally:
    sys.dont_write_bytecode = _dont_write_bytecode
executable = _helpers.executable
invoke = _helpers.invoke
positive_int = _helpers.positive_int
resolve_compiler = _helpers.resolve_compiler
stop_process = _helpers.stop_process

COUNTERS = (
    "pid",
    "checks",
    "preparations",
    "command",
    "plan_id",
    "cached_plans",
    "reused",
    "revision",
    "reprepare_reason",
    "reuse_disabled_reason",
    "compiler_worker",
)
EDIT_FUNCTION = "__cargo_session_workspace_benchmark_revision"


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def checked(command, cwd, env, *, timeout=300):
    result, elapsed = invoke(command, cwd, env, timeout=timeout)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command!r}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result, elapsed


def statistics_ms(values):
    ordered = sorted(values)
    return {
        "count": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


def environment_digest(env):
    digest = hashlib.sha256()
    for key, value in sorted((os.fsencode(k), os.fsencode(v)) for k, v in env.items()):
        for part in (key, value):
            digest.update(len(part).to_bytes(8, "little"))
            digest.update(part)
    return digest.hexdigest()


def binary_info(program, workspace, env):
    result, _ = checked([program, "--version", "--verbose"], workspace, env)
    return {
        "path": program,
        "resolved_path": str(Path(program).resolve()),
        "sha256": sha256(Path(program)),
        "version": result.stdout.strip(),
    }


def snapshot(args, work, env):
    result, _ = checked(["git", "rev-parse", "--show-toplevel"], args.repository, env)
    repository = Path(result.stdout.strip()).resolve()
    result, _ = checked(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            args.revision + "^{commit}",
        ],
        repository,
        env,
    )
    revision = result.stdout.strip()
    archive = work / "workspace.tar"
    checked(
        ["git", "archive", "--format=tar", "--output", str(archive), revision],
        repository,
        env,
    )
    workspace = work / "workspace"
    workspace.mkdir()
    with tarfile.open(archive) as contents:
        contents.extractall(workspace, filter="data")
    archive.unlink()
    result, _ = checked(["git", "status", "--porcelain"], repository, env)
    return workspace, {
        "repository": str(repository),
        "revision": revision,
        "snapshot_method": "git archive; working-tree modifications are excluded",
        "original_checkout_dirty": bool(result.stdout),
    }


def fixture_path(workspace, value):
    path = (workspace / value).resolve()
    if not path.is_relative_to(workspace) or not path.is_file():
        raise RuntimeError(
            f"fixture path must name a file inside the snapshot: {value}"
        )
    return path


def config_identities(workspace, cargo_home):
    files = set()
    for directory in (workspace, *workspace.parents):
        files.update(directory / ".cargo" / name for name in ("config", "config.toml"))
    files.update(cargo_home / name for name in ("config", "config.toml"))
    return [
        {"path": str(path), "sha256": sha256(path)}
        for path in sorted(files)
        if path.is_file()
    ]


class RunningSession:
    def __init__(self, cargo, name, work, workspace, env, defaults, timeout):
        self.cargo = cargo
        self.workspace = workspace
        self.env = env
        self.timeout = timeout
        self.socket = work / f"{name}.sock"
        if len(os.fsencode(self.socket)) >= 100:
            raise RuntimeError("--work-dir is too long for a portable Unix socket path")
        self.log_path = work / f"{name}-server.log"
        self.log = self.log_path.open("w+")
        self.process = None
        self.argv = [cargo, "session", "serve", "--socket", str(self.socket), *defaults]
        started = time.perf_counter_ns()
        try:
            self.process = subprocess.Popen(
                self.argv,
                cwd=workspace,
                env=env,
                stdout=self.log,
                stderr=self.log,
                start_new_session=True,
            )
            deadline = time.monotonic() + 30
            while not self.socket.exists():
                if self.process.poll() is not None or time.monotonic() >= deadline:
                    self.log.seek(0)
                    raise RuntimeError(
                        f"session {name} did not start:\n{self.log.read()}"
                    )
                time.sleep(0.01)
            self.status = self.management("status")
            self.startup_ms = (time.perf_counter_ns() - started) / 1_000_000
        except BaseException:
            self.close()
            raise

    def command(self, operation, arguments):
        return [
            self.cargo,
            "session",
            operation,
            "--socket",
            str(self.socket),
            "--json",
            *arguments,
        ]

    def management(self, operation):
        result, _ = checked(
            self.command(operation, []), self.workspace, self.env, timeout=5
        )
        return json.loads(result.stdout)

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    if self.socket.exists():
                        self.management("stop")
                        self.process.wait(timeout=5)
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                    pass
                finally:
                    stop_process(self.process)
        finally:
            self.log.close()


def artifacts(stdout, package_id):
    selected = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue  # Test harness and doctest output is not Cargo JSON.
        if (
            isinstance(item, dict)
            and item.get("reason") == "compiler-artifact"
            and item.get("package_id") == package_id
        ):
            selected.append(
                {
                    "target": item["target"]["name"],
                    "kind": item["target"]["kind"],
                    "fresh": item["fresh"],
                    "filenames": item["filenames"],
                    "executable": item.get("executable"),
                }
            )
    return selected


def sample(
    args,
    report,
    work,
    workspace,
    env,
    cargo,
    session,
    lane,
    command,
    arguments,
    phase,
    round_number,
    order,
    package_id,
    source_value,
    source_sha,
):
    argv = (
        [cargo, command, *arguments]
        if session is None
        else session.command(command, [] if lane == "parent_session" else arguments)
    )
    result, elapsed = invoke(argv, workspace, env, timeout=args.timeout)
    number = len(report["warmup_samples"]) + len(report["samples"]) + 1
    prefix = work / "logs" / f"{number:04d}-{phase}-{command}-{lane}"
    prefix.with_suffix(".stdout").write_text(result.stdout)
    prefix.with_suffix(".stderr").write_text(result.stderr)
    item = {
        "phase": phase,
        "round": round_number,
        "command": command,
        "lane": lane,
        "lane_order": order,
        "argv": argv,
        "elapsed_ms": elapsed,
        "returncode": result.returncode,
        "source_value": source_value,
        "source_sha256": source_sha,
        "stdout_log": str(prefix.with_suffix(".stdout")),
        "stderr_log": str(prefix.with_suffix(".stderr")),
    }
    stdout = result.stdout
    protocol_error = None
    if session is not None:
        try:
            response = json.loads(result.stdout)
            item["server_ms"] = response["elapsed_ms"]
            item["counters"] = {key: response.get(key) for key in COUNTERS}
            item["session_status"] = response["status"]
            item["session_returncode"] = response["returncode"]
            stdout = response["stdout"]
            if response["pid"] != session.status["pid"]:
                protocol_error = "server identity changed"
        except (ValueError, KeyError, TypeError) as error:
            protocol_error = f"invalid session response: {error}"
        if protocol_error:
            item["protocol_error"] = protocol_error
    item["selected_artifacts"] = artifacts(stdout, package_id)
    item["compiled_artifacts"] = sum(
        not artifact["fresh"] for artifact in item["selected_artifacts"]
    )
    if command == "test":
        item["test_results"] = [
            dict(
                status=status,
                **dict(
                    zip(
                        ("passed", "failed", "ignored", "measured", "filtered_out"),
                        map(int, counts),
                    )
                ),
            )
            for status, *counts in re.findall(
                r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;",
                stdout,
                re.MULTILINE,
            )
        ]
    collection = "warmup_samples" if phase == "warmup" else "samples"
    report[collection].append(item)
    with (work / "samples.jsonl").open("a") as raw:
        raw.write(json.dumps(item) + "\n")
    print(
        f"{phase} {round_number:02d} {command:6s} {lane:14s} {elapsed:9.2f} ms",
        file=sys.stderr,
        flush=True,
    )
    if protocol_error:
        raise RuntimeError(f"{lane} {command}: {protocol_error}; see {prefix}.stdout")
    if result.returncode or item.get("session_returncode", 0):
        raise RuntimeError(f"{lane} {command} failed; see {prefix}.stdout and .stderr")
    if command == "test":
        suites = item["test_results"]
        if not any(
            suite["status"] == "ok" and suite["passed"] > 0 for suite in suites
        ) or any(suite["status"] != "ok" or suite["failed"] for suite in suites):
            raise RuntimeError(
                f"{lane} test did not report successful nonempty test execution"
            )
    if not item["selected_artifacts"]:
        raise RuntimeError(
            f"{lane} {command} emitted no selected-package artifact: {package_id}"
        )
    if phase == "edit" and all(
        artifact["fresh"] for artifact in item["selected_artifacts"]
    ):
        raise RuntimeError(f"{lane} {command} did not recompile the edited package")
    if (
        args.require_reuse
        and phase != "warmup"
        and lane == "session"
        and not item["counters"]["reused"]
    ):
        raise RuntimeError(
            f"the daemon did not reuse the {command} plan: {item['counters']}"
        )
    return item


def summarize(samples):
    summary = {}
    for phase in dict.fromkeys(item["phase"] for item in samples):
        commands = {}
        for command in dict.fromkeys(item["command"] for item in samples):
            selected = [
                item
                for item in samples
                if item["phase"] == phase and item["command"] == command
            ]
            if not selected:
                continue
            lanes = {}
            for lane in dict.fromkeys(item["lane"] for item in selected):
                values = [item for item in selected if item["lane"] == lane]
                result = statistics_ms([item["elapsed_ms"] for item in values])
                responses = [
                    item
                    for item in values
                    if "server_ms" in item and "counters" in item
                ]
                if responses:
                    result["server"] = statistics_ms(
                        [item["server_ms"] for item in responses]
                    )
                    result["reused_samples"] = sum(
                        item["counters"]["reused"] is True for item in responses
                    )
                    result["preparations"] = [
                        item["counters"]["preparations"] for item in responses
                    ]
                    result["plan_ids"] = sorted(
                        {
                            item["counters"]["plan_id"]
                            for item in responses
                            if item["counters"]["plan_id"] is not None
                        }
                    )
                lanes[lane] = result
            if "ordinary" in lanes and "session" in lanes:
                lanes["median_speedup"] = (
                    lanes["ordinary"]["median_ms"] / lanes["session"]["median_ms"]
                )
            commands[command] = lanes
        summary[phase] = commands
    return summary


def run(args, work, report):
    original_env = dict(os.environ)
    workspace, identity = snapshot(args, work, original_env)
    manifest = fixture_path(workspace, args.manifest_path)
    source = fixture_path(workspace, args.source)
    original_source = source.read_bytes()
    if EDIT_FUNCTION.encode() in original_source:
        raise RuntimeError(
            f"source already contains benchmark function {EDIT_FUNCTION}"
        )
    cargo = executable(args.cargo)
    compiler, selection = resolve_compiler(
        executable(args.rustc), workspace, original_env
    )
    compiler_bin = Path(compiler).parent
    rustdoc = executable(args.rustdoc or str(compiler_bin / "rustdoc"))
    clippy = (
        executable(str(compiler_bin / "clippy-driver"))
        if "clippy" in args.commands
        else None
    )
    cargo_clippy = executable(str(compiler_bin / "cargo-clippy")) if clippy else None
    cargo_home = Path(original_env.get("CARGO_HOME", Path.home() / ".cargo")).absolute()
    paths = [str(compiler_bin), str(cargo_home / "bin")]
    paths.extend(
        os.path.abspath(path)
        for path in original_env.get("PATH", os.defpath).split(os.pathsep)
        if path
    )
    overrides = {
        "PATH": os.pathsep.join(dict.fromkeys(paths)),
        "CARGO_HOME": str(cargo_home),
        "RUSTUP_HOME": str(
            Path(original_env.get("RUSTUP_HOME", Path.home() / ".rustup")).absolute()
        ),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TERM_COLOR": "never",
        "CARGO_TERM_PROGRESS_WHEN": "never",
        "RUSTC": compiler,
        "RUSTDOC": rustdoc,
        "RUSTC_WRAPPER": "",
        "RUSTC_WORKSPACE_WRAPPER": "",
    }
    common_env = dict(original_env, **overrides)
    report["workspace"] = {
        **identity,
        "path": str(workspace),
        "manifest": str(manifest),
        "source": str(source),
        "original_source_sha256": hashlib.sha256(original_source).hexdigest(),
    }
    report["binaries"] = {
        "cargo": binary_info(cargo, workspace, common_env),
        "rustc": {
            **binary_info(compiler, workspace, common_env),
            "selection": selection,
        },
        "rustdoc": binary_info(rustdoc, workspace, common_env),
    }
    if clippy:
        compiler_version, _ = checked([compiler, "-vV"], workspace, common_env)
        clippy_version, _ = checked([clippy, "--rustc", "-vV"], workspace, common_env)
        if compiler_version.stdout != clippy_version.stdout:
            raise RuntimeError(
                "selected clippy-driver and rustc belong to different compiler builds"
            )
        report["binaries"]["clippy_driver"] = {
            "path": clippy,
            "sha256": sha256(Path(clippy)),
            "rustc_version": clippy_version.stdout.strip(),
        }
        report["binaries"]["cargo_clippy"] = binary_info(
            cargo_clippy, workspace, common_env
        )
    report["configuration_files"] = config_identities(workspace, cargo_home)
    common_args = [
        "--manifest-path",
        str(manifest),
        "-p",
        args.package,
        "--message-format=json",
        "--offline",
        "--locked",
        *args.cargo_arg,
    ]
    metadata, _ = checked(
        [
            cargo,
            "metadata",
            "--manifest-path",
            str(manifest),
            "--offline",
            "--locked",
            "--no-deps",
            "--format-version=1",
        ],
        workspace,
        common_env,
        timeout=args.timeout,
    )
    metadata = json.loads(metadata.stdout)
    packages = [
        package for package in metadata["packages"] if package["name"] == args.package
    ]
    if len(packages) != 1:
        raise RuntimeError(
            f"expected one workspace package named {args.package}, found {len(packages)}"
        )
    package = packages[0]
    if not source.is_relative_to(Path(package["manifest_path"]).parent):
        raise RuntimeError("--source must belong to the selected package")
    report["workspace"].update(
        package_id=package["id"],
        direct_dependencies=package["dependencies"],
        workspace_members=len(metadata["workspace_members"]),
        lockfile_sha256=sha256(workspace / "Cargo.lock"),
    )
    lanes = {"ordinary": cargo, "session": cargo}
    if args.parent_cargo:
        lanes["parent_session"] = executable(args.parent_cargo)
        report["binaries"]["parent_cargo"] = binary_info(
            lanes["parent_session"], workspace, common_env
        )
    if args.baseline_cargo:
        lanes["baseline_session"] = executable(args.baseline_cargo)
        report["binaries"]["baseline_cargo"] = binary_info(
            lanes["baseline_session"], workspace, common_env
        )
    environments = {}
    report["environments"] = {}
    for lane, binary in lanes.items():
        target = work / f"target-{lane}"
        lane_overrides = dict(
            overrides,
            CARGO=binary,
            CARGO_TARGET_DIR=str(target),
            CARGO_BUILD_BUILD_DIR=str(target),
        )
        environments[lane] = dict(original_env, **lane_overrides)
        report["environments"][lane] = {
            "overrides": lane_overrides,
            "full_environment_sha256": environment_digest(environments[lane]),
        }
    sessions = {}
    report["session_startup"] = {}
    source_value = 0

    def write_source(value):
        body = f"\n\n#[doc(hidden)]\npub fn {EDIT_FUNCTION}() -> u64 {{ {value} }}\n".encode()
        source.write_bytes(original_source + body)
        return sha256(source)

    source_sha = write_source(source_value)
    try:
        for lane, binary in lanes.items():
            if lane == "ordinary":
                continue
            defaults = common_args if lane == "parent_session" else []
            session = RunningSession(
                binary,
                lane,
                work,
                workspace,
                environments[lane],
                defaults,
                args.timeout,
            )
            sessions[lane] = session
            report["session_startup"][lane] = {
                "elapsed_ms": session.startup_ms,
                "argv": session.argv,
                "status": session.status,
                "log": str(session.log_path),
            }
        for phase, rounds in [
            ("warmup", args.warmup_rounds),
            ("source_unchanged", args.rounds),
            ("edit", args.rounds),
        ]:
            for round_number in range(1, rounds + 1):
                if phase == "edit":
                    source_value = round_number
                    source_sha = write_source(source_value)
                for command_index, command in enumerate(args.commands):
                    arguments = list(common_args)
                    suffix = (
                        args.clippy_arg
                        if command == "clippy"
                        else args.test_arg
                        if command == "test"
                        else []
                    )
                    if suffix:
                        arguments.extend(["--", *suffix])
                    order = [
                        lane
                        for lane in lanes
                        if lane != "parent_session" or command == "check"
                    ]
                    if len(order) == 2:
                        if (round_number + command_index) % 2 == 0:
                            order.reverse()
                    else:
                        offset = (round_number + command_index) % len(order)
                        order = order[offset:] + order[:offset]
                    for lane in order:
                        sample(
                            args,
                            report,
                            work,
                            workspace,
                            environments[lane],
                            lanes[lane],
                            sessions.get(lane),
                            lane,
                            command,
                            arguments,
                            phase,
                            round_number,
                            order,
                            package["id"],
                            source_value,
                            source_sha,
                        )
        report["final_status"] = {
            lane: session.management("status") for lane, session in sessions.items()
        }
    finally:
        for session in sessions.values():
            session.close()
    report["summary"] = summarize(report["samples"])


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--cargo",
        required=True,
        help="Cargo binary used for both ordinary commands and the daemon",
    )
    parser.add_argument("--rustc", default=os.environ.get("RUSTC", "rustc"))
    parser.add_argument(
        "--rustdoc", help="matching rustdoc; defaults to a sibling of rustc"
    )
    parser.add_argument(
        "--parent-cargo", help="optional older fixed-check session binary"
    )
    parser.add_argument(
        "--baseline-cargo",
        help="existing workspace daemon to compare across all commands",
    )
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--revision",
        default="HEAD",
        help="exact Git commit to snapshot; uncommitted changes are excluded",
    )
    parser.add_argument("--manifest-path", default="Cargo.toml")
    parser.add_argument("--package", default="cargo-platform")
    parser.add_argument("--source", default="crates/cargo-platform/src/lib.rs")
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="new directory for the snapshot, build outputs, and all evidence (kept)",
    )
    parser.add_argument(
        "--commands",
        nargs="+",
        choices=["check", "build", "test", "clippy"],
        default=["check", "build", "test", "clippy"],
    )
    parser.add_argument(
        "--rounds",
        type=positive_int,
        default=20,
        help="samples per command/lane in each measured phase",
    )
    parser.add_argument("--warmup-rounds", type=positive_int, default=2)
    parser.add_argument(
        "--timeout", type=positive_int, default=300, help="seconds per command"
    )
    parser.add_argument(
        "--cargo-arg",
        action="append",
        default=[],
        help="extra shared Cargo argument, e.g. --cargo-arg=-j2",
    )
    parser.add_argument(
        "--clippy-arg",
        action="append",
        default=[],
        help="driver argument after --, e.g. --clippy-arg=-Dwarnings",
    )
    parser.add_argument(
        "--test-arg", action="append", default=[], help="test harness argument after --"
    )
    parser.add_argument(
        "--require-reuse",
        action="store_true",
        help="fail if any measured main-daemon command reparses its plan",
    )
    args = parser.parse_args()
    if len(set(args.commands)) != len(args.commands):
        parser.error("--commands must not contain duplicates")
    if args.parent_cargo and "check" not in args.commands:
        parser.error("--parent-cargo requires check in --commands")
    if args.work_dir:
        work = args.work_dir.absolute()
        work.mkdir(mode=0o700, parents=True, exist_ok=False)
    else:
        runtime = Path("/run/user") / str(os.getuid())
        work = Path(
            tempfile.mkdtemp(
                prefix="cargo-workspace-", dir=runtime if runtime.is_dir() else None
            )
        )
    (work / "logs").mkdir()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    report = {
        "benchmark": "same Cargo binary: real workspace mixed commands",
        "format_version": 1,
        "harness": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__)),
            "helper_sha256": sha256(Path(__file__).with_name("session.py")),
        },
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "configuration": {
            **vars(args),
            "repository": str(args.repository),
            "work_dir": str(work),
            "source_edit": f"append public {EDIT_FUNCTION} returning the round number",
            "mode_order": "alternate two-lane order; rotate three-lane check order by round plus command index",
            "source_unchanged": "source bytes stay fixed; switching commands may still recompile artifacts",
            "edit": "change one function body before each mixed-command round",
            "command_order": args.commands,
            "clock": "perf_counter_ns",
            "p95": "nearest rank: ceil(0.95 * count)",
            "outlier_filter": None,
            "cold_and_warmup_in_summary": False,
        },
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_affinity": sorted(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else None,
        },
        "warmup_samples": [],
        "samples": [],
    }
    error = None
    try:
        run(args, work, report)
        report["status"] = "complete"
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exception:
        error = exception
        report["status"] = "failed"
        report["error"] = str(exception)
        if report["samples"]:
            report["partial_summary"] = summarize(report["samples"])
    finally:
        report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_path = work / "report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "report": str(report_path),
                    "status": report.get("status", "interrupted"),
                    "summary": report.get("summary", report.get("partial_summary", {})),
                },
                indent=2,
            )
        )
    if error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
