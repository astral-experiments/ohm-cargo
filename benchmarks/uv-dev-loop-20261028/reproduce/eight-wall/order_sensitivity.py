#!/usr/bin/env python3
"""Exact assignment-balanced sign randomization diagnostic, separate from original gates."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from math import comb
from pathlib import Path


def histogram(period_signs, baseline_first):
    positive = period_signs.count(1)
    negative = period_signs.count(-1)
    ties = period_signs.count(0)
    hist = Counter()
    for p in range(positive + 1):
        for q in range(negative + 1):
            z = baseline_first - p - q
            if 0 <= z <= ties:
                wins = p + negative - q
                score = 2 * wins - positive - negative
                hist[score] += comb(positive, p) * comb(negative, q) * comb(ties, z)
    assert hist.total() == comb(len(period_signs), baseline_first)
    return hist


def diagnostics(rows, schedule, metric, rank, identifiers):
    signs, wins, losses, first = [], 0, 0, 0
    sources = set()
    for i, order in enumerate(schedule):
        a, b = rows[2*i:2*i+2]
        if ([a['arm'], b['arm']] != order or [int(a[rank]), int(b[rank])] != [0, 1]
                or a['pair'] != b['pair'] or int(a['pair']) != identifiers[i]
                or a['source_sha256'] != b['source_sha256'] or a['source_sha256'] in sources):
            raise ValueError(f'pair {i} differs from registered source, order or identifier')
        sources.add(a['source_sha256'])
        delta = int(a[metric]) - int(b[metric])
        signs.append((delta > 0) - (delta < 0))
        first += a['arm'] == 'base'
        if a['arm'] == 'candidate':
            delta = -delta
        wins += delta > 0
        losses += delta < 0
    if first * 2 != len(schedule):
        raise ValueError('cohort does not have equal arm-order allocation')
    return wins - losses, histogram(signs, first)


def receipt(score, hist):
    extreme = sum(n for s,n in hist.items() if abs(s) >= abs(score))
    return dict(score=score, extreme=extreme, assignments=hist.total(),
                p=extreme / hist.total(), score_histogram=dict(sorted(hist.items())))


def read_arm(root, kind, endpoint, name):
    if kind == 'wall':
        d = root/'results'/name
        path = d/'pairs.csv'
        if not (d/'POST.json').is_file():
            return None
        if list(d.glob('FAILED-*.json')) or not json.loads((d/'POST.json').read_text())['matched']:
            return None
        blocks = json.loads((root/'plan.json').read_text())['cohorts'][name]['schedule']
        schedule = [x['arms'] for x in blocks]
        ids = list(range(len(blocks)))
        metric, rank = 'elapsed_ns', 'rank'
    else:
        d = root/('identical' if name == 'initial' else 'replica')/'results'/endpoint
        path = d/'samples.csv'
        if not (d/'admission.json').is_file() or list(d.glob('rejected-*.json')):
            return None
        plan = json.loads((d/'protocol.json').read_text())
        schedule = plan['order']
        ids = list(range(10, 18)) if name == 'initial' else plan['measured_edits']
        metric, rank = 'value', 'order'
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if not raw.endswith(b'\n'):
        return None
    rows = list(csv.DictReader(raw.decode().splitlines()))
    if len(rows) != 2 * len(schedule):
        return None
    if kind == 'roles' and any(r['mode'] != 'count' or int(r[metric]) != sum(int(r[k]) for k in ('cargo','rustc','wild')) for r in rows):
        raise ValueError('per-role values do not match the summed count')
    if kind == 'wall' and any(r['literal'] != blocks[i//2]['literal'] for i,r in enumerate(rows)):
        raise ValueError('wrong timed literal')
    score, hist = diagnostics(rows, schedule, metric, rank, ids)
    return dict(receipt(score, hist), raw_sha256=hashlib.sha256(raw).hexdigest()), hist


def main():
    p = argparse.ArgumentParser()
    p.add_argument('kind', choices=('roles','wall'))
    p.add_argument('root', type=Path)
    a = p.parse_args()
    results = {}
    label = 'Seven-change role instructions' if a.kind == 'roles' else 'Eight-change native elapsed time'
    lines = [f'# {label} with assignment-conditioned p-values', '',
             'This separate diagnostic conditions on the frozen balance of baseline-first and candidate-first pairs. It compares the absolute observed candidate wins minus losses with all assignments under the sharp no-effect null. Original sign/rank gates are reported in the main study.', '',
             '| Command | Cohort | Wins minus losses | At least as extreme | Total allocations | Two-sided conditional p |',
             '| --- | --- | ---: | ---: | ---: | ---: |']
    for ep in (('check','build','test') if a.kind == 'roles' else ('test',)):
        fits = {name:read_arm(a.root, a.kind, ep, name) for name in ('initial', 'replica')}
        result = {name: x[0] if x else None for name,x in fits.items()}
        result['stratified'] = None
        if all(fits.values()):
            joint = Counter()
            for i, n in fits['initial'][1].items():
                for j, m in fits['replica'][1].items():
                    joint[i+j] += n*m
            result['stratified'] = receipt(result['initial']['score'] + result['replica']['score'], joint)
        results[ep] = result
        for name, row in result.items():
            command = 'test --no-run' if ep == 'test' else ep
            display = (f"{row['score']} | {row['extreme']:,} | {row['assignments']:,} | {row['p']:.8g}" if row else '— | — | — | pending or inadmissible')
            lines.append(f'| `cargo {command}` | {name} | {display} |')
    (a.root/'order-sensitivity-results.json').write_text(json.dumps(results, indent=2)+'\n')
    (a.root/'order-sensitivity-results.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
