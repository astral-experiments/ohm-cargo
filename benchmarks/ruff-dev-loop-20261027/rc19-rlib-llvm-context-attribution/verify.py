"""Check the official driver, raw callback counts, and medians on the four Ruff archives."""
import ast
import hashlib
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parent
data = json.loads((root / 'observations.json').read_bytes())
assert data['empty_stderr'] and data['process_exit'] == '0'
assert data['official_archive'] == '629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8'
assert data['sdk']['driver'] == 'a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de'
assert data['sdk']['llvm'] == '43bac9749e539cd5988a4d5452b64582cf07ac9e7c059fde29c7bee76e106c51'
assert data['sdk']['callback_symbol'] == '00000000061c25c0'
for name in ('released-symbols.c', 'observe-context.c'):
    assert hashlib.sha256((root/'reproduce'/name).read_bytes()).hexdigest() == data['source_sha256'][name]
ast.parse((root/'reproduce/screen.py').read_bytes())
for crate, info in data['records'].items():
    observations = data['observations'][crate]
    for label in ('normal', 'observed'):
        rows = observations[label]
        assert len(rows) == 24
        costs = info['cost'][label]
        for row in rows:
            assert row[0:2] == [info['elf_members'], info['symbols']]
            assert 0 <= row[6] + row[7] < row[3]
            assert row[4:6] == ([row[0], row[0]] if label == 'observed' else [0,0])
        for col, name in [(3,'total_median_ns'), (6,'constructor_median_ns'), (7,'destructor_median_ns')]:
            assert statistics.median(r[col] for r in rows[2:]) == costs[name]
    print(crate, info['elf_members'], info['symbols'], info['complete_ordered_symbols'])
assert sum(x['elf_members'] for x in data['records'].values()) == 687
assert sum(x['symbols'] for x in data['records'].values()) == 81411
