"""Read a completed, already scored H2 result and its minimum per-process verification inputs."""
import gzip
import hashlib
import io
from pathlib import Path
import sys
import tarfile

base = Path.home() / '.cache/ohm-233-position-qualified-20261027'
raw = base / 'whole-ruff-observer-prefetch-fifo-v2'
assert (base / 'prefetch-fifo-qualified-v2/queue.rc').read_text().strip() == '0'
assert (raw / 'public/statistics.json').is_file() and not (raw / 'failure.txt').exists()
allowed = ['complete.json', 'anchors-complete.json', 'subjects.json', 'measured.json', 'training-limit.json',
           'prior-unscored-*.json', 'training-?.json', 'public/*',
           'anchor-*/anchor.json', 'final-*/anchor.json', 'prepare-*/receipt.json',
           'timed-*/receipt.json', 'timed-*/invocation.json', 'audit-*/receipt.json', 'audit-*/exec.*']
files = sorted({p for pattern in allowed for p in raw.glob(pattern) if p.is_file()})
assert sum(p.parent.name.startswith('timed-') and p.name == 'receipt.json' for p in files) == 64
assert sum(p.parent.name.startswith('audit-') and p.name == 'receipt.json' for p in files) == 64
assert sum(p.parent.name.startswith('audit-') and p.name.startswith('exec.') for p in files) >= 64
manifest = []
with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', compresslevel=3, mtime=0) as gz:
    with tarfile.open(fileobj=gz, mode='w|') as ar:
        def add(name, data):
            spec = tarfile.TarInfo(name)
            spec.size = len(data)
            spec.mode = 0o600
            ar.addfile(spec, io.BytesIO(data))

        for path in files:
            name = str(path.relative_to(raw))
            data = path.read_bytes()
            manifest.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
            add(name, data)
        add('TRANSFER_SHA256SUMS', ''.join(manifest).encode())
