"""Stream an exact, compressed archive of the successful edit qualification traces for one arm."""
import argparse
from pathlib import Path
import json
import re
import sys
import tarfile

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('directory', type=Path)
cli.add_argument('arm', choices=['parent', 'candidate'])
args = cli.parse_args()
cohort = args.directory
assert re.fullmatch(r'results-revision-native-[0-9a-f]{12}-(?:build|test)', cohort.name)
assert json.loads((cohort/'complete.json').read_bytes())['source_clean']
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
    for name in ['plan.json', 'complete.json']:
        archive.add(cohort/name, arcname=f'{cohort.name}/{name}', recursive=False)
    for phase in ['verify-edit', 'verify-final-edit']:
        trace = cohort/(args.arm+'-'+phase)
        files = [trace/n for n in ['stdout', 'stderr', 'receipt.json']]
        files.extend(f for f in sorted(trace.glob('exec.*')) if re.fullmatch(r'exec\.\d+', f.name) and f.stat().st_size)
        assert len(files) > 3
        for f in files:
            assert f.is_file() and not f.is_symlink() and f.stat().st_size < 16_000_000
            archive.add(f, arcname=f'{cohort.name}/{trace.name}/{f.name}', recursive=False)
