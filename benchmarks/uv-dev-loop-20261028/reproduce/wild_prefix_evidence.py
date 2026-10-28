"""Preserve measured linker inputs, checks and counts while omitting the multi-GB ELF outputs."""
from collections import defaultdict
import csv
import json
from pathlib import Path


def block_rows(root):
    plan = json.loads((root / 'actual/plan.json').read_text())
    with (root / 'actual/samples.csv').open() as stream:
        samples = list(csv.DictReader(stream))
    commands = defaultdict(list)
    for row in samples:
        commands[int(row['block']), int(row['position'])].append(row)
    if len(commands) != 32:
        raise ValueError('incomplete edited-link cohort')
    blocks = []
    for i, order in enumerate(plan['orders']):
        assert order in {'ABBA', 'BAAB'}
        sums = {'A': 0, 'B': 0}
        edits = {'A': set(), 'B': set()}
        for pos, arm in enumerate(order):
            observed = commands[i, pos]
            total, = [r for r in observed if r['unit'] == 'TOTAL']
            children = [r for r in observed if r['unit'] != 'TOTAL']
            assert len(children) == len({r['unit'] for r in children}) == 5
            assert set(r['arm'] for r in observed) == {total['arm']}
            assert (total['arm'] == 'parent') == (arm == 'A')
            assert sum(int(r['instructions']) for r in children) == int(total['instructions'])
            sums[arm] += int(total['instructions'])
            edits[arm].add(total['source'])
        assert edits['A'] == edits['B'] and len(edits['A']) == 2
        blocks.append(dict(block=i, order=order, baseline_instructions=sums['A'], candidate_instructions=sums['B']))
    assert len(blocks) == 8 and len([r for r in blocks if r['order'] == 'ABBA']) == 4
    return samples, blocks


def collect(work, files, rows):
    meta = work / 'wild-prefix/pr.json'
    chosen = json.loads(meta.read_text())['directory'] if meta.is_file() else None
    for name in ('wild-prefix', 'wild-prefix-v2'):
        root = work / name
        if not root.is_dir():
            continue
        selected = name == chosen
        dest = 'components/wild-prefix' if selected else f'experiments/{name}'
        if selected:
            files[f'{dest}/pr.json'] = meta
            source = work / 'wild-publication/initial-full/source.json'
            if source.is_file(): files[f'{dest}/source.json'] = source
        sources = [f for f in root.iterdir() if f.is_file() and f.name != 'pr.json']
        for d in ('actual', 'screen', 'holdout', 'fallback', 'fixtures', 'logs', 'pilot', 'captures', 'profile', 'links'):
            if (root / d).is_dir():
                sources.extend(f for f in (root / d).rglob('*') if f.is_file())
        suffixes = {'.csv', '.tsv', '.json', '.jsonl', '.txt', '.md', '.sha256', '.py', '.sh', '.log', '.s', '.S', '.ld', '.outpath', '.patch', '.yml'}
        for f in sources:
            if f.suffix in suffixes and 'interim' not in f.name and f.stat().st_size <= 8 * 1024**2:
                files[f'{dest}/{f.relative_to(root)}'] = f
        packet = work / 'wild-prefix-evidence.zip' if selected else root / 'evidence.zip'
        if packet.is_file(): files[f'{dest}/evidence.zip'] = packet
        if not (root / 'actual/summary.json').is_file():
            continue
        samples, blocks = block_rows(root)
        normalized = work / 'wild-publication' / name / 'block-results.csv'
        normalized.parent.mkdir(parents=True, exist_ok=True)
        with normalized.open('w') as stream:
            writer = csv.DictWriter(stream, list(blocks[0]))
            writer.writeheader()
            writer.writerows(blocks)
        files[f'{dest}/actual/block-results.csv'] = normalized
        for row in samples:
            unit = row['unit']
            rows.append(dict(change='wild-section-prefixes' if selected else name, cohort='edited linker blocks',
                             scope='edited uv, all five Wild processes' if unit == 'TOTAL' else f'edited uv, Wild for {unit}',
                             endpoint='test', pair=row['block'], order=row['position'],
                             arm='base' if row['arm'] == 'parent' else 'candidate',
                             value=row['instructions'], unit='wild_instructions'))
