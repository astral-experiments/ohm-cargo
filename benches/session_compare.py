#!/usr/bin/env python3
"""Compare two Cargo session binaries after identical source edits.

Both sessions use the same compiler and fixture, independent warmed build
outputs, and alternating measurement order. Each round must retain preparation
and recompile the changed leaf in both sessions.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "session_benchmark", Path(__file__).with_name("session.py")
)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


class RunningSession:
    def __init__(self, cargo, args, name, root, workspace, env):
        self.cargo = cargo
        self.workspace = workspace
        self.env = env
        self.socket = root / f"{name}.sock"
        self.log = (root / f"{name}.log").open("w+")
        self.process = None
        started = time.perf_counter_ns()
        try:
            self.process = subprocess.Popen(
                [
                    cargo,
                    "session",
                    "serve",
                    "--socket",
                    str(self.socket),
                    "-p",
                    "app",
                    "--lib",
                    *args,
                ],
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
                    raise RuntimeError(f"{name} did not start:\n{self.log.read()}")
                time.sleep(0.01)
            self.call("status", timeout=5)
            self.startup_ms = (time.perf_counter_ns() - started) / 1_000_000
        except BaseException:
            self.close()
            raise

    def call(self, command, *, timeout=300):
        return bench.client(
            self.cargo,
            command,
            self.socket,
            self.workspace,
            self.env,
            timeout=timeout,
        )

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    if self.socket.exists():
                        self.call("stop", timeout=5)
                        self.process.wait(timeout=5)
                finally:
                    bench.stop_process(self.process)
        finally:
            self.log.close()


def binary_info(program, workspace, env):
    result, _ = bench.invoke([program, "--version", "--verbose"], workspace, env)
    with open(program, "rb") as binary:
        digest = hashlib.file_digest(binary, "sha256").hexdigest()
    return {
        "path": program,
        "sha256": digest,
        "version": bench.successful(result).stdout.strip(),
    }


def compare(args):
    cargos = {
        name: bench.executable(getattr(args, name)) for name in ("before", "after")
    }
    requested_compiler = bench.executable(args.rustc)
    worker = bench.executable(args.after_worker) if args.after_worker else None
    if worker:
        args.after_serve_arg.extend(["--compiler-worker", worker])
    with tempfile.TemporaryDirectory(
        prefix="cargo-session-compare-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        source, dependency = bench.write_workspace(workspace, args.crates)
        original_env = dict(os.environ)
        compiler, selection = bench.resolve_compiler(
            requested_compiler, workspace, original_env
        )
        common_env = dict(
            original_env,
            CARGO_NET_OFFLINE="true",
            CARGO_TERM_COLOR="never",
            RUSTC=compiler,
            RUSTC_WRAPPER="",
            RUSTC_WORKSPACE_WRAPPER="",
        )
        targets = {name: root / f"{name}-target" for name in cargos}
        envs = {
            name: dict(
                common_env,
                CARGO_TARGET_DIR=str(target),
                CARGO_BUILD_BUILD_DIR=str(target),
            )
            for name, target in targets.items()
        }
        info = {
            name: binary_info(cargo, workspace, common_env)
            for name, cargo in cargos.items()
        }
        info["rustc"] = binary_info(compiler, workspace, common_env)
        info["rustc"]["selection"] = selection
        if worker:
            with open(worker, "rb") as binary:
                info["after_worker"] = {
                    "path": worker,
                    "sha256": hashlib.file_digest(binary, "sha256").hexdigest(),
                }
        sessions = {}
        prepared = {}
        cold = {}
        depfiles = {}
        previous_stamps = {}
        samples = []
        status_samples = []
        try:
            for name, cargo in cargos.items():
                session = RunningSession(
                    cargo,
                    getattr(args, f"{name}_serve_arg"),
                    name,
                    root,
                    workspace,
                    envs[name],
                )
                sessions[name] = session
                response, elapsed_ms = session.call("check")
                if response["checks"] != 1 or response["reused"]:
                    raise RuntimeError(f"unexpected initial preparation: {response}")
                if worker and name == "after":
                    stats = response.get("compiler_worker") or {}
                    if (
                        not stats.get("pid")
                        or stats.get("starts") != 1
                        or stats.get("requests") != 1
                    ):
                        raise RuntimeError(
                            f"worker did not compile the initial root: {response}"
                        )
                prepared[name] = response
                cold[name] = {
                    "startup_ms": session.startup_ms,
                    "client_ms": elapsed_ms,
                    "server_ms": response["elapsed_ms"],
                }
                depfiles[name] = list(targets[name].rglob("app-*.d"))
                if not depfiles[name]:
                    raise RuntimeError(f"no leaf dep-info for {name}")
                previous_stamps[name] = bench.stamps(depfiles[name])
            for number in range(args.rounds):
                order = ["before", "after"] if number % 2 == 0 else ["after", "before"]
                sample = {
                    "round": number + 1,
                    "order": order,
                    "source_value": number + 1,
                }
                for name in order:
                    bench.write_edit(source, dependency, number + 1)
                    response, elapsed_ms = sessions[name].call("check")
                    first = prepared[name]
                    if (
                        not response["reused"]
                        or response["pid"] != first["pid"]
                        or response["preparations"] != first["preparations"]
                        or response["checks"] != first["checks"] + number + 1
                    ):
                        raise RuntimeError(
                            f"{name} did not retain preparation: {response}"
                        )
                    if worker and name == "after":
                        stats = response.get("compiler_worker") or {}
                        first_worker = first["compiler_worker"]
                        if (
                            stats.get("pid") != first_worker["pid"]
                            or stats.get("starts") != 1
                            or stats.get("requests") != number + 2
                            or stats.get("fallback_reason") is not None
                        ):
                            raise RuntimeError(
                                f"worker did not retain the compiler: {response}"
                            )
                    current_stamps = bench.stamps(depfiles[name])
                    if current_stamps == previous_stamps[name]:
                        raise RuntimeError(f"{name} reused an unchanged leaf artifact")
                    previous_stamps[name] = current_stamps
                    sample[name] = {
                        "client_ms": elapsed_ms,
                        "server_ms": response["elapsed_ms"],
                        "client_overhead_ms": elapsed_ms - response["elapsed_ms"],
                        "checks": response["checks"],
                        "preparations": response["preparations"],
                    }
                    if worker and name == "after":
                        sample[name]["compiler_worker"] = response["compiler_worker"]
                samples.append(sample)
            for number in range(args.rounds):
                order = ["before", "after"] if number % 2 == 0 else ["after", "before"]
                sample = {"round": number + 1, "order": order}
                for name in order:
                    response, elapsed_ms = sessions[name].call("status")
                    if response["pid"] != prepared[name]["pid"]:
                        raise RuntimeError(
                            f"{name} changed servers during status: {response}"
                        )
                    sample[name] = elapsed_ms
                status_samples.append(sample)
            counter_keys = ("pid", "checks", "preparations", "reused")
            counters = {}
            for name, session in sessions.items():
                final, _ = session.call("status")
                counters[name] = {
                    "after_preparation": {
                        key: prepared[name][key] for key in counter_keys
                    },
                    "after_measurement": {key: final[key] for key in counter_keys},
                }
                if worker and name == "after":
                    counters[name]["after_preparation"]["compiler_worker"] = prepared[
                        name
                    ]["compiler_worker"]
                    counters[name]["after_measurement"]["compiler_worker"] = final[
                        "compiler_worker"
                    ]
        finally:
            first_error = None
            for session in sessions.values():
                try:
                    session.close()
                except BaseException as error:  # noqa: BLE001 - close every server on interruption
                    first_error = first_error or error
            if first_error is not None and sys.exc_info()[0] is None:
                raise first_error

        summary = {
            name: {
                field: bench.summary([sample[name][field] for sample in samples])
                for field in ("client_ms", "server_ms", "client_overhead_ms")
            }
            for name in cargos
        }
        return {
            "benchmark": "paired sessions after real leaf-source edits",
            "configuration": {
                "dependency_crates": args.crates,
                "total_crates": args.crates + 1,
                "rounds": args.rounds,
                "dependency_shape": "chain",
                "offline": True,
                "measurement_order": "alternating",
                "before_serve_args": args.before_serve_arg,
                "after_serve_args": args.after_serve_arg,
            },
            "binaries": info,
            "host": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "cold_preparation": {"included_in_speedup": False, **cold},
            "changed_source": {
                **summary,
                "client_speedup": summary["before"]["client_ms"]["median_ms"]
                / summary["after"]["client_ms"]["median_ms"],
            },
            "status_ms": {
                name: bench.summary([sample[name] for sample in status_samples])
                for name in cargos
            },
            "status_samples": status_samples,
            "session_counters": counters,
            "samples": samples,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="parent PR's Cargo binary")
    parser.add_argument("--after", required=True, help="current PR's Cargo binary")
    parser.add_argument("--rustc", default=os.environ.get("RUSTC", "rustc"))
    parser.add_argument("--crates", type=bench.positive_int, default=100)
    parser.add_argument("--rounds", type=bench.positive_int, default=30)
    parser.add_argument(
        "--after-worker",
        help="worker executable; require one retained compiler PID across every check",
    )
    parser.add_argument("--before-serve-arg", action="append", default=[])
    parser.add_argument("--after-serve-arg", action="append", default=[])
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        result = compare(parser.parse_args())
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
