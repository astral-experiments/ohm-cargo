"""Verify the release-18 result and replay the Cargo source census after unpacking."""
import csv
from hashlib import sha256
from itertools import combinations
import json
from math import comb, isclose
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import zipfile


root = Path(__file__).resolve().parent
gate = json.loads((root / 'cargo/depfile-plan.json').read_text())
results = json.loads((root / 'cargo/depfile-results.json').read_text())
for name, plan in gate['cohorts'].items():
    raw = root / f'cargo/count-{name}/pairs.csv'
    claimed = results['cohorts'][name]
    assert claimed['raw_sha256'] == sha256(raw.read_bytes()).hexdigest()
    with raw.open() as stream:
        rows = list(csv.DictReader(stream))
    n = plan['pairs']
    assert len(rows) == 2*n == 2*claimed['n']
    deltas, periods = [], []
    for i, order in enumerate(plan['order']):
        pair = rows[2*i:2*i+2]
        assert [r['arm'] for r in pair] == order
        assert all(int(r['pair']) == i and r['endpoint'] == 'build' for r in pair)
        values = {r['arm']: int(r['value']) for r in pair}
        deltas.append(1-values['candidate']/values['base'])
        d = int(pair[0]['value']) - int(pair[1]['value'])
        periods.append((d > 0) - (d < 0))
    wins, losses = sum(v>0 for v in deltas), sum(v<0 for v in deltas)
    active = wins + losses
    p_sign = min(1., 2*sum(comb(active,i) for i in range(min(wins,losses)+1))/2**active)
    allocations = list(combinations(range(n), n//2))
    extreme = sum(abs(sum(v if i in first else -v for i,v in enumerate(periods))) >= abs(wins-losses) for first in allocations)
    p_order = extreme / len(allocations)
    rank = max(r for r in range(1,n//2+1) if 2*sum(comb(n,i) for i in range(r))/2**n <= .05)
    ordered = sorted(deltas)
    assert [ordered[rank-1], ordered[n-rank]] == claimed['rank_interval']
    assert statistics.median(deltas) == claimed['median_reduction'] and wins == claimed['wins']
    assert isclose(p_sign,claimed['sign_p']) and isclose(p_order,claimed['balanced_order_p'])
    assert claimed['passed'] == (ordered[rank-1] > 0 and p_sign < .05 and p_order < .05)
    receipt = json.loads((root / f'cargo/admission-{name}/admitted.json').read_text())
    assert receipt['base']['uv_d_sha256'] == receipt['candidate']['uv_d_sha256']
    assert receipt['base']['all_public_depfiles'] == receipt['candidate']['all_public_depfiles']
    assert all(receipt[arm]['ordinary_successful_uv_d_reads'] and receipt[arm]['regenerated_bytes'] > 0 for arm in ('base','candidate'))
assert results['replicated'] == all(c['passed'] for c in results['cohorts'].values())

with tempfile.TemporaryDirectory() as temp:
    scratch = Path(temp)
    census = scratch / 'cargo-history'
    shutil.copytree(root / 'cargo-history', census)
    (scratch / 'cargo').mkdir()
    shutil.copy2(root / 'cargo/snapshot.json', scratch / 'cargo/snapshot.json')
    subprocess.run([sys.executable, '-I', '-S', '-B', census / 'classify.py'], cwd=scratch, check=True, stdout=subprocess.DEVNULL)
    for filename in ('site-findings.json','commit-states.json','summary.json'):
        original = json.loads((root/'cargo-history'/filename).read_text())
        replay = json.loads((census/filename).read_text())
        if filename == 'summary.json':
            original.pop('as_of'); replay.pop('as_of')
            index = json.loads((census/'source-index.json').read_text())
            scoped = json.loads((root/'cargo/snapshot.json').read_text())
            with zipfile.ZipFile(root/'cargo-release18-audit.zip') as inner:
                frozen = inner.read('work/upstream-monitor/cargo/snapshot.json')
            full = json.loads(frozen)
            assert all(full[k] == value for k,value in scoped.items())
            replay.update(distinct_released_cargo_commits=sum(bool(v.get('releases')) for v in index['refs'].values()),
                          distinct_source_commits=replay['recognized_commits'], distinct_file_blobs=len(index['blobs']),
                          ohm_refs={k:v['sha'] for k,v in scoped['refs'].items()},
                          authoritative_release_url='https://github.com/astral-sh/ohm/releases/tag/' + index['latest_release'],
                          source_inputs={k:sha256(frozen if k=='cargo/snapshot.json' else (root/k).read_bytes()).hexdigest() for k in original['source_inputs']})
        assert replay == original, filename
print('Both release-18 cohorts, their depfiles and the complete Cargo source classification reproduced.')
