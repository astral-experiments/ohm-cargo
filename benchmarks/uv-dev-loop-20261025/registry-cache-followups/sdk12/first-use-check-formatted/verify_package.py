"""Authenticate this portable packet, then replay counts and direct edges."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'PACKAGE-MANIFEST.json').read_bytes())
expected = set(manifest['files']) | {'PACKAGE-MANIFEST.json'}
actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
assert actual == expected
for name, row in manifest['files'].items():
    relative = PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root / name
    assert path.is_file() and not path.is_symlink()
    content = path.read_bytes()
    assert len(content) == row['bytes']
    assert hashlib.sha256(content).hexdigest() == row['sha256']
    assert hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() == row['git_blob']
for reader in ('reproduce.py', 'replay_parse_edges.py', 'replay_cache_controls.py'):
    subprocess.run([sys.executable, '-I', '-B', str(root / reader)], check=True)
print(json.dumps({'state': 'complete-portable-replay-passed', 'files': len(expected)}))
