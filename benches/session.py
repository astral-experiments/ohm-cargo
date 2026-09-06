#!/usr/bin/env python3
"""Compare warm Cargo checks with a live session after real leaf-source edits.

This creates an offline workspace and separate build directories for each mode.
Only changed-source checks contribute to the reported steady-state speedup.
"""

import argparse
import json
import os
import platform
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def invoke(command, cwd, env, *, timeout=300):
    started = time.perf_counter_ns()
    with subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            stop_process(process)
            raise
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return subprocess.CompletedProcess(
        command, process.returncode, stdout, stderr
    ), elapsed_ms


def successful(result):
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(result.args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def client(cargo, command, socket, workspace, env, *, timeout=300):
    result, elapsed_ms = invoke(
        [cargo, "session", command, "--socket", str(socket), "--json"],
        workspace,
        env,
        timeout=timeout,
    )
    successful(result)
    response = json.loads(result.stdout)
    if response.get("error") or response.get("returncode", 0):
        raise RuntimeError(f"session {command} failed: {response}")
    return response, elapsed_ms


def write_workspace(workspace, crates):
    names = [f"dep_{number:04d}" for number in range(crates)]
    (workspace / "Cargo.toml").write_text(
        '[workspace]\nresolver = "2"\nmembers = ' + json.dumps([*names, "app"]) + "\n"
    )
    for number, name in enumerate(names):
        directory = workspace / name
        (directory / "src").mkdir(parents=True)
        manifest = f'[package]\nname = "{name}"\nversion = "0.0.0"\nedition = "2021"\n'
        body = "1"
        if number:
            dependency = names[number - 1]
            manifest += (
                f'\n[dependencies]\n{dependency} = {{ path = "../{dependency}" }}\n'
            )
            body = f"{dependency}::value() + 1"
        (directory / "Cargo.toml").write_text(manifest)
        (directory / "src/lib.rs").write_text(f"pub fn value() -> u64 {{ {body} }}\n")
    app = workspace / "app"
    (app / "src").mkdir(parents=True)
    (app / "Cargo.toml").write_text(
        '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\n'
        f'\n[dependencies]\n{names[-1]} = {{ path = "../{names[-1]}" }}\n'
    )
    source = app / "src/lib.rs"
    write_edit(source, names[-1], 0)
    return source, names[-1]


def write_edit(source, dependency, value):
    source.write_text(f"pub fn answer() -> u64 {{ {dependency}::value() + {value} }}\n")


def stamps(paths):
    result = []
    for path in paths:
        info = path.stat()
        result.append((info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
    return result


def summary(values):
    return {
        "median_ms": statistics.median(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def executable(value):
    found = shutil.which(value)
    if found is None:
        raise RuntimeError(f"executable not found: {value}")
    # Preserve rustup proxy names rather than following their symlinks.
    return os.path.abspath(found)


def resolve_compiler(compiler, workspace, env):
    selection = {"requested_path": compiler, "method": "provided executable"}
    rustup = shutil.which("rustup", path=env.get("PATH"))
    if rustup is None:
        rustup = shutil.which(str(Path(compiler).with_name("rustup")))
    if rustup is None:
        return compiler, selection
    try:
        is_proxy = os.path.samefile(compiler, rustup)
    except OSError:
        is_proxy = False
    if not is_proxy:
        return compiler, selection

    # Only bypass a positively identified rustup proxy. Resolve its selection
    # in the benchmark workspace before changing the shared build environment.
    rustup = os.path.abspath(rustup)
    result, _ = invoke([rustup, "which", "rustc"], workspace, env, timeout=30)
    selected = successful(result).stdout.strip()
    if not selected or not os.path.isabs(selected):
        raise RuntimeError(
            f"rustup did not return an absolute compiler path: {selected!r}"
        )
    selection.update(method="rustup which rustc", rustup_path=rustup)
    # Do not resolve symlinks: the selected path can determine rustc's sysroot.
    return selected, selection


def benchmark(args):
    cargo = executable(args.cargo)
    compiler = executable(args.rustc)
    with tempfile.TemporaryDirectory(
        prefix="cargo-session-bench-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        source, dependency = write_workspace(workspace, args.crates)
        targets = {mode: root / f"{mode}-target" for mode in ("cargo", "session")}
        socket = root / "server.sock"
        original_env = dict(os.environ)
        compiler, compiler_selection = resolve_compiler(
            compiler, workspace, original_env
        )
        common_env = dict(original_env)
        common_env.update(
            CARGO_NET_OFFLINE="true",
            CARGO_TERM_COLOR="never",
            RUSTC=compiler,
            RUSTC_WRAPPER="",
            RUSTC_WORKSPACE_WRAPPER="",
        )
        environments = {
            mode: dict(
                common_env,
                CARGO_TARGET_DIR=str(target),
                CARGO_BUILD_BUILD_DIR=str(target),
            )
            for mode, target in targets.items()
        }
        baseline_command = [cargo, "check", "-p", "app", "--lib"]
        serve_command = [
            cargo,
            "session",
            "serve",
            "--socket",
            str(socket),
            "-p",
            "app",
            "--lib",
        ]
        versions = {}
        for name, program in (("cargo", cargo), ("rustc", compiler)):
            result, _ = invoke(
                [program, "--version", "--verbose"], workspace, common_env
            )
            versions[name] = successful(result).stdout.strip()
        result, baseline_cold_ms = invoke(
            baseline_command, workspace, environments["cargo"]
        )
        successful(result)
        depfiles = {"cargo": list(targets["cargo"].rglob("app-*.d"))}
        if not depfiles["cargo"]:
            raise RuntimeError("could not find baseline app dep-info")
        previous_stamps = {"cargo": stamps(depfiles["cargo"])}

        with (root / "server.log").open("w+") as log:
            started = time.perf_counter_ns()
            server = subprocess.Popen(
                serve_command,
                cwd=workspace,
                env=environments["session"],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 30
                while True:
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(
                            f"session exited during startup:\n{log.read()}"
                        )
                    if socket.exists():
                        client(
                            cargo,
                            "status",
                            socket,
                            workspace,
                            environments["session"],
                            timeout=5,
                        )
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "session did not become ready within 30 seconds"
                        )
                    time.sleep(0.01)
                startup_ms = (time.perf_counter_ns() - started) / 1_000_000
                prepared, session_cold_ms = client(
                    cargo, "check", socket, workspace, environments["session"]
                )
                if prepared["checks"] != 1 or prepared["reused"]:
                    raise RuntimeError(f"unexpected initial preparation: {prepared}")
                depfiles["session"] = list(targets["session"].rglob("app-*.d"))
                if not depfiles["session"]:
                    raise RuntimeError("could not find session app dep-info")
                previous_stamps["session"] = stamps(depfiles["session"])
                samples = []
                for number in range(args.rounds):
                    order = (
                        ["cargo", "session"]
                        if number % 2 == 0
                        else ["session", "cargo"]
                    )
                    sample = {
                        "round": number + 1,
                        "order": order,
                        "source_value": number + 1,
                    }
                    for mode in order:
                        # Both targets last saw the preceding value. Give each
                        # mode the same changed source and a fresh timestamp.
                        write_edit(source, dependency, number + 1)
                        if mode == "cargo":
                            result, elapsed_ms = invoke(
                                baseline_command, workspace, environments[mode]
                            )
                            successful(result)
                            sample["cargo_client_ms"] = elapsed_ms
                        else:
                            response, elapsed_ms = client(
                                cargo, "check", socket, workspace, environments[mode]
                            )
                            if (
                                not response["reused"]
                                or response["pid"] != prepared["pid"]
                                or response["preparations"] != prepared["preparations"]
                                or response["checks"] != prepared["checks"] + number + 1
                            ):
                                raise RuntimeError(
                                    f"expected a retained Cargo plan: {response}"
                                )
                            sample.update(
                                session_client_ms=elapsed_ms,
                                session_server_ms=response["elapsed_ms"],
                                preparations=response["preparations"],
                                checks=response["checks"],
                            )
                        current_stamps = stamps(depfiles[mode])
                        if current_stamps == previous_stamps[mode]:
                            raise RuntimeError(
                                f"{mode} reused an unchanged app artifact"
                            )
                        previous_stamps[mode] = current_stamps
                    samples.append(sample)
                final_status, _ = client(
                    cargo, "status", socket, workspace, environments["session"]
                )
            finally:
                try:
                    if server.poll() is None and socket.exists():
                        client(
                            cargo,
                            "stop",
                            socket,
                            workspace,
                            environments["session"],
                            timeout=5,
                        )
                        server.wait(timeout=5)
                finally:
                    stop_process(server)

        baseline = summary([sample["cargo_client_ms"] for sample in samples])
        session = summary([sample["session_client_ms"] for sample in samples])
        counter_keys = ("pid", "checks", "preparations", "reused")
        return {
            "benchmark": "changed leaf library source, independently warmed targets",
            "configuration": {
                "dependency_crates": args.crates,
                "total_crates": args.crates + 1,
                "rounds": args.rounds,
                "dependency_shape": "chain",
                "offline": True,
                "compiler_wrappers_disabled": True,
                "measurement_order": "alternating",
                "baseline_command": baseline_command,
                "session_command": [
                    cargo,
                    "session",
                    "check",
                    "--socket",
                    "<private socket>",
                    "--json",
                ],
            },
            "toolchain": {
                "cargo_path": cargo,
                "rustc_path": compiler,
                "rustc_selection": compiler_selection,
                **versions,
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "cold_preparation": {
                "cargo_client_ms": baseline_cold_ms,
                "session_startup_ms": startup_ms,
                "session_client_ms": session_cold_ms,
                "session_server_ms": prepared["elapsed_ms"],
                "included_in_speedup": False,
            },
            "changed_source": {
                "cargo_client": baseline,
                "session_client": session,
                "session_server": summary(
                    [sample["session_server_ms"] for sample in samples]
                ),
                "client_speedup": baseline["median_ms"] / session["median_ms"],
            },
            "session_counters": {
                "after_preparation": {key: prepared[key] for key in counter_keys},
                "after_measurement": {key: final_status[key] for key in counter_keys},
            },
            "samples": samples,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--crates",
        type=positive_int,
        default=100,
        help="dependency crates, plus one app library (default: 100)",
    )
    parser.add_argument(
        "--rounds",
        type=positive_int,
        default=30,
        help="changed-source checks per mode (default: 30)",
    )
    parser.add_argument(
        "--cargo",
        default="cargo",
        help="Cargo executable with the built-in session command",
    )
    parser.add_argument(
        "--rustc",
        default=os.environ.get("RUSTC", "rustc"),
        help="compiler executable for both modes (default: RUSTC or rustc)",
    )
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        print(json.dumps(benchmark(args), indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
