"""Run the frozen cohorts as audited intermediate Cargo executables become available."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys


here = Path(__file__).resolve().parent
work = here.parent
stages = json.loads((here / 'registration.json').read_text())['stages']
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('--start', choices=[s['name'] for s in stages], default='unit')
args = cli.parse_args()
with (work / 'release-like/published-identities.tsv').open() as stream:
    revisions = {r['variant']: r['head'] for r in csv.DictReader(stream, delimiter='\t')}
for stage in stages[[r['name'] for r in stages].index(args.start):]:
    name = stage['name']
    if name != 'std':
        subprocess.run([sys.executable, '-B', work / 'pgo-holdout/wait-for-stage.py', name, 'ready'],
                       cwd=work.parent, check=True)
        manifest = json.loads((work / 'pgo-intermediates/records' / name / 'ready.json').read_text())
        binary = work / 'pgo-intermediates/bin' / name
        with binary.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == manifest['cargo_sha256']
        assert manifest['cargo_commit'] == revisions[name] and manifest['pull_request'] == stage['pr']
        assert manifest['raw_files'] == manifest['training_commands_verified'] == 24
        assert manifest['frozen_training_files_verified'] == 270
    print(f'Starting {name}', flush=True)
    subprocess.run([sys.executable, '-B', here / 'measure.py', name], cwd=work.parent, check=True)
