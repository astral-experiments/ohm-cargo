"""Check both independent branch returns and their physical storage measurements."""
import hashlib
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parent
phases = {'empty-A', 'first-B', 'return-A', 'return-B', 'unchanged-B'}
crates = ['ruff_python_ast', 'ruff_python_parser']

def check_screen(path):
    rows = json.loads(path.read_bytes())
    samples = rows['samples']
    assert set(samples) == {f'pair-{i:02d}-{a}' for i in (1, 2) for a in 'PQ'}
    assert len(rows['raw_capture_sha256']) == 64
    clean = {}
    for sample in samples.values():
        assert set(sample) == phases
        for phase, measure in sample.items():
            assert measure['wall_seconds'] > 0 and measure['allocated_bytes'] > 0
            elf = measure['clean_elf_sha256']
            assert len(elf) == 64 and clean.setdefault(phase[-1], elf) == elf
            if phase.startswith('return-'):
                assert measure['dirty'] == crates
            if phase == 'unchanged-B':
                assert not measure['dirty']
            if 'component_seconds' in measure:
                assert math.isclose(sum(measure['component_seconds']), measure['wall_seconds'], abs_tol=1e-8)
    assert clean['A'] != clean['B']
    calls = rows['compiler_calls']
    if calls:
        assert len(calls) == 18
        for i in (1, 2):
            for phase in ('first-B', 'return-A', 'return-B'):
                actual = [c for c in calls if c['phase'] == f'pair-{i:02d}-Q/{phase}']
                assert sorted(c['crate'] for c in actual) == crates
                assert all(c['rustc'] == 0 and c['compressed_tables'] >= 2 for c in actual)
                if phase.startswith('return-'):
                    assert all(c['HEAD'] == c['chosen'] and c['restored_tables'] >= 2 for c in actual)
            assert not any(c['phase'] == f'pair-{i:02d}-Q/unchanged-B' for c in calls)
    for phase in ('return-A','return-B'):
        for i, saved in enumerate(rows['returned_speedups'][phase], 1):
            p, q = [samples[f'pair-{i:02d}-{arm}'][phase] for arm in 'PQ']
            ratio = p['wall_seconds'] / q['wall_seconds']
            assert math.isclose(ratio, saved, abs_tol=1e-8)
            print(path.stem, phase, i, f"{ratio:.3f}× time, {q['allocated_bytes']/p['allocated_bytes']:.4f}× storage")

for name in ('older-files', 'two-tables', 'two-tables-flate2'):
    path = root / (name + '.json')
    if path.is_file():
        check_screen(path)

def check_registered(path):
    from itertools import combinations
    from statistics import median

    data = json.loads(path.read_bytes())
    plan = data['plan']
    samples = data['samples']
    assert plan['pairs'] == 12 and len(samples) == 24
    assert plan['orders'].count('PQ') == plan['orders'].count('QP') == 6
    assert set(plan['primary']) == {'return-A', 'return-B'}
    for row in samples.values():
        assert set(row) == phases
        for phase, s in row.items():
            assert s['ELF'] == data['clean'][phase[-1]] and len(s['stdout_sha256']) == 64
            assert s['wall'] > 0 and s['cpu'] >= 0 and s['bytes'] > 0
            if phase.startswith('return-'):
                assert s['dirty'] == 2
            if phase == 'unchanged-B':
                assert s['dirty'] == 0
    gate = True
    for phase, saved in data['summary'].items():
        split = phase.split('+')
        rows = [(sum(samples[f'pair-{i:02d}-P'][k]['wall'] for k in split),
                 sum(samples[f'pair-{i:02d}-Q'][k]['wall'] for k in split)) for i in range(1,13)]
        ratios = sorted(p/q for p,q in rows)
        assert saved['all_speedups'] == ratios and saved['paired_median'] == median(ratios)
        assert saved['parent_median'] == median(p for p,q in rows)
        assert saved['candidate_median'] == median(q for p,q in rows)
        n=len(ratios)
        indices = [k for k in range(1,n//2+1) if 2*sum(math.comb(n,j) for j in range(k))/2**n <= .025]
        rank=max(indices)
        assert saved['simultaneous_ci'] == [ratios[rank-1], ratios[-rank]]
        above=sum(r>2 for r in ratios)
        assert saved['one_sided_sign_p_vs_2x'] == sum(math.comb(n,k) for k in range(above,n+1))/2**n
        observed=sum(math.log(p/q) for p,q in rows)
        effects=[math.log(p/q)*(1 if o=='PQ' else -1) for (p,q),o in zip(rows,plan['orders'])]
        schedules=list(combinations(range(n),n//2))
        pvalue=sum(abs(sum(v*(1 if i in schedule else -1) for i,v in enumerate(effects)))+1e-10>=abs(observed) for schedule in schedules)/len(schedules)
        assert saved['balanced_two_sided_p_vs_equal'] == pvalue
        if len(split)==1:
            p_bytes=[samples[f'pair-{i:02d}-P'][phase]['bytes'] for i in range(1,13)]
            q_bytes=[samples[f'pair-{i:02d}-Q'][phase]['bytes'] for i in range(1,13)]
            assert saved['storage_P']==median(p_bytes) and saved['storage_Q']==median(q_bytes)
            assert saved['storage_max_ratio']==max(q/p for p,q in zip(p_bytes,q_bytes))
        if phase in plan['primary']:
            gate &= saved['simultaneous_ci'][0]>2 and saved['storage_max_ratio']<1.10
            print('12-pair prototype',phase,f"{saved['paired_median']:.3f}×",saved['simultaneous_ci'])
    assert gate==data['gate_passed']

registered=root/'twelve-pairs.json'
if registered.is_file():
    check_registered(registered)

receipt_path = root / 'replay-qualification.json'
if receipt_path.is_file():
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt['run_orders'] == ['PQ', 'QP'] and receipt['full_timing_sample'] is False
    assert receipt['correct_storage_snapshots'] == 24 and receipt['codecs_invocations'] == 18
    assert set(receipt['elapsed_return_ratios']) == {'return-A', 'return-B'}
    assert all(len(ratios) == 2 and min(ratios) > 2 for ratios in receipt['elapsed_return_ratios'].values())
    assert len(set(receipt['matched_clean'].values())) == 2
    for relative, expected in receipt['source_sha256'].items():
        with (root.parents[1] / relative).open('rb') as member:
            assert hashlib.file_digest(member, 'sha256').hexdigest() == expected, relative
    print('Public compression replay verified against its measured source')
