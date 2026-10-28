#!/usr/bin/env python3
"""Summarize both registered cohorts after all native workload audits."""
import collections
import csv
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def cohort(name,cfg,plan):
    root = HERE/'results'/name
    if not json.loads((root/'POST.json').read_text())['matched'] or list(root.glob('FAILED-*.json')):
        raise ValueError(f'{name}: missing final audit or a recorded failure')
    rows = list(csv.DictReader((root/'pairs.csv').open()))
    if len(rows)!=48:
        raise ValueError('all 48 observations are required')
    byarm = collections.defaultdict(list)
    changes = []
    sources = set()
    for i,block in enumerate(cfg['schedule']):
        pair = rows[2*i:2*i+2]
        if ([r['arm'] for r in pair]!=block['arms'] or [int(r['rank']) for r in pair]!=[0,1]
                or any(int(r['pair'])!=i or r['literal']!=block['literal'] for r in pair)
                or len({r['source_sha256'] for r in pair})!=1 or pair[0]['source_sha256'] in sources):
            raise ValueError(f'{name}: invalid pair {i}')
        sources.add(pair[0]['source_sha256'])
        for r in pair:
            arm = r['arm']
            if r['cargo_sha256']!=plan['arms'][arm]['cargo'][1] or r['wild_sha256']!=plan['arms'][arm]['wild'][1]:
                raise ValueError(f'{name}: unexpected ELF identity')
            byarm[arm].append(int(r['elapsed_ns'])/1e9)
        changes.append(1-byarm['candidate'][-1]/byarm['base'][-1])
    changes.sort()
    wins,losses=sum(x>0 for x in changes),sum(x<0 for x in changes)
    n=wins+losses
    p=min(1,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n)
    med=statistics.median(changes)
    passed=med>0 and p<.05 and (name!='initial' or changes[6]>0)
    return dict(base=statistics.median(byarm['base']),candidate=statistics.median(byarm['candidate']),
                reduction=med,p=p,lo=changes[6],hi=changes[17],wins=wins,ties=24-n,passed=passed)


def main():
    plan=json.loads((HERE/'plan.json').read_text())
    result={k:cohort(k,v,plan) for k,v in plan['cohorts'].items()}
    passed=all(v['passed'] for v in result.values())
    (HERE/'results.json').write_text(json.dumps(dict(repeatable=passed,cohorts=result),indent=2)+'\n')
    rows=['# Native edited test-build time with all eight changes','',
          'The whole-command clock covers full-workspace `cargo test --no-run --locked --offline -j8`, including the released Ohm rustc and default native Wild. Each pair builds the same new private-body literal from matched targets. No tests execute.','',
          '| Cohort | Baseline median | Candidate median | Median paired reduction [97.73% rank interval] | Improved | Ties | Exact sign p | Gate |',
          '| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |']
    for name,r in result.items():
        rows.append(f"| {name} | {r['base']:.3f} s | {r['candidate']:.3f} s | {r['reduction']:.3%} [{r['lo']:.3%}, {r['hi']:.3%}] | {r['wins']}/24 | {r['ties']} | {r['p']:.6g} | {'passed' if r['passed'] else 'inconclusive'} |")
    rows.extend(['', '**Repeatable whole-command speedup.**' if passed else '**No repeatable whole-command speedup established.**', '',
                 'Before and after timing, native traces verified six released rustc processes and five real Wild invocations per arm. Every one of the 96 timed commands rebuilt only uv and reported the complete 72-executable test roster. The two Cargo binaries were independently self-trained. The baseline linker is the matched release-source Wild, and the candidate linker contains both Wild changes.', ''])
    (HERE/'summary.md').write_text('\n'.join(rows))


if __name__=='__main__':
    main()
