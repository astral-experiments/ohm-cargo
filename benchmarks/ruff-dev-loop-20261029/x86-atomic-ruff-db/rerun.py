"""Replay the Ruff edit in an isolated clone and count actual compiler and native linker processes."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import CASES, reassemble

RUFF = "93526150df078af7dd8fc4226cdcc469539d2001"
EDIT = "11a6493c944a9b78ebc72fa0b792ab706eae093a"
SOURCE = "crates/ruff_db/src/system/memory_fs.rs"
CALLER = """use ruff_db::system::MemoryFileSystem;
fn main() {
    let fs = MemoryFileSystem::new();
    fs.write_file_all("a/a.py", b"ok").unwrap();
    println!("{:?}", fs.remove_directory("a").unwrap_err().kind());
}
"""


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ruff",
        type=Path,
        required=True,
        help="local Git repository containing the two pinned Ruff revisions",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="Cargo registry directory with the locked offline cache and index",
    )
    parser.add_argument(
        "--work",
        type=Path,
        required=True,
        help="new private directory on one filesystem",
    )
    args = parser.parse_args()
    source = args.ruff.resolve(strict=True)
    reg = args.registry.resolve(strict=True)
    work = args.work.absolute()
    if sys.platform != "linux" or os.uname().machine != "x86_64" or work.exists():
        raise SystemExit("a new work directory and Linux x86-64 are required")
    if shutil.disk_usage(work.parent).free < 8 * 2**30:
        raise SystemExit("the fresh and retained build stores need at least 8 GiB free")
    work.mkdir(mode=0o700)
    clone = work / "ruff"
    target = work / "target"
    shared = work / "shared"
    raw = work / "raw"
    ch = work / "cargo-home"
    for p in (target, shared, raw, work / "tmp", ch / "registry"):
        p.mkdir(parents=True)
    shutil.copytree(reg / "index", ch / "registry/index", symlinks=True)
    (ch / "registry/cache").symlink_to(reg / "cache", target_is_directory=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--local",
            "--shared",
            "--no-checkout",
            "--",
            source,
            clone,
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            clone,
            "-c",
            "advice.detachedHead=false",
            "checkout",
            "--quiet",
            "--detach",
            RUFF,
        ],
        check=True,
    )

    def git_blob(rev):
        return subprocess.check_output(
            ["git", "-C", source, "show", rev + ":" + SOURCE]
        )

    original = git_blob(RUFF)
    historical = git_blob(EDIT + "^")
    changed = git_blob(EDIT)
    previous = b"return Err(directory_not_empty());"
    current = b"return Err(io::Error::from(io::ErrorKind::DirectoryNotEmpty));"
    assert (
        historical.count(previous)
        == changed.count(current)
        == original.count(current)
        == 1
        and original == (clone / SOURCE).read_bytes()
    )
    helper = (
        historical[historical.index(b"fn directory_not_empty()") :].split(b"}\n", 1)[0]
        + b"}\n\n"
    )
    assert original.count(b"fn invalid_utf8()") == 1 and helper not in original
    old = original.replace(current, previous).replace(
        b"fn invalid_utf8()", helper + b"fn invalid_utf8()"
    )
    bad = original.replace(current, b"return Err(ohm_missing_directory_error());")
    env = {
        k: os.environ[k]
        for k in ("HOME", "USER", "LOGNAME", "PATH", "RUSTUP_HOME")
        if k in os.environ
    }
    env.update(
        CARGO_HOME=str(ch),
        CARGO_TARGET_DIR=str(target),
        CARGO_BUILD_BUILD_DIR=str(shared),
        TMPDIR=str(work / "tmp"),
        CARGO_NET_OFFLINE="true",
        CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",
        CARGO_TERM_COLOR="never",
        RUSTUP_AUTO_INSTALL="0",
        LC_ALL="C",
        TZ="UTC",
    )

    def which(tool):
        return Path(
            subprocess.check_output(
                ["rustup", "which", "--toolchain", "ohm", tool], env=env, text=True
            ).strip()
        )

    rustc = which("rustc")
    cargo = which("cargo")
    wild = (
        rustc.parent.parent / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    )
    (driver,) = (rustc.parent.parent / "lib").glob("librustc_driver-*.so")
    identities = {
        k: sha(p)
        for k, p in (
            ("cargo", cargo),
            ("rustc", rustc),
            ("driver", driver),
            ("wild", wild),
        )
    }
    (work / "reader.rs").write_text(CALLER)
    results = {}
    products = {}

    def run_program(av, expect):
        p = subprocess.run(av, cwd=clone, env=env, capture_output=True)
        assert p.returncode == expect, (str(av[0]), p.returncode, p.stderr[-600:])
        return p.stdout

    def run(tag, kind, version):
        slot = raw / tag
        slot.mkdir()
        sub = ["build"] if kind == "build" else ["test", "--lib", "--no-run"]
        av = [
            "strace",
            "-ff",
            "-qq",
            "-s",
            "131072",
            "-e",
            "trace=execve",
            "-o",
            slot / "exec",
            "cargo",
            "+ohm",
            *sub,
            "--locked",
            "--offline",
            "-p",
            "ruff_db",
            "-j4",
            "--message-format=json",
        ]
        with (slot / "stdout").open("xb") as so, (slot / "stderr").open("xb") as se:
            ret = subprocess.run(
                av, cwd=clone, env=env, stdout=so, stderr=se
            ).returncode
        valid = version != "bad"
        assert ret == (0 if valid else 101), (tag, ret, slot)
        typed = [json.loads(l) for l in (slot / "stdout").read_bytes().splitlines()]
        assert typed[-1] == {"reason": "build-finished", "success": valid}
        full = []
        cached = 0
        links = 0
        for log in slot.glob("exec.*"):
            for ex, args, _ in reassemble(log.read_text()):
                p = Path(ex)
                p = p if p.is_absolute() else clone / p
                if not p.is_file():
                    continue
                if p.samefile(rustc):
                    if "link-only" in args or any(
                        x.startswith("-Zlink-only") for x in args
                    ):
                        cached += 1
                    elif "--crate-name" in args and "--out-dir" in args:
                        full.append(args[args.index("--crate-name") + 1])
                elif p.samefile(wild):
                    links += 1
        units = [r for r in typed if r["reason"] == "compiler-artifact"]
        row = {
            "full": len(full),
            "link_only": cached,
            "wild": links,
            "crates": dict(sorted(Counter(full).items())),
            "typed": len(units),
            "fresh": sum(u["fresh"] for u in units),
        }
        if not valid:
            errors = [
                r["message"]["code"]["code"]
                for r in typed
                if r["reason"] == "compiler-message"
                and r["message"]["level"] == "error"
                and r["message"].get("code")
            ]
            assert errors == ["E0425"]
            row["errors"] = errors
        elif kind == "test":
            (u,) = [
                u for u in units if u["target"]["name"] == "ruff_db" and u["executable"]
            ]
            exe = Path(u["executable"])
            inventory = run_program([exe, "--list", "--format", "terse"], 0)
            names = sorted(
                l[:-6] for l in inventory.decode().splitlines() if l.endswith(": test")
            )
            assert len(names) > 50 and set(CASES) <= set(names)
            for i, test in enumerate(CASES):
                fails = version == "old" and i == 0
                stdout = run_program(
                    [exe, "--exact", test, "--test-threads=1"], 101 if fails else 0
                )
                assert (
                    "test " + test + " ... " + ("FAILED" if fails else "ok")
                ).encode() in stdout
            row.update(
                elf=sha(exe),
                inventory=hashlib.sha256("\n".join(names).encode()).hexdigest(),
                tests=len(names),
            )
        else:
            (u,) = [u for u in units if u["target"]["name"] == "ruff_db"]
            (lib,) = [p for p in u["filenames"] if p.endswith(".rlib")]
            dirs = {Path(f).parent for u in units for f in u["filenames"]}
            for base in (target, shared):
                dirs.update(
                    p.parent for pat in ("*.rlib", "*.so") for p in base.rglob(pat)
                )
            exe = work / "reader"
            extra = [
                item for d in sorted(dirs) for item in ("-L", "dependency=" + str(d))
            ]
            run_program(
                [
                    "rustc",
                    "+ohm",
                    "--edition=2024",
                    work / "reader.rs",
                    "--extern",
                    "ruff_db=" + lib,
                    *extra,
                    "-o",
                    exe,
                ],
                0,
            )
            answer = run_program([exe], 0).decode().strip()
            assert answer == {"old": "Other", "new": "DirectoryNotEmpty"}[version]
            row.update(elf=sha(exe), verdict=answer)
        if valid:
            fingerprint = {
                k: row[k] for k in ("elf", "inventory", "tests", "verdict") if k in row
            }
            assert products.setdefault((version, kind), fingerprint) == fingerprint, (
                tag,
                fingerprint,
            )
        results[tag] = row
        print(
            tag,
            row["full"],
            row["link_only"],
            row["wild"],
            row.get("verdict", row.get("errors", "")),
            flush=True,
        )

    for phase, version, data in (
        ("original", "old", old),
        ("edited", "new", original),
        ("invalid", "bad", bad),
        ("repaired", "new", original),
        ("reverted", "old", old),
        ("independent-new", "new", original),
    ):
        if phase == "independent-new":
            for p in (target, shared):
                p.rename(work / ("retained-" + p.name))
                p.mkdir()
        (clone / SOURCE).write_bytes(data)
        for kind in ("build", "test"):
            tag = phase + "-" + kind
            run(tag, kind, version)
            if phase in ("original", "edited"):
                for i in (1, 2):
                    run(tag + "-unchanged-" + str(i), kind, version)
    assert all(
        products["old", k]["elf"] != products["new", k]["elf"]
        for k in ("build", "test")
    )
    with (work / "result.json").open("x") as f:
        json.dump(
            {"tools": identities, "ruff": RUFF, "edit": EDIT, "phases": results},
            f,
            indent=2,
        )
        f.write("\n")


if __name__ == "__main__":
    main()
