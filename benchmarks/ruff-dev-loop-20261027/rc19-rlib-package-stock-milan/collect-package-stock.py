"""Project the six distributed-toolchain Cargo and consumer results on host two."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
study = root / 'package-stock-qa'
assert (study / 'exit').read_text() == '0\n'
names = ['original', 'edit', 'edit-repeat', 'independent-empty-edited', 'restore', 'restore-repeat']
def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def read(path):
    return json.loads(path.read_bytes())
result = {'seed': read(root / 'package-seedresume/seed.json'),
          'geometry': read(study / 'geometry.json'), 'qualification': read(study / 'qualify.json'),
          'script_hashes': {n: digest(root / n) for n in ['cli_input.py', 'reader.rs', 'h2-stock-qa.py', 'h2-stock-qa.sh']},
          'phases': {}}
for name in names:
    d = study / name
    rows = [json.loads(line) for line in (d / 'cargo.jsonl').read_bytes().splitlines()]
    jobs = [v for v in rows if v['reason'] == 'compiler-artifact']
    assert [v['success'] for v in rows if v['reason'] == 'build-finished'] == [True]
    root_job, = [v for v in jobs if v['target']['name'] == 'ruff_linter' and v['target']['kind'] == ['lib']]
    summary = read(d / 'summary.json')
    caller = read(d / 'consumer/result.json')
    assert len(jobs) == summary['units'] and sum(v['fresh'] for v in jobs) == summary['fresh']
    assert caller['linter'] == summary['archive'] and caller['executable'] == summary['consumer_exe']
    assert root_job['fresh'] == summary['root_fresh'] and caller['exit'] == 0
    result['phases'][name] = {'summary': summary, 'consumer': caller,
                             'dirty_units': sorted([v['target']['name'], v['target']['kind']] for v in jobs if not v['fresh']),
                             'raw_digests': {n: digest(d / n) for n in ['cargo.jsonl', 'cargo.err', 'consumer/result.json', 'consumer/compiler.stderr', 'summary.json']}}
print(json.dumps(result, sort_keys=True, indent=2))
