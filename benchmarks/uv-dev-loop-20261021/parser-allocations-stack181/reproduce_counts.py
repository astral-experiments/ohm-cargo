#!/usr/bin/env python3
"""Read-only profile/table checks and the fixed Cargo-instruction statistics."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import random
import tarfile

HERE = Path(__file__).resolve().parent


def quantile(values, probability):
    position = (len(values) - 1) * probability
    low = int(position)
    fraction = position - low
    return values[low] * (1 - fraction) + values[min(low + 1, len(values) - 1)] * fraction


def statistics(rows):
    logs = [math.log(a / b) for a, b, _ in rows]
    generator = random.Random(1701)
    boot = sorted(math.fsum(generator.choices(logs, k=len(logs))) / len(logs) for _ in range(20000))
    alpha = (1 - 0.99) / 2
    wins = sum(x > 0 for x in logs)
    losses = sum(x < 0 for x in logs)
    n = wins + losses
    sign_p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n) if n else 1.0
    order = {label: 1 - 1 / math.exp(math.fsum(math.log(a / b) for a, b, o in rows if o == label) /
             sum(o == label for _, _, o in rows)) for label in ('AB', 'BA')}
    return {'pairs': len(logs), 'wins': wins, 'losses': losses, 'ties': len(logs) - n,
            'reduction': 1 - 1 / math.exp(math.fsum(logs) / len(logs)),
            'interval_99': [1 - 1 / math.exp(quantile(boot, alpha)), 1 - 1 / math.exp(quantile(boot, 1 - alpha))],
            'sign_p': sign_p, 'order_reduction': order}


def main():
    subset = json.loads((HERE / 'PUBLICATION-SUBSET.json').read_text())
    original = json.loads((HERE / 'ORIGINAL-IR-MANIFEST.json').read_text())
    summary = json.loads((HERE / 'summary.json').read_text())
    expected = subset['selected']
    assert set(expected).isdisjoint(subset['omitted_private'])
    assert set(expected) | set(subset['omitted_private']) == set(original['files'])
    archive_path = HERE / 'raw-ir.tar.gz'
    with archive_path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == subset['publication_archive_sha256']
    payload = {}
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            name = member.name
            assert member.isfile() and name in expected and name not in payload
            assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
            data = archive.extractfile(member).read()
            assert len(data) == expected[name]['bytes']
            assert hashlib.sha256(data).hexdigest() == expected[name]['sha256'] == original['files'][name]
            payload[name] = data
    assert set(payload) == set(expected)
    verified, workflows = set(), {}
    # Both complete profile/table audits finish before either effect is calculated.
    for workflow, seed in [('check', 20261021121), ('test', 20261021122)]:
        prefix = f'results/ir-{workflow}/'
        manifest = json.loads(payload[prefix + 'manifest.json'])
        samples = json.loads(payload[prefix + 'samples.json'])
        assert manifest['state'] == 'complete'
        assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (12, 2, seed)
        assert manifest['variant_sha256'] == manifest['variant_sha256_after']
        assert len(samples) == 28
        assert json.loads(payload[f'benchmark/ir-{workflow}.json']) == manifest['configuration']
        assert len(list(csv.DictReader(io.StringIO(payload[prefix + 'samples.csv'].decode())))) == 28
        planned = [(stage, pair, position, variant, 'AB' if order[0] == 'baseline' else 'BA')
                   for stage in ('warmup', 'measurement')
                   for pair, order in enumerate(manifest['plans'][stage])
                   for position, variant in enumerate(order)]
        assert [(r['stage'], r['pair'], r['position'], r['variant'], r['order']) for r in samples] == planned
        pairs = {}
        for row in samples:
            assert row['returncode'] == row['prepare']['returncode'] == 0 and row['executable_unchanged']
            assert row['installed_sha256'] == manifest['variant_sha256'][row['variant']]
            assert '--trace-children=no' in row['command']
            if workflow == 'test':
                assert '--no-run' in row['command']
            metric = row['metric_files']['cargo_ir']
            name = prefix + Path(metric['path']).name
            data = payload[name]
            assert hashlib.sha256(data).hexdigest() == metric['sha256']
            lines = data.decode().splitlines()
            events = [x.split()[1:] for x in lines if x.startswith('events:')]
            totals = [list(map(int, x.split()[1:])) for x in lines if x.startswith('summary:')]
            assert len(events) == len(totals) == 1
            counter = totals[0][events[0].index('Ir')]
            assert counter == row['metrics']['cargo_ir'] == row['metric_cargo_ir'] and counter > 0
            assert name not in verified
            verified.add(name)
            if row['stage'] == 'measurement':
                pair = pairs.setdefault(row['pair'], {'order': row['order']})
                assert pair['order'] == row['order'] and row['variant'] not in pair
                pair[row['variant']] = counter
        assert set(pairs) == set(range(12))
        assert sum(p['order'] == 'AB' for p in pairs.values()) == 6
        workflows[workflow] = [(pairs[i]['baseline'], pairs[i]['candidate'], pairs[i]['order']) for i in range(12)]
    assert len(verified) == 56
    results = {workflow: statistics(rows) for workflow, rows in workflows.items()}
    for workflow, result in results.items():
        accepted = summary['instructions'][workflow]
        assert result['pairs'] == accepted['pairs'] and result['wins'] == accepted['wins']
        assert abs(result['reduction'] - accepted['reduction']) < 1e-12
        assert all(abs(a - b) < 1e-12 for a, b in zip(result['interval_99'], accepted['interval_99']))
        assert result['sign_p'] == accepted['sign_p']
        assert result['reduction'] >= .01 and result['interval_99'][0] > 0 and result['sign_p'] <= .01
        assert all(x > 0 for x in result['order_reduction'].values())
    print(json.dumps({'all_publication_members_verified': len(payload), 'full_profiles_verified': len(verified),
        'both_profile_table_audits_preceded_statistics': True, 'instrumented_elapsed_time_not_analyzed': True,
        'native_data_not_read': True, 'instructions': results}, indent=2))


if __name__ == '__main__':
    main()
