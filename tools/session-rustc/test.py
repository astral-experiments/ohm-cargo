#!/usr/bin/env python3
"""End-to-end tests for the real worker. Requires an explicitly built Cargo and rustc-dev."""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time

MANIFEST = '''[package]
name = "app"
version = "0.1.0"
edition = "2021"
'''


def run(command, *, cwd, env, success=True):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    assert (result.returncode == 0) == success, (command, result.stdout, result.stderr)
    return result


def replace(path):
    temporary = path.with_name(path.name + ".replacement")
    shutil.copy2(path, temporary)
    os.replace(temporary, path)


class Session:
    def __init__(self, cargo, worker, project, env, socket):
        self.cargo, self.project, self.env, self.socket = cargo, project, env, socket
        self.log = open(socket.parent / "server.log", "w+")
        self.process = subprocess.Popen(
            [str(cargo), "session", "serve", "--offline", "--lib", "--compiler-worker", str(worker), "--socket", str(socket)],
            cwd=project, env=env, stdout=self.log, stderr=self.log, start_new_session=True,
        )
        deadline = time.monotonic() + 30
        while not socket.exists():
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.log.seek(0)
                raise AssertionError(self.log.read())
            time.sleep(0.01)

    def command(self, operation):
        return [str(self.cargo), "session", operation, "--socket", str(self.socket), "--json"]

    def check(self, success=True):
        result = run(self.command("check"), cwd=self.project, env=self.env, success=success)
        response = json.loads(result.stdout)
        assert (response["returncode"] == 0) == success, response
        return response

    def close(self):
        try:
            run(self.command("stop"), cwd=self.project, env=self.env)
            self.process.wait(timeout=10)
            assert self.process.returncode == 0
            assert not self.socket.exists()
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
            self.log.close()


def same_worker(response, previous, requests):
    current = response["compiler_worker"]
    assert current["pid"] == previous["compiler_worker"]["pid"], response
    assert current["starts"] == 1, response
    assert current["requests"] == requests, response
    assert current["fallback_reason"] is None, response


