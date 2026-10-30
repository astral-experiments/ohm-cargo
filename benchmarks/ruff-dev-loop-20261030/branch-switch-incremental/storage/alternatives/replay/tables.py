"""Losslessly pack the two private Ruff compiler tables after a second checkout is seen."""
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

root = Path(os.environ["OHM_REPLAY_DIRECTORY"]).resolve()
assert root == Path(__file__).resolve().parent and (root / ".table-replay").is_file()
label, crate, compiler, *args = sys.argv[1:]
assert crate in {"ruff_python_ast", "ruff_python_parser"} and len(label) == 16
incremental, = [Path(arg.removeprefix("-C").removeprefix("incremental=")).resolve()
                for arg in args if arg.removeprefix("-C").startswith("incremental=")]
assert any(incremental.is_relative_to(root / folder) for folder in ("target", "build"))
manifest_name = ".ohm-table-replay.json"
zstd = os.environ["OHM_REPLAY_ZSTD"]

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def sessions():
    found = []
    for bucket in incremental.glob(crate + "-*"):
        assert bucket.is_dir() and not bucket.is_symlink()
        for folder in bucket.glob("s-*"):
            if folder.is_dir() and not folder.is_symlink() and not folder.name.endswith("-working"):
                _, timestamp, key, _ = folder.name.split("-")
                if key.startswith("_"):
                    found.append((int(timestamp, 36), key.split("_")[1], folder))
    return found

def restore(folder):
    manifest = folder / manifest_name
    if not manifest.exists():
        return 0
    tables = json.loads(manifest.read_bytes())
    for table in tables:
        names = table["names"]
        assert all(Path(n).name == n for n in [*names, table["archive"]])
        first, archive = folder / names[0], folder / table["archive"]
        with first.open("xb") as out:
            subprocess.run([zstd, "-dq", "--single-thread", "-c", "--", archive], stdout=out, check=True)
        assert first.stat().st_size == table["size"] and digest(first) == table["sha256"]
        first.chmod(table["mode"])
        os.utime(first, ns=(table["mtime_ns"],) * 2)
        for alias in names[1:]:
            os.link(first, folder / alias)
        archive.unlink()
    manifest.unlink()
    return len(tables)

def pack(folder):
    manifest = folder / manifest_name
    if manifest.exists():
        return 0
    inodes = defaultdict(list)
    for path in folder.iterdir():
        meta = path.lstat()
        if stat.S_ISREG(meta.st_mode):
            inodes[meta.st_dev, meta.st_ino].append(path)
    tables = []
    for paths in inodes.values():
        paths.sort()
        first = paths[0]
        meta = first.lstat()
        if meta.st_nlink != len(paths) or not any(p.name in {"dep-graph.bin", "query-cache.bin"} for p in paths):
            continue
        archive = folder / f".ohm-table-replay-{len(tables)}.zst"
        with archive.open("xb") as out:
            subprocess.run([zstd, "-q", "-1", "--single-thread", "-c", "--", first], stdout=out, check=True)
        if archive.stat().st_blocks >= meta.st_blocks:
            archive.unlink()
            continue
        tables.append({"archive": archive.name, "names": [p.name for p in paths], "sha256": digest(first),
                       "size": meta.st_size, "mode": stat.S_IMODE(meta.st_mode), "mtime_ns": meta.st_mtime_ns})
    if tables:
        manifest.write_text(json.dumps(tables, sort_keys=True))
        for table in tables:
            for name in table["names"]:
                (folder / name).unlink()
    return len(tables)

chosen = max(sessions(), key=lambda row: (row[1] == label, row[0]), default=None)
start = time.monotonic()
restored = restore(chosen[2]) if chosen else 0
prep = time.monotonic() - start
process = subprocess.run([compiler, *args], close_fds=False)
start = time.monotonic()
compressed = 0
current = sessions()
if process.returncode == 0 and len({checkout for _, checkout, _ in current}) > 1:
    assert len(current) == 2 and any(checkout == label for _, checkout, _ in current)
    compressed = sum(pack(folder) for _, _, folder in current)
logdir = root / "table-visits"
logdir.mkdir(exist_ok=True)
with (logdir / f"{os.getpid()}.json").open("x") as f:
    json.dump({"crate": crate, "phase": os.environ["OHM_REPLAY_PHASE"], "head": label,
               "chosen": chosen[1] if chosen else None, "restored": restored, "compressed": compressed,
               "restore_s": prep, "pack_s": time.monotonic() - start, "rustc_exit": process.returncode}, f)
sys.exit(process.returncode)
