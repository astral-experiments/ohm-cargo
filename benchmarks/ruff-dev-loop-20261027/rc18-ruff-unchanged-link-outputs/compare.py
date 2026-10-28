"""Compare each physical link with the previous ELF at the same target path."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

archive = Path(sys.argv[1])
with archive.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == 'ee336c50bac854f16648f19f870d5dbe915892f9fd5c9cedb08e50ab14e2779d'
with tarfile.open(archive, 'r:xz') as bundle:
    phases = {name: json.load(bundle.extractfile(f'test/{name}/retained-links.json'))
              for name in ('cold', 'unchanged', 'edited', 'restored', 'final-unchanged')}
    for name in ('unchanged', 'final-unchanged'):
        processes = json.load(bundle.extractfile(f'test/{name}/actual-processes.json'))['processes']
        assert [p['unit_or_output'] for p in processes if p['kind'] == 'full'] == ['ron']
        assert len([p for p in processes if p['kind'] == 'link-only']) == 50
        assert {r['pid'] for r in phases[name]['wild']} == {p['pid'] for p in processes if p['kind'] == 'wild'}

pairs = []
for before, after in [('cold', 'unchanged'), ('restored', 'final-unchanged')]:
    previous = phases[before]['elf']
    current = phases[after]
    matched = {}
    assert len(current['wild']) == 50
    for row in current['wild']:
        target = row['output']
        assert row['retained'] and target not in matched
        assert current['elf'][target] == {k: row[k] for k in ('sha256', 'size')}
        matched[target] = previous[target] == current['elf'][target]
    pairs.append(matched)

assert pairs[0].keys() == pairs[1].keys()
names = list(phases)
rows = []
for path in sorted(pairs[0]):
    parts = Path(path).parts
    assert parts[-2] == 'out'
    rows.append({'package': parts[-4], 'file': parts[-1],
                 'unchanged_matches': [pair[path] for pair in pairs],
                 'elfs': {n: phases[n]['elf'][path] for n in names}})
stable = [r for r in rows if all(r['unchanged_matches'])]
largest = max(stable, key=lambda r: r['elfs']['final-unchanged']['size'])
assert (largest['package'], largest['file']) == ('ty_server','e2e-27d34c779ecc8418')
e = largest['elfs']
assert e['cold'] == e['unchanged'] == e['restored'] == e['final-unchanged'] and e['edited'] != e['cold']
result = {'equal_after_cold':sum(pairs[0].values()), 'equal_after_restore':sum(pairs[1].values()),
          'equal_in_both':len(stable), 'equal_in_both_bytes':sum(r['elfs']['final-unchanged']['size'] for r in stable),
          'largest_equal_target': largest['file'], 'targets': rows}
assert (result['equal_after_cold'],result['equal_after_restore'],result['equal_in_both']) == (49,48,47)
print(json.dumps(result, indent=2))
