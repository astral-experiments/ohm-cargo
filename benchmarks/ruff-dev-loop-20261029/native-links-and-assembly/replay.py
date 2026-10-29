"""Count compiles and native links for one installation using an existing Ohm toolchain."""

import argparse
import ast
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess


RUFF = "93526150df078af7dd8fc4226cdcc469539d2001"
CHANGES = {
    "build": (
        "ef23c9c39eb3029bab0139c3ea7ae6d95c4131e0",
        "crates/ruff_python_ast/src/python_version.rs",
    ),
    "test": (
        "dc2f0a86fd9c4f256a6809370e29bfe2631ebd8d",
        "crates/ruff_python_ast/src/token/tokens.rs",
    ),
}


def git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", repo, *args])


def source_states(repo, mode):
    commit, path = CHANGES[mode]
    new = git(repo, "show", f"{RUFF}:{path}")
    if mode == "build":
        assert new == git(repo, "show", f"{commit}:{path}")
        return path, git(repo, "show", f"{commit}^:{path}"), new
    # Restore only the two production hunks. Keep all tests present in the checkout.
    patch = git(repo, "diff", "-U0", commit + "^", commit, "--", path).splitlines(
        keepends=True
    )
    hunks = [i for i, line in enumerate(patch) if line.startswith(b"@@")]
    assert len(hunks) == 6
    old = new
    for first, last in zip(hunks[:2], hunks[1:3]):
        lines = patch[first + 1 : last]
        added = b"".join(line[1:] for line in lines if line.startswith(b"+"))
        removed = b"".join(line[1:] for line in lines if line.startswith(b"-"))
        assert old.count(added) == 1
        old = old.replace(added, removed)
    return path, old, new


def native(trace, compiler, linker):
    full = []
    links = Counter()
    pattern = re.compile(
        r'^execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-f]+ /\* [^*]* \*/|NULL)\)\s+= 0$'
    )
    for log in trace.glob("exec.*"):
        for line in log.read_text().splitlines():
            if not line.startswith("execve(") or not line.endswith(" = 0"):
                continue
            result = pattern.fullmatch(line)
            if not result:
                raise RuntimeError(f"Incomplete execve record in {log}")
            program, argv = Path(ast.literal_eval(result[1])), ast.literal_eval(
                result[2]
            )
            if not program.is_file():
                continue
            if program.samefile(compiler):
                if "--crate-name" in argv and "--out-dir" in argv:
                    full.append(argv[argv.index("--crate-name") + 1])
                elif any(
                    a == "-Zlink-only"
                    or (a == "-Z" and argv[i + 1 : i + 2] == ["link-only"])
                    for i, a in enumerate(argv)
                ):
                    links["rustc_link_only"] += 1
            if program.samefile(linker):
                links["wild"] += 1
    return {
        "full_rustc": sorted(full),
        "link_only_rustc": links["rustc_link_only"],
        "wild": links["wild"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ruff",
        required=True,
        type=Path,
        help="clean Ruff git checkout at the registered commit",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="new, empty output path for this installation",
    )
    parser.add_argument(
        "--toolchain",
        default="ohm",
        help="rustup-linked SDK using the intended Cargo and rustc",
    )
    parser.add_argument("--mode", required=True, choices=CHANGES)
    args = parser.parse_args()
    repo, out = args.ruff.resolve(), args.out.resolve()
    if git(repo, "rev-parse", "HEAD").decode().strip() != RUFF or git(
        repo, "status", "--porcelain", "--untracked-files=no"
    ):
        parser.error(
            "Ruff must match the exact registered commit and have no tracked edits"
        )
    if out.exists() or out.is_relative_to(repo):
        parser.error("choose a new output directory outside the Ruff checkout")
    out.mkdir(parents=True)
    workspace = out / "ruff"
    # Give the worktree command an empty source target so the measured target starts cold.
    setup = os.environ | {
        "CARGO_TARGET_DIR": str(out / "setup-source-target"),
        "CARGO_BUILD_BUILD_DIR": str(out / "setup-shared"),
        "CARGO_NET_OFFLINE": "true",
    }
    subprocess.run(
        [
            "cargo",
            "+" + args.toolchain,
            "worktree",
            "add",
            "--offline",
            "--detach",
            "--target-dir",
            str(out / "setup-target"),
            str(workspace),
            RUFF,
        ],
        cwd=repo,
        env=setup,
        check=True,
    )
    rel, old, new = source_states(repo, args.mode)
    path = workspace / rel
    assert path.read_bytes() == new and old != new
    env = os.environ | {
        "CARGO_TARGET_DIR": str(out / "target"),
        "CARGO_BUILD_BUILD_DIR": str(out / "shared"),
        "CARGO_NET_OFFLINE": "true",
        "CARGO_CACHE_AUTO_CLEAN_FREQUENCY": "never",
        "CARGO_TERM_COLOR": "never",
    }
    for name in (
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "RUSTC",
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
    ):
        if env.get(name):
            parser.error(f"clear {name} before reproducing the measured configuration")
    sdk = Path(
        subprocess.check_output(
            ["rustc", "+" + args.toolchain, "--print", "sysroot"], env=env, text=True
        ).strip()
    )
    compiler = sdk / "bin/rustc"
    linker = sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    assert compiler.is_file() and linker.is_file()
    version = subprocess.check_output(
        ["cargo", "+" + args.toolchain, "-Vv"], env=env, text=True
    )
    print(version, flush=True)
    flags = ["build"] if args.mode == "build" else ["test", "--lib", "--no-run"]
    for name, state in [
        ("old", old),
        ("old-repeat-1", None),
        ("old-repeat-2", None),
        ("edit", new),
        ("edit-repeat-1", None),
        ("edit-repeat-2", None),
        ("revert", old),
        ("revert-repeat-1", None),
        ("revert-repeat-2", None),
    ]:
        if state is not None:
            path.write_bytes(state)
        dest = out / name
        dest.mkdir()
        cmd = [
            "strace",
            "-ff",
            "-qq",
            "-s",
            "131072",
            "-e",
            "trace=execve",
            "-o",
            str(dest / "exec"),
            "cargo",
            "+" + args.toolchain,
            *flags,
            "--locked",
            "--offline",
            "-p",
            "ruff_python_ast",
            "-j4",
            "--message-format=json",
        ]
        with (dest / "cargo.jsonl").open("xb") as stdout, (dest / "cargo.stderr").open(
            "xb"
        ) as stderr:
            subprocess.run(
                cmd, cwd=workspace, env=env, stdout=stdout, stderr=stderr, check=True
            )
        rows = [
            json.loads(line)
            for line in (dest / "cargo.jsonl").read_bytes().splitlines()
        ]
        assert rows[-1] == {"reason": "build-finished", "success": True}
        result = native(dest, compiler, linker)
        if name in ("edit", "revert"):
            assert "ruff_python_ast" in result["full_rustc"]
        (dest / "native.json").write_text(json.dumps(result, indent=2) + "\n")
        print(name, json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
