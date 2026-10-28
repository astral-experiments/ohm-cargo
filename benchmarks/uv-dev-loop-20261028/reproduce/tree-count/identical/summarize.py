#!/usr/bin/env python3
"""Render prespecified initial and conditional repeat outcomes from raw process counts."""
import collections
import csv
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ROLES = ('cargo', 'rustc', 'wild')


def read_cohort(root, ids, alpha):
    rejected = sorted(root.glob('rejected-*.json'))
    path = root / 'samples.csv'
    with path.open() as f:
        rows = list(csv.DictReader(f))
    if rejected or len(rows) != 16:
        reason = json.loads(rejected[0].read_text())['error'] if rejected else 'incomplete'
        return {'status': 'rejected' if rejected else 'incomplete', 'pairs': len(rows)//2, 'reason': reason}
    groups = collections.defaultdict(dict)
    sources = collections.defaultdict(set)
    positions = collections.defaultdict(list)
    for r in rows:
        n = int(r['pair'])
        if r['arm'] in groups[n] or r['mode'] != 'count':
            raise ValueError(f'Unexpected row in {path}: {r}')
        groups[n][r['arm']] = {k: int(r[k]) for k in (*ROLES, 'value')}
        sources[n].add(r['source_sha256'])
        positions[n].append((int(r['order']), r['arm']))
        if sum(groups[n][r['arm']][role] for role in ROLES) != int(r['value']):
            raise ValueError(f'Wrong role sum in {path}')
    if set(groups) != set(ids) or any(set(g) != {'base', 'candidate'} for g in groups.values()):
        raise ValueError(f'Missing pair in {path}')
    if any(len(hashes) != 1 for hashes in sources.values()) or len(set.union(*sources.values())) != 8:
        raise ValueError(f'The eight paired edits do not match in {path}')
    cfg = json.loads((root/'protocol.json').read_text())
    chosen = cfg['measured_edits'] if isinstance(cfg['measured_edits'],list) else list(ids)
    for n, order in zip(chosen, cfg['order'], strict=True):
        if positions[n] != list(enumerate(order)):
            raise ValueError(f'Arm order differs from the registered schedule in {path}')
    changes = sorted(1-g['candidate']['value']/g['base']['value'] for g in groups.values())
    pos, neg = sum(v>0 for v in changes), sum(v<0 for v in changes)
    n = pos + neg
    p = min(1, 2*sum(math.comb(n,k) for k in range(min(pos,neg)+1))/2**n)
    median = statistics.median(changes)
    arms = {arm: {role: statistics.median(g[arm][role] for g in groups.values())/1e9
                  for role in (*ROLES, 'value')} for arm in ('base','candidate')}
    shares = {r: statistics.median(g['base'][r]/g['base']['value'] for g in groups.values()) for r in ROLES}
    with next(root.glob('pilot-*-native-base/receipt.json')).open() as f:
        roster = json.load(f)['roster']
    status = 'passed' if median>0 and p<alpha else 'regression' if median<0 and p<alpha else 'inconclusive'
    return dict(status=status, pairs=8, gain=median,
                lo=changes[0], hi=changes[-1], wins=pos, p=p, arms=arms, shares=shares, roster=roster)


def inspect(root, ids, alpha, missing):
    if (root / 'samples.csv').is_file():
        return read_cohort(root, ids, alpha)
    rejected = sorted(root.glob('rejected-*.json'))
    if rejected:
        return dict(status='rejected', pairs=0, reason=json.loads(rejected[0].read_text())['error'])
    return dict(status=missing, pairs=0)


def summarize():
    lines = ['# Edited uv instruction sums', '',
             'The sum covers Cargo, every released-rustc invocation, and every Wild invocation, including their threads. Both arms compile uv with the released Ohm rustc and use Wild `--no-fork`. The kernel, wrappers, `cc`, `collect2` and unwrapped forked work are outside the sum. Each pair changes a private same-length literal. No tests run.', '',
             '| Cargo command | Cohort | Pairs | Baseline G instructions | Candidate G instructions | Median paired reduction [rank interval] | Improved | Exact sign p | Gate |',
             '| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |']
    shares = ['| Command | Cohort | Cargo | rustc | Wild |', '| --- | --- | ---: | ---: | ---: |']
    notes = []
    for ep, cmd in (('check','cargo check'),('build','cargo build'),('test','cargo test --no-run')):
        initial_root = HERE / 'results' / ep
        repeat_root = HERE.parent / 'replica/results' / ep
        if (repeat_root/'protocol.json').is_file():
            first_cfg = json.loads((initial_root/'protocol.json').read_text())
            repeat_cfg = json.loads((repeat_root/'protocol.json').read_text())
            if any(first_cfg[key] != repeat_cfg[key] for key in ('uv','sha256','rustc_sha256','command','pinned_cpus')):
                raise ValueError(f'{ep} executable identities, command or affinity differ between cohorts')
        primary = inspect(initial_root, range(10,18), .05/3, 'pending')
        pending = 'pending' if primary['status']=='passed' else 'not eligible' if primary['status'] in ('inconclusive','regression','rejected') else 'awaiting initial gate'
        repeat = inspect(repeat_root, range(20,28), .05, pending)
        for label, result in (('Initial',primary),('Independent repeat',repeat)):
            if 'gain' not in result:
                lines.append(f"| `{cmd}` | {label} | {result['pairs']} | — | — | — | — | — | {result['status']} |")
                if result.get('reason') and result['status']=='rejected':
                    notes.append(f"**{cmd} {label.lower()}.** {result['reason']}")
                continue
            a, b = result['arms']['base'], result['arms']['candidate']
            lines.append(f"| `{cmd}` | {label} | 8 | {a['value']:.3f} | {b['value']:.3f} | {result['gain']:.3%} [{result['lo']:.3%}, {result['hi']:.3%}] | {result['wins']}/8 | {result['p']:.6g} | {result['status']} |")
            shares.append(f"| `{cmd}` | {label} | " + ' | '.join(f"{result['shares'][r]:.2%} ({a[r]:.3f} → {b[r]:.3f} G)" for r in ROLES) + ' |')
            rustc, links = [], []
            for role, key in result['roster']['roles']:
                if role == 'rustc':
                    args = json.loads(key)
                    name = args[args.index('--crate-name')+1] if '--crate-name' in args else 'query'
                    kind = 'test' if '--test' in args else args[args.index('--crate-type')+1] if '--crate-type' in args else 'probe'
                    rustc.append(f'{name} ({kind})')
                elif role == 'wild':
                    links.append(Path(json.loads(key)).name)
            notes.append(f"**{cmd} {label.lower()}.** Verified {len(rustc)} rustc invocations ({', '.join(rustc)}), {len(links)} Wild invocations ({', '.join(links) or 'none'}), and {len(result['roster']['tests'])} test executables.")
        if primary['status']=='passed' and repeat['status']!='passed':
            notes.append(f"**{cmd}.** The positive initial result {('has not yet been independently replicated' if repeat['status'] in ('pending','incomplete') else 'did not pass the independent repeat') }.")
    lines += ['', 'The min–max rank interval has 99.22% coverage for a continuous median at eight pairs. Sign tests exclude ties. A repeatable direction requires a positive median and two-sided p < .05/3 in the initial cohort, then a positive median and p < .05 in a separate, fresh cohort. Only initially passing endpoints qualify for the repeat.', '',
              '## Baseline instruction shares', '',
              'Each percentage is the median of baseline role / baseline total across the eight source edits. Parentheses show the separate baseline and candidate median role counts in billions. Medians are computed independently.', '', *shares, '',
              '## Workload admission', '', 'The live jobserver may distribute worker threads differently across matching link outputs. All observed threads contribute to each linker count. The frozen admission gate checks which compiler and linker work the command invoked.', '', *[n+'\n' for n in notes],
              'The rejected first pilot compared the structural check edit, which compiled three targets, with a later literal change, which compiled only the library. It contributes no samples. Each subsequent cohort freezes the exact compiler and linker roster from four identical-state native/count admission cells, then checks it on every held-out observation.', '']
    (HERE / 'summary.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    summarize()
