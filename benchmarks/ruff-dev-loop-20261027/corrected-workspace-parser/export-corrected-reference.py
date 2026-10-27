"""Export completed clean and warm ELF, diagnostic and CLI receipts for the corrected compiler."""
import json
from pathlib import Path
import sys
import tarfile
import time

root = Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
name = 'revision-native-66815c41574c'
reference = root/(name+'-elf-reference')
while True:
    try:
        summary = json.loads((reference/'statistics.json').read_bytes())
        assert set(summary) == {'build','test'}
        break
    except (OSError, ValueError):
        assert not (root/(name+'-logs')/'launch.rc').is_file(), 'benchmark script ended without a valid reference'
        time.sleep(10)
assert json.loads((reference/'complete.json').read_bytes())['source_clean']
phases = [f'{arm}-{cache}-{mode}-edited' for arm in ('parent','candidate') for cache in ('warm','cold') for mode in ('build','test')]
phases += [f'candidate-warm-{mode}-original' for mode in ('build','test')]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
    files = [reference/'complete.json',reference/'statistics.json']
    for phase in phases:
        files.append(reference/(phase+'.json'))
        log=reference/(phase+'.stderr')
        if log.is_file(): files.append(log)
    for path in files:
        assert path.is_file() and not path.is_symlink() and path.stat().st_size < 5_000_000
        tar.add(path,arcname=path.name,recursive=False)
