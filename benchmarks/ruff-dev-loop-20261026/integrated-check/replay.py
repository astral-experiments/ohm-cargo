import argparse
import hashlib
import shlex
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import time

parser = argparse.ArgumentParser(
    description="Replay one historical Ruff CLI edit under two Cargo and compiler pairs."
)
for flag in (
    "ruff",
    "sysroot",
    "cargo-home",
    "control-cargo",
    "candidate-cargo",
    "control-driver",
    "candidate-driver",
    "output",
    "scratch",
):
    parser.add_argument("--" + flag, type=Path, required=True)
args = parser.parse_args()
root, scratch = args.output.resolve(), args.scratch.resolve()
assert root != scratch and root not in scratch.parents and scratch not in root.parents
root.mkdir(parents=True, exist_ok=False)
scratch.mkdir(parents=True, exist_ok=False)
case, mode, method = "integrated-check", "check", "warm-cross"
package = "ruff"
path = "crates/ruff/src/main.rs"
ruff_checkout = args.ruff.resolve()
base = "93526150df078af7dd8fc4226cdcc469539d2001"
change = "da8ee78491f784cdead4c69e83c58bc87fd0622c"
fixture = root / "fixture"
# Use a real pinned Ruff worktree so its build script observes Git HEAD, as in development.
assert (ruff_checkout / ".git").is_file() and not subprocess.check_output(
    ["git", "--no-optional-locks", "-C", ruff_checkout, "status", "--porcelain"]
)
assert (
    subprocess.check_output(
        ["git", "--no-optional-locks", "-C", ruff_checkout, "rev-parse", "HEAD"]
    ).strip()
    == base.encode()
)
fixture.symlink_to(ruff_checkout, target_is_directory=True)
live = root / "compilers/live"
live.parent.mkdir()
subprocess.run(["cp", "-a", args.sysroot.resolve(), live], check=True)
# This tree is private. All arms see exactly the same frontend, standard library, runtime paths and compiler identity.
frontend = live / "bin/rustc"
assert "librustc_driver-774a793a844d5500.so" in subprocess.check_output(
    ["ldd", frontend], text=True
)
for arm, cargo_binary, driver in [
    ("A", args.control_cargo, args.control_driver),
    ("B", args.candidate_cargo, args.candidate_driver),
]:
    driver_dir = root / "drivers" / arm
    driver_dir.mkdir(parents=True)
    shutil.copy2(driver.resolve(), driver_dir / "librustc_driver-774a793a844d5500.so")
    cargo_dir = root / "cargos" / arm
    cargo_dir.mkdir(parents=True)
    shutil.copy2(cargo_binary.resolve(), cargo_dir / "cargo")
    ident = subprocess.check_output(
        [frontend, "-vV"],
        env=dict(os.environ, LD_LIBRARY_PATH=str(driver_dir) + ":" + str(live / "lib")),
        text=True,
    )
    assert (
        "f1a7cf9d20b2cae39e991b178b56ba06b43dc8fa" in ident
        and "LLVM version: 23.1.1" in ident
    )
(root / "rustup/toolchains").mkdir(parents=True)
(root / "rustup/toolchains/ohm").symlink_to(live)
private_home = scratch / "cargo-home"
private_home.mkdir()
subprocess.run(
    ["cp", "-a", args.cargo_home.resolve() / "registry", private_home / "registry"],
    check=True,
)
shim = live / "bin/cargo"
shim.unlink(missing_ok=True)
shim.write_text(
    '#!/bin/sh\nexec valgrind --tool=callgrind --cache-sim=no --branch-sim=no "--trace-children=$OHM_TRACE_CHILDREN" "--callgrind-out-file=$OHM_TREE_OUT/profile.%p" "--log-file=$OHM_TREE_OUT/vg.%p" '
    + shlex.quote(str(root / "compilers/cargo-native"))
    + ' "$@"\n'
)
shim.chmod(0o755)
wrap = root / "compiler-wrapper"
wrap.write_text(
    '#!/bin/sh\ncase " $* " in *" --crate-name "*) export LD_LIBRARY_PATH="$OHM_DRIVER_DIR:$OHM_SYSROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; set -- "$@" --sysroot "$OHM_SYSROOT";; esac\nexec "$@"\n'
)
wrap.chmod(0o755)
target_source = root / "fixture" / path
after = subprocess.check_output(["git", "-C", ruff_checkout, "show", base + ":" + path])
historic = subprocess.check_output(
    ["git", "-C", ruff_checkout, "show", change + "^:" + path]
)
marker = b"    let args = wild::args_os();"
block = historic[
    historic.index(b"    // support FORCE_COLOR env var") : historic.index(marker)
]
assert len(block.splitlines()) == 7 and after.count(marker) == 1 and block not in after
before = after.replace(marker, block + marker)
assert target_source.read_bytes() in (before, after)
assert (root / "fixture/.git").is_file() and subprocess.check_output(
    ["git", "--no-optional-locks", "-C", root / "fixture", "rev-parse", "HEAD"]
).strip() == base.encode()
store = scratch / case
seed = scratch / (case + "-seed")
receipts = root / "data" / case / method
receipts.mkdir(exist_ok=True, parents=True)
env = dict(
    os.environ,
    RUSTUP_HOME=str(root / "rustup"),
    RUSTUP_TOOLCHAIN="ohm",
    CARGO_HOME=str(private_home),
    CARGO_TARGET_DIR=str(store / "target"),
    CARGO_BUILD_BUILD_DIR=str(store / "shared"),
    CARGO_BUILD_JOBS="6",
    CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all",
    CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
    RUSTC=str(root / "compilers/live/bin/rustc"),
    CARGO_TERM_COLOR="never",
    LC_ALL="C.UTF-8",
    RUSTUP_AUTO_INSTALL="0",
)
cargo = [
    shutil.which("cargo"),
    "+ohm",
    mode,
    "--locked",
    "--offline",
    "--message-format=json",
]


