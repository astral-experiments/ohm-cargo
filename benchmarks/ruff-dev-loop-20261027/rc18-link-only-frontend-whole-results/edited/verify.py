"""Verify every ordinary Cargo process and its subsequent notebook assertion in the edit study."""
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import sys

if not __debug__:
    raise SystemExit('Run without Python optimization.')
directory = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parent
samples = json.loads((directory / 'samples.json').read_bytes())
reported = json.loads((directory / 'summary.json').read_bytes())
order = 'AB BA BA AB BA BA AB AB BA AB AB BA'.split()
assert [row['order'] for row in samples] == order
assert Counter(order[::2]) == Counter(order[1::2]) == {'AB': 3, 'BA': 3}
expected_elf = {
    'notebook': 'd76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8',
    'original': 'be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7',
}
tests = {'notebook::hover_past_end_of_cell', 'notebook::inlay_hints_range_past_end_of_cell'}
for index, row in enumerate(samples):
    state = 'notebook' if index % 2 == 0 else 'original'
    assert row['state'] == state
    for arm in 'AB':
        for phase, fresh in [('edit', 559), ('repeat', 563)]:
            run = row[arm][phase]
            assert run['exit'] == 0 and run['units'] == 619 and run['fresh'] == fresh
            assert run['wall_ns'] > 0
            for stream in ('cargo_stdout_sha256', 'cargo_stderr_sha256'):
                assert len(bytes.fromhex(run[stream])) == 32
        oracle = row[arm]['behavior']
        assert oracle['listed'] == 200 and oracle['state'] == state
        assert oracle['e2e_sha256'] == expected_elf[state] and set(oracle['tests']) == tests
        for assertion in oracle['tests'].values():
            assert assertion['exit'] == (101 if state == 'notebook' else 0)
            assert all(len(bytes.fromhex(assertion[stream])) == 32 for stream in ('stdout_sha256', 'stderr_sha256'))

def seconds(run, phase):
    if phase == 'edit_plus_repeat':
        return seconds(run, 'edit') + seconds(run, 'repeat')
    return run[phase]['wall_ns'] / 1e9

for state in ('notebook', 'original', 'both'):
    selected = [row for row in samples if state == 'both' or row['state'] == state]
    for phase in ('edit', 'repeat', 'edit_plus_repeat'):
        control, candidate = [[seconds(row[arm], phase) for row in selected] for arm in 'AB']
        reduction = 1 - math.exp(statistics.fmean(math.log(b / a) for a, b in zip(control, candidate, strict=True)))
        assert reported[state][phase] == {
            'pairs': len(selected), 'median_a_seconds': statistics.median(control),
            'median_b_seconds': statistics.median(candidate),
            'faster': sum(b < a for a, b in zip(control, candidate, strict=True)), 'paired_reduction': reduction,
        }
print('Verified 48 timed edit/repeat commands, 24 test inventories and 48 notebook assertions.')
