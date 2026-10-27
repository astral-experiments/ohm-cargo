"""Keep completed timing copies on scratch between endpoints and verify their full contents."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import stat
import subprocess


def tree(path):
    """Commit paths, file metadata, symlinks, hard-link groups, and regular-file contents."""
    aggregate = hashlib.sha256()
    root = path.stat()
    aggregate.update(json.dumps(['.', root.st_mode, root.st_uid, root.st_gid, root.st_mtime_ns,
        [[a, os.getxattr(path, a).hex()] for a in sorted(os.listxattr(path))]]).encode() + b'\n')
    inodes = {}
    files = entries = size = 0
    for base, directories, names in os.walk(path):
        directories.sort()
        for name in sorted(directories + names):
            p = Path(base) / name
            rel = p.relative_to(path).as_posix()
            s = p.lstat()
            row = [rel, s.st_mode, s.st_uid, s.st_gid, s.st_mtime_ns]
            if stat.S_ISREG(s.st_mode):
                key = (s.st_dev, s.st_ino)
                if key not in inodes:
                    with p.open('rb') as f:
                        inodes[key] = (rel, hashlib.file_digest(f, 'sha256').hexdigest())
                    size += s.st_size
                row.extend((s.st_size, *inodes[key]))
                files += 1
            elif stat.S_ISLNK(s.st_mode):
                row.append(os.readlink(p))
            else:
                assert stat.S_ISDIR(s.st_mode), p
            xattrs = [[a, os.getxattr(p, a, follow_symlinks=False).hex()]
                      for a in sorted(os.listxattr(p, follow_symlinks=False))]
            row.append(xattrs)
            aggregate.update(json.dumps(row, separators=(',', ':')).encode() + b'\n')
            entries += 1
    return dict(sha256=aggregate.hexdigest(), entries=entries, files=files, bytes=size)


def retain_completed_build(out, dest, gate_free):
    state = out / 'state' / 'build'
    saved = out / 'state' / 'verified-original-build-copies'
    assert not state.is_symlink() and not saved.exists() and not dest.exists()
    assert sorted(p.name for p in state.iterdir()) == ['B', 'C']
    assert state.stat().st_dev != dest.parent.stat().st_dev
    size = int(subprocess.check_output(['du', '-s', '-B1', state]).split()[0])
    gate_free(dest.parent, int(1.15 * size))
    subprocess.run(['cp', '-a', '--reflink=auto', '--', state, dest], check=True)
    original = tree(state)
    assert tree(dest) == original and original['files'] > 1000
    state.rename(saved)
    try:
        state.symlink_to(dest, target_is_directory=True)
    except OSError:
        saved.rename(state)
        raise
    assert state.resolve() == dest and not saved.is_symlink()
    # Only these newly created scored copies are retired. Their verified twins remain addressable.
    shutil.rmtree(saved)
    gate_free(out)
    return dict(destination=str(dest), contents=original, allocation=size,
                free_source=shutil.disk_usage(out).free,
                free_retention=shutil.disk_usage(dest.parent).free)
