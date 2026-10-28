"""Reproduce first foreign-span acquisition and the backdated input edit on Linux."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sdk", type=Path, required=True, help="Compatible Ohm SDK containing bin/rustc and lib/rustlib")
parser.add_argument("--driver", type=Path, required=True, help="The selected librustc_driver .so")
parser.add_argument("--cargo", type=Path, required=True, help="The selected Cargo executable")
parser.add_argument("--fixture", type=Path, required=True, help="The seven-package heldout-fixture directory")
parser.add_argument("--expected", choices=("legacy", "ignored", "probe", "optional"), required=True)
parser.add_argument("--out", type=Path, required=True, help="A new directory")
args = parser.parse_args()
root = args.out.resolve()
root.mkdir()
temporary_sdk = tempfile.TemporaryDirectory(prefix="toolchain-", dir=root)
sdk = Path(temporary_sdk.name)
source_sdk = args.sdk.resolve()
(sdk / "bin").mkdir(parents=True)
(sdk / "lib").mkdir()
for p in (source_sdk / "bin").iterdir():
    if p.name not in {"cargo", "rustc"}:
        (sdk / "bin" / p.name).symlink_to(p.resolve())
shutil.copy2(source_sdk / "bin/rustc", sdk / "bin/rustc")
shutil.copy2(args.cargo, sdk / "bin/cargo")
needed = subprocess.check_output(["readelf", "-d", sdk / "bin/rustc"]).decode()
driver_name, = re.findall(r"Shared library: \[(librustc_driver[^\]]+)\]", needed)
for p in (source_sdk / "lib").iterdir():
    if p.name != driver_name:
        (sdk / "lib" / p.name).symlink_to(p.resolve())
shutil.copy2(args.driver.resolve(), sdk / "lib" / driver_name)
rustup = root / "rustup"
(rustup / "toolchains").mkdir(parents=True)
(rustup / "toolchains/ohm").symlink_to(sdk)
code = root / "workspace"
shutil.copytree(args.fixture.resolve(), code)
caller = code / "hold_direct/src/main.rs"
old = caller.read_text()
assert old.count(");}") == 1
caller.write_text(old.replace(");}", ');println!("escape-value={}",escape_fixture::value());}') +
                  '\nconst _: &[u8] = include_bytes!("incidental.rlib");\n')
(caller.parent / "incidental.rlib").write_bytes(b"Only a source file, no compiler extern.\n")
actual = root / "extern space/libescape_fixture.rlib"
actual.parent.mkdir()
env = dict(os.environ, RUSTUP_HOME=str(rustup), RUSTUP_AUTO_INSTALL="0",
           CARGO_HOME=str(root / "cargo-home"), CARGO_NET_OFFLINE="true", CARGO_BUILD_JOBS="4",
           CARGO_ENCODED_RUSTFLAGS="--extern\x1fescape_fixture=" + str(actual))
for var in ("RUSTUP_TOOLCHAIN", "RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
            "CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST", "CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST", "LD_LIBRARY_PATH"):
    env.pop(var, None)

def run(argv, **kw):
    return subprocess.run(argv, env=env, check=True, timeout=120, **kw)

def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

assert Path(run(["rustc", "+ohm", "--print", "sysroot"], capture_output=True, text=True).stdout.strip()).samefile(sdk)
version = run(["cargo", "+ohm", "-Vv"], capture_output=True).stdout
assert version == subprocess.check_output([sdk / "bin/cargo", "-Vv"])
identity = {"cargo": digest(sdk / "bin/cargo"), "frontend": digest(sdk / "bin/rustc"),
            "driver": digest(sdk / "lib" / driver_name), "version": version.decode()}
for value, dst in ((17, actual), (29, root / "edited.rlib")):
    src = root / "external.rs"
    src.write_text(f"pub fn value()->u32 {{{value}}}\n")
    stable = root / "stable.rlib"
    run(["rustc", "+ohm", "--crate-name", "escape_fixture", "--crate-type=rlib", "-Copt-level=1",
         "-Cmetadata=keep-identical-tag", "-Cdebuginfo=0", src, "-o", stable], capture_output=True)
    shutil.copy2(stable, dst)
start = actual.stat()
edited = root / "edited.rlib"
assert edited.stat().st_size == start.st_size and digest(edited) != digest(actual)
rows = {}
for phase in ("first", "changed", "noop", "empty"):
    if phase == "changed":
        actual.write_bytes(edited.read_bytes())
        os.utime(actual, ns=(start.st_atime_ns, start.st_mtime_ns))
    state = root / ("independent" if phase == "empty" else "warm")
    target, shared = state / "target", state / "shared"
    env.update(CARGO_TARGET_DIR=str(target), CARGO_BUILD_BUILD_DIR=str(shared))
    rec = root / "records" / phase
    rec.mkdir(parents=True)
    with (rec / "cargo.jsonl").open("wb") as stdout, (rec / "stderr").open("wb") as stderr:
        run(["strace", "-f", "-qq", "-s", "65535", "-e", "trace=execve", "-o", rec / "exec",
             "cargo", "+ohm", "build", "--offline", "-p", "hold_direct", "--message-format=json"],
            cwd=code, stdout=stdout, stderr=stderr)
    records = [json.loads(line) for line in (rec / "cargo.jsonl").read_bytes().splitlines()]
    unit, = [r for r in records if r.get("reason") == "compiler-artifact" and r["target"]["name"] == "hold_direct"]
    native = run([unit["executable"]], capture_output=True).stdout
    (rec / "native").write_bytes(native)
    value = int(native.decode().rsplit("escape-value=", 1)[1].strip())
    assert records[-1]["success"] and unit["fresh"] == (phase == "noop")
    assert value == (17 if phase == "first" else 29)
    proof, = [p for d in (target, shared) for p in d.rglob("dep-bin-hold_direct") if b"OBS1" in p.read_bytes()]
    depfile, = [p for d in (target, shared) for p in d.rglob("hold_direct*.d")
                if p.parent.name == "out" and b"ohm-foreign-span-bytes" in p.read_bytes()]
    checks, dep = proof.read_bytes(), depfile.read_bytes()
    assert checks[5] == 4 and checks[-41:-37] == b"OBS1"
    (rec / "rustc.d").write_bytes(dep)
    (rec / "fingerprint").write_bytes(checks)
    if phase in ("first", "empty"):
        assert checks[-33] == int(args.expected in ("optional", "probe"))
        lines = [row for row in dep.splitlines() if row.startswith(b"# ohm-observer-inputs-v1 ")]
        assert len(lines) == int(args.expected in ("ignored", "optional"))
        ordinary = dep
        if lines:
            nested = bytes.fromhex(lines[0].split(b" ")[3].decode())
            assert b"libescape_fixture.rlib" in nested
            ordinary = dep.replace(lines[0] + b"\n", b"", 1)
        assert (b"libescape_fixture.rlib" in ordinary) == (args.expected == "probe")
        assert any(l.startswith(b"# checksum:") and l.endswith(b"incidental.rlib") for l in ordinary.splitlines())
    else:
        assert checks[-33] == 1
    pending, full, queries = {}, 0, 0
    for raw in (rec / "exec").read_text().splitlines():
        m = re.match(r"(\d+)\s+(.*)", raw)
        if not m:
            continue
        pid, msg = m.groups()
        if msg.startswith("execve("):
            if msg.endswith("<unfinished ...>"):
                pending[pid] = msg.removesuffix("<unfinished ...>")
                continue
        elif msg.startswith("<... execve resumed>"):
            if pid not in pending:
                continue
            msg = pending.pop(pid) + msg.removeprefix("<... execve resumed>")
        else:
            continue
        executable = re.match(r'execve\("([^"]+)"', msg)
        if not msg.rstrip().endswith("= 0") or not executable:
            continue
        path = Path(executable[1])
        if path.name != "rustc" or not path.exists() or not path.samefile(sdk / "bin/rustc"):
            continue
        full += '"--crate-name", "hold_direct"' in msg and '"--print=' not in msg
        queries += '"-Zohm-observer-dep-info", "--print=sysroot"' in msg
    assert full == int(phase != "noop") and queries == int(args.expected == "probe" and phase != "noop")
    st = actual.stat()
    assert (st.st_ino, st.st_size, st.st_mtime_ns) == (start.st_ino, start.st_size, start.st_mtime_ns)
    rows[phase] = {"native": native.decode().strip(), "complete": bool(checks[-33]), "caller_full": full,
                   "capability_queries": queries, "external_sha256": digest(actual), "all_fresh": all(
        r["fresh"] for r in records if r.get("reason") == "compiler-artifact")}
out = {"expected": args.expected, "images": identity, "rows": rows}
(root / "result.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, indent=2, sort_keys=True))

temporary_sdk.cleanup()
