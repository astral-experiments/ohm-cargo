"""Summarize all three fresh commands and recheck the frozen order and identities."""
import hashlib
from pathlib import Path
import random
import runpy
import sys

archived = not sys.argv[1:]
source, out = (None, Path(__file__).resolve().parent) if archived else map(Path, sys.argv[1:])
common = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cargo-stack-holdout' / 'analyze.py'))
read, save, table = [common[name] for name in ('read', 'save', 'table')]
hashes = {'parent': '211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc',
          'candidate': 'd0dbe4c237e7e6f6a5a482806deedae81cc08f72c5449826d13c6f4bf96ec9aa'}


def paired_summary(rows, seed):
    schedule = list(range(12))
    random.Random(seed).shuffle(schedule)
    assert [r['first_arm'] for r in rows] == ['candidate' if slot % 2 else 'parent' for slot in schedule]
    assert [int(r['block']) for r in rows] == list(range(12)) and all(r['pair'] == '0' for r in rows)
    pairs = [(int(r['parent_ir']), int(r['candidate_ir'])) for r in rows]
    diffs = [old - new for old, new in pairs]
    slots = [d if r['first_arm'] == 'parent' else -d for d, r in zip(diffs, rows)]
    stat = common['summarize'](pairs)
    stat.update(common['exact']({'all': slots}, sum(diffs)))
    return stat


comparisons, receipts, all_rows = {}, {}, []
if archived:
    stored = read(out / 'verification.json')
    published = table(out / 'pairs.csv')
for i, (mode, n_artifacts) in enumerate([('check', 520), ('build', 501), ('test', 619)]):
    if archived:
        receipt = stored[mode]
        assert receipt['fresh_artifacts'] == n_artifacts
        records, proofs = receipt['records'], receipt['index_and_proofs']
        rows = [{k: v for k, v in row.items() if k not in ('mode', 'seed')} for row in published if row['mode'] == mode]
        assert all(int(row['seed']) == 622901 + i for row in published if row['mode'] == mode)
    else:
        root = source / mode
        for arm, digest in hashes.items():
            with (root / arm).open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        records, proofs = (read(root / name) for name in ('cache-records.json', 'git-records.json'))
        assert (source / (mode + '.log')).read_text().rstrip().endswith(f'{n_artifacts} fresh units')
        rows = table(root / 'pairs.csv')
    assert records['identical'] and all(not changed for changed in records['changes'].values())
    assert proofs['after'] == proofs['before']
    seed = 622901 + i
    comparisons[mode] = paired_summary(rows, seed)
    receipts[mode] = dict(fresh_artifacts=n_artifacts, records=records, index_and_proofs=proofs)
    all_rows.extend(dict(mode=mode, seed=seed, **r) for r in rows)
common['adjust'](comparisons)
summary = dict(subject_sha256=hashes, comparisons=comparisons)
if archived:
    assert len(published) == 36 and summary == read(out / 'summary.json') and receipts == stored
    print('All 36 balanced pairs, three exact tests, Holm adjustments and validity receipts agree.')
    if (out / 'exact-source-check.json').exists():
        extra = read(out / 'exact-source-check.json')
        assert extra['statistics'] == paired_summary(table(out / 'exact-source-pairs.csv'), 618023)
        assert extra['candidate_sha256'] == read(out / 'elf-equivalence.json')['full_draft_sha256']
        assert extra['fresh_artifacts'] == 520 and extra['registry']['identical']
        print('All 12 independent pairs from the exact PR sources agree.')
else:
    common['write_table'](out / 'pairs.csv', all_rows)
    save(out / 'summary.json', summary)
    save(out / 'verification.json', receipts)