def native_mapping_retirement(compiler, worker, macro, root, env):
    """Implicit -L lookup must retire a worker even without Cargo's graph guard."""
    output = macro / "libcounter.so"
    run([
        str(compiler), "--edition=2021", "--crate-name", "counter",
        "--crate-type", "proc-macro", str(macro / "src/lib.rs"), "-o", str(output),
    ], cwd=root, env=env)
    source = root / "implicit_macro.rs"
    source.write_text("extern crate counter;\ncounter::counter!();\n")
    control, endpoint = socket.socketpair()
    control.settimeout(30)
    process = subprocess.Popen([
        str(worker), f"--cargo-session-fd={endpoint.fileno()}", "--",
        "--edition=2021", "--crate-name", "implicit_macro", "--crate-type", "lib",
        "--emit=metadata", "-L", str(macro), str(source),
        "-o", str(root / "implicit_macro.rmeta"),
    ], cwd=root, env=env, pass_fds=(endpoint.fileno(),),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    endpoint.close()

    def read(count):
        data = bytearray()
        while len(data) < count:
            received = control.recv(count - len(data))
            assert received, "worker closed its control channel early"
            data.extend(received)
        return bytes(data)

    def frame(limit):
        length, = struct.unpack("<Q", read(8))
        assert length <= limit, length
        return read(length)

    try:
        magic = b"cargo-rustc-worker-v1\n"
        assert read(len(magic)) == magic
        for _ in range(6):
            frame(64 * 1024)
        control.sendall(b"C")
        code, reusable = read(2)
        stdout = frame(8 * 1024 * 1024)
        stderr = frame(8 * 1024 * 1024 - len(stdout))
        assert code == 0, (stdout, stderr)
        assert reusable == 0, "a worker that loaded a procedural macro was retained"
        process.wait(timeout=10)
        assert process.returncode == 0
        assert control.recv(1) == b"", "retired worker kept its control channel open"
    finally:
        control.close()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def substituted_driver_refused(worker, driver, root, env):
    """An equal-content driver at another inode is not the selected installation."""
    with tempfile.TemporaryDirectory(prefix="loader-override-", dir=root) as temporary:
        libraries = Path(temporary)
        for library in driver.parent.iterdir():
            destination = libraries / library.name
            if library == driver:
                shutil.copyfile(library, destination)
            else:
                destination.symlink_to(library, target_is_directory=library.is_dir())
        search = [str(libraries)]
        if env.get("LD_LIBRARY_PATH"):
            search.append(env["LD_LIBRARY_PATH"])
        control, endpoint = socket.socketpair()
        control.settimeout(30)
        process = subprocess.Popen([
            str(worker), f"--cargo-session-fd={endpoint.fileno()}", "--", "--version",
        ], cwd=root, env=env | {"LD_LIBRARY_PATH": os.pathsep.join(search)},
            pass_fds=(endpoint.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        endpoint.close()
        try:
            assert control.recv(1) == b"", "substituted driver was admitted"
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode != 0, (stdout, stderr)
            assert b"loaded compiler driver does not match" in stderr, (stdout, stderr)
        finally:
            control.close()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--rustc-dev", type=Path, required=True)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    cargo, original_rustc = args.cargo.resolve(), args.rustc.resolve()
    original_sysroot = Path(subprocess.check_output([str(original_rustc), "--print", "sysroot"], text=True).strip())
    with tempfile.TemporaryDirectory(prefix="cargo-worker-test-", dir=args.scratch) as temporary:
        root = Path(temporary)
        # A private, unregistered toolchain lets replacement tests mutate only
        # their own compiler copy; all installed libraries remain read-only.
        toolchain = root / "rustup/toolchains/test-worker"
        (toolchain / "bin").mkdir(parents=True)
        compiler = toolchain / "bin/rustc"
        shutil.copy2(original_rustc, compiler)
        (toolchain / "lib").symlink_to(original_sysroot / "lib", target_is_directory=True)
        worker = root / "session-rustc"
        subprocess.run([
            "python3", str(Path(__file__).with_name("build.py")), "--rustc", str(compiler),
            "--rustc-dev", str(args.rustc_dev.resolve()), "--output", str(worker),
        ], check=True)
        project = root / "project"
        (project / "src").mkdir(parents=True)
        (project / "Cargo.toml").write_text(MANIFEST)
        source = project / "src/lib.rs"
        source.write_text('include!("../shared.rs");\n')
        shared = project / "shared.rs"
        shared.write_text('pub fn value() -> u32 { let worker_warning_once = 0; 1 }\n')
        env = os.environ.copy()
        for key in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"]:
            env.pop(key, None)
        env.update({
            "RUSTC": str(compiler), "RUSTUP_HOME": str(root / "rustup"),
            "RUSTUP_TOOLCHAIN": "test-worker", "CARGO_HOME": str(root / "cargo-home"),
            "CARGO_TARGET_DIR": str(project / "target"), "CARGO_BUILD_BUILD_DIR": str(project / "target"),
            "TMPDIR": str(root),
        })
        driver, = (original_sysroot / "lib").glob("librustc_driver-*.so")
        substituted_driver_refused(worker, driver.resolve(), root, env)
        socket_directory = root / "socket"
        socket_directory.mkdir(mode=0o700)
        session = Session(cargo, worker, project, env, socket_directory / "server.sock")
        try:
            first = session.check()
            assert first["compiler_worker"]["pid"], first
            assert "worker_warning_once" in first["stderr"], first
            same_worker(first, first, 1)
            same_worker(session.check(), first, 1)  # Cargo's own fingerprint skips rustc.
            shared.write_text('pub fn value() -> u32 { 2 }\n')
            changed = session.check()
            same_worker(changed, first, 2)
            assert "worker_warning_once" not in changed["stderr"], changed
            shared.write_text('pub fn value() -> u32 { "broken" }\n')
            broken = session.check(False)
            same_worker(broken, first, 3)
            assert "mismatched types" in broken["stderr"], broken
            shared.write_text('pub fn value() -> i32 { -1 }\n')
            fixed = session.check()
            same_worker(fixed, first, 4)
            assert "mismatched types" not in fixed["stderr"], fixed
            run([str(cargo), "check", "--offline", "--lib"], cwd=project, env=env)

            replace(worker)
            shared.write_text('pub fn value() -> i32 { -2 }\n')
            replaced = session.check()
            assert replaced["preparations"] > fixed["preparations"], replaced
            assert replaced["compiler_worker"]["pid"] != fixed["compiler_worker"]["pid"], replaced
            replace(compiler)
            shared.write_text('pub fn value() -> i32 { -3 }\n')
            replaced_compiler = session.check()
            assert replaced_compiler["preparations"] > replaced["preparations"], replaced_compiler
            assert replaced_compiler["compiler_worker"]["pid"] != replaced["compiler_worker"]["pid"], replaced_compiler

            # Block rustc in an include read, then kill it after dispatch. Opening
            # the FIFO's writer proves the compiler is waiting for this request.
            fifo = project / "blocked.rs"
            os.mkfifo(fifo)
            source.write_text('include!("../blocked.rs");\n')
            client = subprocess.Popen(session.command("check"), cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 30
            while True:
                try:
                    writer = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                    break
                except OSError as error:
                    assert error.errno == errno.ENXIO, error
                    assert client.poll() is None and time.monotonic() < deadline, "compiler never reached the FIFO"
                    time.sleep(0.01)
            os.kill(replaced_compiler["compiler_worker"]["pid"], signal.SIGKILL)
            os.close(writer)
            stdout, stderr = client.communicate(timeout=30)
            assert client.returncode != 0, (stdout, stderr)
            crashed = json.loads(stdout)
            assert "failed after dispatch" in crashed["stderr"], crashed
            assert crashed["compiler_worker"]["pid"] is None, crashed
            assert crashed["compiler_worker"]["requests"] == replaced_compiler["compiler_worker"]["requests"] + 1, crashed
            fifo.unlink()
            source.write_text('include!("../shared.rs");\n')
            recovered = session.check()
            assert recovered["compiler_worker"]["pid"] != replaced_compiler["compiler_worker"]["pid"], recovered
            assert recovered["compiler_worker"]["starts"] == 2, recovered
        finally:
            session.close()

        # User rustflags can add code-generation output after Cargo's default
        # metadata flag. Such a request must use an ordinary compiler process.
        output_env = env | {"RUSTFLAGS": "--emit=link"}
        session = Session(cargo, worker, project, output_env, socket_directory / "server.sock")
        try:
            source.write_text('pub fn value() -> u32 { 4 }\n')
            response = session.check()
            assert response["compiler_worker"]["starts"] == 0, response
            assert response["compiler_worker"]["pid"] is None, response
            assert "metadata output" in response["compiler_worker"]["fallback_reason"], response
        finally:
            session.close()

        # Build scripts add rustc-env after preparation's loader checks. The
        # actual per-unit environment must also reject loader injection.
        build_script = project / "build.rs"
        preload = root / "missing-preload.so"
        build_script.write_text(f'fn main() {{ println!("cargo::rustc-env=LD_PRELOAD={preload}"); }}\n')
        session = Session(cargo, worker, project, env, socket_directory / "server.sock")
        try:
            response = session.check()
            assert response["compiler_worker"]["starts"] == 0, response
            assert response["compiler_worker"]["pid"] is None, response
            assert "loader injection" in response["compiler_worker"]["fallback_reason"], response
        finally:
            session.close()
            build_script.unlink()

        # A stateful macro must always use fresh ordinary compiler processes.
        macro = project / "counter"
        (macro / "src").mkdir(parents=True)
        (macro / "Cargo.toml").write_text('[package]\nname="counter"\nversion="0.1.0"\nedition="2021"\n[lib]\nproc-macro=true\n')
        (macro / "src/lib.rs").write_text('''extern crate proc_macro;
use proc_macro::TokenStream;
use std::sync::atomic::{AtomicUsize, Ordering};
static CALLS: AtomicUsize = AtomicUsize::new(0);
#[proc_macro]
pub fn counter(_: TokenStream) -> TokenStream {
    let n = CALLS.fetch_add(1, Ordering::SeqCst);
    format!("const _: [(); 0] = [(); {n}];").parse().unwrap()
}
''')
        native_mapping_retirement(compiler, worker, macro, root, env)
        (project / "Cargo.toml").write_text(MANIFEST + '\n[dependencies]\ncounter={path="counter"}\n')
        source.write_text('counter::counter!();\npub fn value() -> u32 { 1 }\n')
        session = Session(cargo, worker, project, env, socket_directory / "server.sock")
        try:
            for value in [2, 3]:
                source.write_text(f'counter::counter!();\npub fn value() -> u32 {{ {value} }}\n')
                response = session.check()
                assert response["compiler_worker"]["starts"] == 0, response
                assert response["compiler_worker"]["pid"] is None, response
                assert "procedural macros" in response["compiler_worker"]["fallback_reason"], response
        finally:
            session.close()
    print("PASS: worker reuse, output boundaries, source/include edits, errors, locks, replacement, crash recovery, output fallback, loader injection fallback, driver substitution, macro fallback, native mapping retirement")


if __name__ == "__main__":
    main()
