"""Complete byte/mode/mtime and internal hard-link topology, without copying aliases."""
from pathlib import Path
import os
import stat
from common import sha


def inventory(root):
    root = Path(root)
    rows = []
    cache = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        row = {'path': '.' if path == root else str(path.relative_to(root)),
               'mode': stat.S_IMODE(info.st_mode), 'mtime_ns': info.st_mtime_ns}
        if stat.S_ISDIR(info.st_mode):
            row['kind'] = 'directory'
        elif stat.S_ISREG(info.st_mode):
            key = (info.st_dev, info.st_ino)
            if key not in cache:
                cache[key] = (row['path'], sha(path))
            group, digest = cache[key]
            row.update(kind='file', bytes=info.st_size, sha256=digest, hardlink_group=group)
        else:
            raise AssertionError('unexpected nonregular bank entry: ' + row['path'])
        rows.append(row)
    return rows


def inode_set(root):
    return {(s.st_dev, s.st_ino) for p in Path(root).rglob('*') if stat.S_ISREG((s := p.lstat()).st_mode)}


def total_bytes(rows):
    return sum(row.get('bytes', 0) for row in rows)