def execute(arm, out, count=False):
    out.mkdir()
    live_cargo = root / "compilers/cargo-native"
    shutil.copyfile(root / "cargos" / arm / "cargo", live_cargo)
    os.chmod(live_cargo, 0o755)
    os.utime(live_cargo, ns=(1792940400000000000, 1792940400000000000))
    command = list(cargo)
    process_env = dict(
        env,
        OHM_STACK_ARM=arm,
        RUSTC_WRAPPER=str(root / "compiler-wrapper"),
        OHM_PACKAGE=package,
        OHM_SYSROOT=str(root / "compilers/live"),
        OHM_DRIVER_DIR=str(root / "drivers" / arm),
        SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt",
        SSL_CERT_DIR="/etc/ssl/certs",
    )
    process_env.update(
        OHM_TREE_OUT=str(out), OHM_TRACE_CHILDREN="yes" if count else "no"
    )
    begin = time.monotonic_ns()
    with (out / "stdout").open("wb") as so, (out / "stderr").open("wb") as se:
        sub = subprocess.run(
            command, cwd=root / "fixture", env=process_env, stdout=so, stderr=se
        )
    elapsed = time.monotonic_ns() - begin
    assert sub.returncode == 0, (out, (out / "stderr").read_text()[-800:])
    artifacts = [
        j
        for s in (out / "stdout").read_bytes().splitlines()
        if (j := json.loads(s))["reason"] == "compiler-artifact"
    ]
    dirty = sorted(
        (j["target"]["name"], j["target"]["kind"], j["profile"]["test"])
        for j in artifacts
        if not j["fresh"]
    )
    records = []
    if count:
        for p in sorted(out.glob("profile.*")):
            if p.stat().st_size == 0:
                continue
            lines = p.read_bytes().splitlines()
            images = [
                line[5:].split()[0].decode()
                for line in lines
                if line.startswith(b"cmd: ")
            ]
            totals = [
                int(line.split()[1]) for line in lines if line.startswith(b"totals: ")
            ]
            assert len(totals) == len(images) == 1, (p, totals, images)
            log = (out / ("vg." + p.name.split(".")[-1])).read_text()
            assert (
                "terminating with default action" not in log and "Collected :" in log
            ), (p, log[-350:])
            if images[0].endswith("/rustc"):
                selected = str(
                    (root / "drivers" / arm).resolve()
                    / "librustc_driver-774a793a844d5500.so"
                ).encode()
                aliased = str(
                    root / "drivers" / arm / "librustc_driver-774a793a844d5500.so"
                ).encode()
                assert any(selected in l or aliased in l for l in lines), (p, selected)
            records.append({"image": images[0], "instructions": totals[0]})
        assert (
            len(records) == 2
            and sum(
                Path(r["image"]) == root / "compilers/cargo-native" for r in records
            )
            == 1
            and sum(r["image"].endswith("/rustc") for r in records) == 1
        ), records
        assert len(artifacts) == 520 and dirty == [(package, ["bin"], False)], (
            len(artifacts),
            dirty,
        )
    row = {
        "arm": arm,
        "command": cargo,
        "elapsed_s": elapsed / 1e9,
        "instructions": sum(r["instructions"] for r in records),
        "processes": records,
        "dirty": dirty,
        "units": len(artifacts),
        "source": target_source.name,
    }
    roster = sorted(
        (
            j["package_id"],
            j["target"]["name"],
            j["target"]["kind"],
            j["profile"]["test"],
        )
        for j in artifacts
    )
    row["roster_sha256"] = hashlib.sha256(
        json.dumps(roster, separators=(",", ":")).encode()
    ).hexdigest()
    if count:
        expected = receipts.parent / "warm-cross" / "fresh-A" / "row.json"
        assert (
            row["roster_sha256"] == json.loads(expected.read_bytes())["roster_sha256"]
        )
        outputs = [Path(f) for j in artifacts if not j["fresh"] for f in j["filenames"]]
        assert (
            len(outputs) == 1
            and outputs[0].suffix == ".rmeta"
            and "ruff-" in outputs[0].name
        )
        metas = {
            Path(f) for j in artifacts for f in j["filenames"] if f.endswith(".rmeta")
        }
        apis = set(store.rglob("*.public-api-hash"))
        assert len(metas) > 100 and len(apis) > 10, (len(metas), len(apis))

        def digest_group(paths):
            digest = hashlib.sha256()
            for f in sorted(paths):
                digest.update(str(f.relative_to(store)).encode() + b"\0")
                with f.open("rb") as fh:
                    digest.update(hashlib.file_digest(fh, "sha256").digest())
            return digest.hexdigest()

        row["artifact_sha256"] = {
            "edited_rmeta": hashlib.sha256(outputs[0].read_bytes()).hexdigest(),
            "workspace_rmeta": digest_group(metas),
            "public_api_hashes": digest_group(apis),
        }
        row["metadata_files"] = {"rmeta": len(metas), "api": len(apis)}
    (out / "row.json").write_text(json.dumps(row, indent=2) + "\n")
    print(
        out.name, arm, round(elapsed / 1e9, 3), row["instructions"], dirty, flush=True
    )
    return row


