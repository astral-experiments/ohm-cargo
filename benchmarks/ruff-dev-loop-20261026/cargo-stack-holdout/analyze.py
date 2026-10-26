"""Analyze the balanced Ruff holdout and fresh workspace commands.

Pass the directory containing replay.py's measured block receipts, the fresh
three-mode directory, and the evidence output directory on the command line.
"""
import csv
import hashlib
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def table(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write_table(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def summarize(pairs):
    percentages = sorted(100 * (1 - new / old) for old, new in pairs)
    n = len(pairs)
    assert n == 12
    # Third and tenth order statistics cover a continuous median with 96.14%.
    return dict(n=n, favorable=sum(old > new for old, new in pairs),
                parent_median_ir=statistics.median(old for old, new in pairs),
                candidate_median_ir=statistics.median(new for old, new in pairs),
                median_reduction=statistics.median(percentages),
                interval=[percentages[2], percentages[-3]],
                observed_range=[percentages[0], percentages[-1]])


def exact(strata, observed):
    # Each stratum fixes the third arm's position. Conditional on this
    # positioning, the two compared arms each go first in half its blocks.
    distributions = []
    for diffs in strata.values():
        assert len(diffs) % 2 == 0
        distributions.append([
            sum(diffs) - 2 * sum(assigned)
            for assigned in itertools.combinations(diffs, len(diffs) // 2)
        ])
    extreme = sum(abs(sum(terms)) >= abs(observed)
                  for terms in itertools.product(*distributions))
    count = math.prod(map(len, distributions))
    return dict(extreme=extreme, assignments=count, p=extreme / count)


def adjust(summary):
    previous = 0
    for i, record in enumerate(sorted(summary.values(), key=lambda r: r['p'])):
        previous = max(previous, min(1, record['p'] * (len(summary) - i)))
        record['holm_p'] = previous


def heldout(run, output):
    plan = read(run / 'measure-plan.json')
    rows = table(run / 'blocks.csv')
    assert len(rows) == 36 and len(plan['schedule']) == 12
    blocks = defaultdict(dict)
    processes = []
    commands = {}
    for r in rows:
        b, pos, arm = int(r['block']), int(r['position']), r['arm']
        assert arm == plan['schedule'][b][pos] and arm not in blocks[b]
        total = int(r['total_ir'])
        blocks[b][arm] = pos, total
        receipt = read(run / f'{b:02}-{pos}-{arm}.json')
        assert receipt['arm'] == arm and receipt['total_ir'] == total and sum(ir for cmd, ir in receipt['counts']) == total
        for cmd, ir in receipt['counts']:
            key=hashlib.sha256(cmd.encode()).hexdigest()
            commands[key]=cmd
            processes.append(dict(block=b, position=pos, arm=arm, program=Path(cmd.split()[0]).name,
                                  command_sha256=key, instructions=ir))
    comparisons = {}
    for baseline, third in [('parent', 'seven'), ('seven', 'parent')]:
        values, strata = [], defaultdict(list)
        for b in sorted(blocks):
            data = blocks[b]
            oldpos, old = data[baseline]
            newpos, new = data['combined']
            thirdpos = data[third][0]
            values.append((old, new))
            strata[thirdpos].append((old - new) if oldpos < newpos else (new - old))
        assert sorted(map(len, strata.values())) == [4, 4, 4]
        stat = summarize(values)
        stat.update(exact(strata, sum(a - b for a, b in values)))
        assert stat['assignments'] == 216
        comparisons[baseline] = stat
    adjust(comparisons)
    write_table(output / 'blocks.csv', rows)
    write_table(output / 'processes.csv', processes)
    save(output / 'commands.json', commands)
    save(output / 'subjects.json', plan)
    save(output / 'roster.json', read(run / 'artifact-roster.json'))
    return dict(comparisons=comparisons, validation=read(run / 'cache-validation.json'))


def fresh(run, output):
    comparisons, raw = {}, []
    for index, mode in enumerate(['check', 'build', 'test']):
        root = run / mode
        records = read(root / 'cache-records.json')
        assert records['identical'] and not any(records['changes'].values())
        pairs, strata = [], {'all': []}
        orders = []
        for r in table(root / 'pairs.csv'):
            first = r['first_arm']
            old, new = int(r['parent_ir']), int(r['candidate_ir'])
            assert first in ['parent','candidate']
            orders.append(first)
            pairs.append((old,new))
            strata['all'].append((old - new) if first == 'parent' else (new - old))
            raw.append(dict(mode=mode, seed=946271+index, **r))
        assert orders.count('parent') == orders.count('candidate') == 6
        stat = summarize(pairs)
        stat.update(exact(strata, sum(a-b for a,b in pairs)))
        assert stat['assignments'] == 924
        stat['registry_record_counts'] = records['counts']
        comparisons[mode] = stat
    adjust(comparisons)
    write_table(output / 'fresh-pairs.csv',raw)
    return comparisons


if __name__ == '__main__':
    edited_dir, fresh_dir, out = map(Path, sys.argv[1:])
    save(out / 'summary.json', dict(heldout=heldout(edited_dir,out), fresh=fresh(fresh_dir,out)))
