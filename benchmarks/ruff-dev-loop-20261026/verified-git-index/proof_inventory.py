"""Record the exact private Ohm proof inventory outside the counted Cargo process."""

import hashlib
import json
from pathlib import Path


def proof_inventory(cargo_home, include_git):
    directories = [".ohm-registry-json-v1"]
    if include_git:
        directories.append(".ohm-git-index-sha1dc-v1")
    inventory = {}
    for name in directories:
        directory = Path(cargo_home).resolve() / name
        assert directory.is_dir(), directory
        items = []
        for entry in sorted(directory.iterdir()):
            info = entry.lstat()
            assert entry.is_file() and not entry.is_symlink(), entry
            items.append(
                (
                    entry.name,
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                    hashlib.sha256(entry.read_bytes()).hexdigest(),
                )
            )
        inventory[name] = dict(
            count=len(items),
            ino=directory.stat().st_ino,
            sha256=hashlib.sha256(
                json.dumps(items, separators=(",", ":")).encode()
            ).hexdigest(),
        )
    return inventory


def record_inventory(manifest, expected, cargo_home, include_git, stage):
    actual = proof_inventory(cargo_home, include_git)
    with manifest.open("a") as log:
        log.write(
            json.dumps(dict(stage=stage, inventory=actual), sort_keys=True) + "\n"
        )
    assert expected is None or actual == expected, (
        "private proof inventory changed",
        stage,
        expected,
        actual,
    )
    return actual