def prepare():
    target_source.write_bytes(before)
    execute("A", receipts / "build-A")
    assert not execute("A", receipts / "fresh-A")["dirty"]
    fresh_b = execute("B", receipts / "first-B")
    print("B initial dirty count", len(fresh_b["dirty"]), flush=True)
    assert not execute("B", receipts / "fresh-B")["dirty"]
    again_a = execute("A", receipts / "again-A")
    print("A after B dirty count", len(again_a["dirty"]), flush=True)
    again_b = execute("B", receipts / "again-B")
    print("B after A dirty count", len(again_b["dirty"]), flush=True)
    assert not again_a["dirty"] and not again_b["dirty"], (again_a, again_b)
    checks = [
        json.loads((receipts / tag / "row.json").read_bytes())
        for tag in ["fresh-A", "fresh-B", "again-A", "again-B"]
    ]
    assert all(
        q["units"] == 520 and q["roster_sha256"] == checks[0]["roster_sha256"]
        for q in checks
    ), checks
    assert not seed.exists()
    subprocess.run(["cp", "-a", str(store), str(seed)], check=True)
    (seed / ".ready").write_text(str(time.time_ns()))


def measure():
    global method, receipts
    method = "tree-clone"
    receipts = root / "data" / case / method
    receipts.mkdir()
    fixed_time = int((seed / ".ready").read_text())
    rng = random.Random(385334)
    # Eight random, balanced blocks from the published seed and predeclared schedule.
    orders = []
    skip = list(range(20))
    rng.shuffle(skip)
    for _ in range(8):
        order = ("A", "B") if rng.randrange(2) else ("B", "A")
        orders.extend([order, order[::-1]])
    for idx in range(16):
        arms = orders[idx]
        pair = []
        for arm in arms:
            import tempfile

            with tempfile.TemporaryDirectory(prefix=case + "-", dir=scratch) as swap:
                swap = Path(swap)
                assert (
                    seed.is_dir()
                    and store.parent == scratch
                    and (seed / ".ready").exists()
                )
                subprocess.run(
                    ["cp", "-a", str(seed), str(swap / "prepared")], check=True
                )
                store.rename(swap / "previous")
                (swap / "prepared").rename(store)
            target_source.write_bytes(after)
            os.utime(target_source, ns=(fixed_time, fixed_time))
            out = receipts / f"{idx:02}-{arm}"
            row = execute(arm, out, True)
            assert any(j[0] == package for j in row["dirty"]), (row, seed)
            pair.append(row)
        assert (
            pair[0]["dirty"] == pair[1]["dirty"]
            and pair[0]["units"] == pair[1]["units"]
            and pair[0]["artifact_sha256"] == pair[1]["artifact_sha256"]
        )
    target_source.write_bytes(after)
    stamps = json.loads((root / "original-source-time.json").read_text())
    os.utime(target_source, ns=tuple(stamps))


original = target_source.stat()
(root / "original-source-time.json").write_text(
    json.dumps([original.st_atime_ns, original.st_mtime_ns])
)
try:
    prepare()
    measure()
finally:
    target_source.write_bytes(after)
    os.utime(target_source, ns=(original.st_atime_ns, original.st_mtime_ns))
