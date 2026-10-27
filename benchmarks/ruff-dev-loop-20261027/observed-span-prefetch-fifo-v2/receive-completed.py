"""Compare the destination replay of all paired timings and actual execs with the H2 output."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tarfile

h = Path(__file__).resolve().parent
out = Path(sys.argv[1]).resolve()
out.mkdir(mode=0o700)
archive = out / 'source-receipts.tar.gz'
with (h / 'collect-completed.py').open('rb') as script, archive.open('xb') as f:
    subprocess.run(['dbox', 'ssh', 'charlie-ohm-relink-b-1024', '--no-tmux', '--',
                    'taskset', '-c', '24-31', 'python3', '-B', '-'], stdin=script, stdout=f, check=True)
raw = out / 'source-receipts'
raw.mkdir(mode=0o700)
with tarfile.open(archive, 'r:gz') as t:
    for member in t:
        file = Path(member.name)
        assert member.isfile() and not file.is_absolute() and '..' not in file.parts
        assert member.size <= 100 * 2**20
        target = raw / file
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f:
            f.write(t.extractfile(member).read())
manifest = (raw / 'TRANSFER_SHA256SUMS').read_text().splitlines()
assert len(manifest) == sum(p.is_file() for p in raw.rglob('*')) - 1
for line in manifest:
    digest, n = line.split('  ', 1)
    assert hashlib.sha256((raw / n).read_bytes()).hexdigest() == digest
replay = out / 'destination-replay'
subprocess.run([sys.executable, '-B', str(h / 'analyze.py'), '--raw', str(raw), '--public', str(replay)], check=True)
remote = raw / 'public'
assert [p.name for p in sorted(replay.iterdir())] == [p.name for p in sorted(remote.iterdir())]
for p in replay.iterdir():
    assert p.read_bytes() == (remote / p.name).read_bytes(), p
print('Matched', len(manifest), 'source receipts and', len(list(replay.iterdir())), 'destination-recomputed files.')
