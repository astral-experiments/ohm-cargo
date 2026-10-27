"""Check the shipped release, byte-for-byte bridge archives, native output and diagnostics."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parent
subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=root, check=True)
for group in ('positions', 'hygiene'):
    directory = root / group
    subprocess.run([sys.executable, '-B', str(directory / 'verify.py')], cwd=directory, check=True)
    native = json.loads((directory / 'native-digests.json').read_bytes())
    archives = {k:v for k,v in native.items() if v['kind'] == 'archive'}
    assert len(archives) == (6 if group == 'positions' else 8)
    for name, row in archives.items():
        data = (directory / 'evidence' / name).read_bytes()
        assert data.startswith(b'!<arch>\n') and row['size'] == len(data)
        assert row['sha256'] == hashlib.sha256(data).hexdigest()
