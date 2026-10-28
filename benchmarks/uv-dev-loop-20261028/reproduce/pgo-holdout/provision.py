#!/usr/bin/env python3
"""Provision a pinned llvm-profdata and exact release-training sources into a new scratch directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1, sha256
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

CARGO_PERF = "0a054b0ead56e41a4584bfab6fdc1a5fad2aedc3"
CASES = {
    "bitmaps-3.2.1": "fffc6646daa4b2ba80ae2ebcf91d1e67716f2a39",
    "diesel-2.2.10": "df8341fa205001163fa3e51b1c412f88a850f3e7",
}
LLVM_URL = "https://static.rust-lang.org/dist/2026-10-15/llvm-tools-1.99.1-x86_64-unknown-linux-gnu.tar.xz"
LLVM_SHA256 = "8429c5117debfb45c22cf2f97712ef00e0e94976c96cf92f661974a458ca7e84"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path)
parser.add_argument(
    "--oss-repo",
    required=True,
    type=Path,
    help="existing OSS checkout for gh-auto identity routing",
)
parser.add_argument(
    "--perf-repo",
    type=Path,
    help="optional existing Git object store containing the pinned rustc-perf revision",
)
parser.add_argument(
    "--llvm-profdata", type=Path, help="optional existing LLVM 23.1.1 binary"
)
parser.add_argument(
    "--stable-lib",
    type=Path,
    default=Path.home() / ".rustup/toolchains/stable-x86_64-unknown-linux-gnu/lib",
)
args = parser.parse_args()
out = args.destination.resolve()
out.mkdir(parents=True, exist_ok=False)
if args.llvm_profdata:
    llvm = args.llvm_profdata.resolve()
else:
    archive = out / "llvm-tools.tar.xz"
    with urllib.request.urlopen(LLVM_URL) as response, archive.open("wb") as dest:
        shutil.copyfileobj(response, dest)
    assert sha256(archive.read_bytes()).hexdigest() == LLVM_SHA256
    # Install the binary alone in scratch. The installed matching 1.99.1
    # toolchain supplies libLLVM if this executable has a dynamic dependency.
    with tarfile.open(archive) as tar:
        entries = [
            m for m in tar if m.isfile() and m.name.endswith("/bin/llvm-profdata")
        ]
        assert len(entries) == 1
        llvm = out / "llvm-profdata-bin"
        llvm.write_bytes(tar.extractfile(entries[0]).read())
        llvm.chmod(0o755)
wrapper = out / "llvm-profdata"
import shlex

wrapper.write_text(
    "#!/bin/sh\nLD_LIBRARY_PATH="
    + shlex.quote(str(args.stable_lib.resolve()))
    + " exec "
    + shlex.quote(str(llvm))
    + ' "$@"\n'
)
wrapper.chmod(0o755)
version = subprocess.check_output([wrapper, "--version"], text=True)
assert "23.1.1" in version, version
(out / "llvm-version.txt").write_text(version)
gh = "/home/dev-user/.local/bin/gh-auto"
for case, tree in CASES.items():
    directory = out / "corpus" / case
    directory.mkdir(parents=True)
    if args.perf_repo:
        source = args.perf_repo.resolve()
        obj = CARGO_PERF + ":collector/compile-benchmarks/" + case
        assert (
            subprocess.check_output(
                ["git", "-C", source, "rev-parse", obj], text=True
            ).strip()
            == tree
        )
        import io

        with tarfile.open(
            fileobj=io.BytesIO(
                subprocess.check_output(["git", "-C", source, "archive", obj])
            )
        ) as tar:
            tar.extractall(directory, filter="data")
    else:
        endpoint = "repos/rust-lang/rustc-perf/git/trees/" + tree + "?recursive=1"
        result = json.loads(
            subprocess.check_output([gh, "api", endpoint], cwd=args.oss_repo.resolve())
        )
        assert result["sha"] == tree and not result["truncated"]
        blobs = [b for b in result["tree"] if b["type"] == "blob"]
        assert blobs and all(b["mode"] in {"100644", "100755"} for b in blobs)

        def fetch_blob(blob):
            from urllib.parse import quote

            relative = Path(blob["path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            url = (
                "https://raw.githubusercontent.com/rust-lang/rustc-perf/"
                + CARGO_PERF
                + "/collector/compile-benchmarks/"
                + case
                + "/"
                + quote(relative.as_posix())
            )
            import time

            for retry in range(3):
                try:
                    with urllib.request.urlopen(url, timeout=45) as response:
                        data = response.read()
                    break
                except OSError:
                    if retry == 2:
                        raise
                    time.sleep(1 + retry)
            assert (
                len(data) == blob["size"]
                and sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                == blob["sha"]
            ), relative
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755 if blob["mode"] == "100755" else 0o644)

        with ThreadPoolExecutor(8) as pool:
            list(pool.map(fetch_blob, blobs))
metadata = {
    "rustc_perf_commit": CARGO_PERF,
    "training_trees": CASES,
    "llvm_tools": LLVM_URL,
    "llvm_tools_archive_sha256": LLVM_SHA256,
    "llvm_version": version,
}
(out / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(out)
