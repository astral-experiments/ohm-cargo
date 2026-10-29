"""Cross-check the actual terminated stock commands, native callers and archive geometry."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
data = json.loads((root / 'stock.json').read_bytes())
phases = data['phases']
order = ['original', 'edit', 'edit-repeat', 'independent-empty-edited', 'restore', 'restore-repeat']
assert set(phases) == set(order)
expected_dirty = set('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
def field(name, key):
    return phases[name]['consumer'][key]
for name, fresh in zip(order, [248, 238, 248, 0, 238, 248], strict=True):
    row = phases[name]
    stats, caller = row['summary'], row['consumer']
    assert stats['units'] == 248 and stats['fresh'] == fresh and len(row['dirty_units']) == 248 - fresh
    assert stats['root_fresh'] == (fresh == 248)
    assert caller['linter'] == stats['archive'] and caller['executable'] == stats['consumer_exe']
    expected = '1 SIM222\n' if name in ('original', 'restore', 'restore-repeat') else '2 SIM222\n3 SIM222\n4 SIM222\n'
    assert caller['exit'] == 0 and caller['stdout'] == stats['consumer_output'] == expected
    assert caller['input'] == 'e981376810375b7214c83ccd0dd840cd0110c7ce31d90cffc45ae1bd9706c4c2'
    assert caller['stderr_sha256'] == hashlib.sha256(b'').hexdigest()
    for value in [caller['linter'], caller['executable'], caller['ast'], *row['raw_digests'].values()]:
        assert len(value) == 64 and len(bytes.fromhex(value)) == 32
    if fresh == 238:
        assert {v[0] for v in row['dirty_units']} == expected_dirty and all(v[1] == ['lib'] for v in row['dirty_units'])
for n in ('reader.rs', 'cli_input.py'):
    assert hashlib.sha256((root / n).read_bytes()).hexdigest() == data['script_hashes'][n]
assert data['seed']['hash'] == field('original', 'linter')
assert data['seed']['full_units'] == 248 and data['seed']['fresh'] == 0
for name, repeat in [('edit', 'edit-repeat'), ('restore', 'restore-repeat')]:
    assert phases[name]['consumer'] == phases[repeat]['consumer']
assert field('restore', 'executable') == field('original', 'executable') != field('edit', 'executable')
assert field('edit', 'executable') != field('independent-empty-edited', 'executable')
q = data['qualification']
assert not q['restored_original_raw'] and not q['warm_and_empty_archive_equal']
for k, name in [('original_archive', 'original'), ('edited_warm_archive', 'edit'), ('restored_archive', 'restore'), ('independent_empty_archive', 'independent-empty-edited')]:
    assert q[k] == field(name, 'linter')
assert len({field(n, 'linter') for n in [order[i] for i in [0, 1, 3, 4]]}) == 4
g = data['geometry']
assert g['old_objects'] == g['new_objects'] == g['native_same_range'] == 256
assert 77383632 == g['native_same_bytes'] < g['matched_chunks_bytes'] == 101067528 < g['old_size'] == g['new_size'] == 101853960
print('Six actual Cargo builds and linked consumer verdicts verified, with 256 equal-offset native objects.')
