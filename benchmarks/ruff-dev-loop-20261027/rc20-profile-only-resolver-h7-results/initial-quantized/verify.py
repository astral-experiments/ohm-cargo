"""Replay the complete parent/candidate result from the portable measurements with Python 3.11+."""
from pathlib import Path
import collections
import hashlib
import json
import math
import random
import statistics

root = Path(__file__).resolve().parent

def load(name):
    return json.loads((root / name).read_bytes())

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()

def metric(rows, seed):
    cells = {}
    all_deltas = []
    for a, b, key in rows:
        delta = 100 * (a - b) / a
        all_deltas.append(delta)
        cells.setdefault(key, []).append(delta)
    assert len(cells) == 4 and all(len(arr) == 8 for arr in cells.values())
    rng = random.Random(seed)
    bootstrap = sorted(statistics.median(
        arr[rng.randrange(len(arr))] for arr in cells.values() for _ in arr
    ) for _ in range(20000))
    wins = sum(v > 0 for v in all_deltas)
    losses = sum(v < 0 for v in all_deltas)
    n = wins + losses
    p = min(1., 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / (2 ** n))
    return dict(A_median_ms=statistics.median(a for a, b, k in rows) / 1e6,
                B_median_ms=statistics.median(b for a, b, k in rows) / 1e6,
                paired_pct=statistics.median(all_deltas),
                CI95_pct=[bootstrap[int((len(bootstrap) - 1) * x)] for x in (.025, .975)],
                p=p, favorable=wins, ties=len(rows)-n,
                direction_pct={d:statistics.median(v for v,r in zip(all_deltas,rows)
                                                    if r[2][0]==d) for d in ('reverse','restore')})

def main():
    for line in (root/'SHA256SUMS').read_text().splitlines():
        file_hash, name = line.split('  ')
        assert digest((root / name).read_bytes()) == file_hash, name
    plan = load('registration.json')
    records = load('rows.json')
    evidence = load('native.json')
    prior = load('prior-clean-variance.json')
    assert prior['ordinary_wall_commands']==0 and len(prior['differences'])==20
    assert prior['previous']['triple_error']!=prior['empty']['triple_error']
    images = plan['images']
    native_map=load('common-clean-output-maps.json')
    assert len(native_map)==265 and digest(canonical(native_map))==evidence['relative_map_sha256']
    assert all(a['rows']==147 and a['fresh']==147 and a['tools']==['proxy','cargo'] and
               a['relative_map_sha256']==evidence['relative_map_sha256'] and a['native_work']==0
               for a in evidence['typed'].values())
    assert len(evidence['typed'])==20 and len(evidence['sites'])==8
    for name, info in evidence['sites'].items():
        counts=collections.Counter(row['index'] for row in info['exec'])
        assert info['expected']==[counts.get(i,0) for i in range(4)]
        assert info['expected']==([1,2,2,2] if name.startswith('A-') and 'switch-' in name else [0,1,1,1])
        for entry in info['exec']:
            assert info['rvas'][entry['index']]==entry['pc_rva']
            if name.startswith('B-') and entry['index']==2:assert entry['ret_rva'] in (0x9fb8fe,0x9fc331)
    assert len(evidence['conflicts'])==8 and len({q['stderr'] for q in evidence['conflicts'].values()})==1
    for q in evidence['conflicts'].values():
        assert q['errors']==[prior['empty']['triple_error']] and q['dso']==prior['empty']['dso'] and q['status']==1
        assert q['rustc']==plan['stock']['rustc'] and q['physical_opens']>0 and len(q['processes'])==2
    for row in evidence['consumers'].values():
        assert row['held_verdict']=='rejected: Star import cannot be parenthesized'
        assert {k:v['names'] for k,v in row['tests'].items()}=={'fixtures':558,'generate_inline_tests':1}
        for k,v in row['tests'].items():
            inv=(root/'inventory'/f'{k}.txt').read_bytes()
            assert digest(inv)==v['inventory'] and sum(l.endswith(b': test') for l in inv.splitlines())==v['names']
            assert v['code']==0 and v['elf']==plan['test_elf'][k]
    orders={d:['AB']*8+['BA']*8 for d in ('reverse','restore')}
    rng=random.Random(plan['schedule_seed'])
    for arr in orders.values():rng.shuffle(arr)
    result={k:[] for k in ('edited','unchanged','sum')}
    assert len(records)==32 and len(evidence['pair_products'])==64
    for i,row in enumerate(records,1):
        direction='reverse' if i%2 else 'restore'
        assert row['pair']==i and row['direction']==direction and row['order']==orders[direction][(i-1)//2]
        ns={}
        for arm in row['order']:
            for phase in ('edit','hit'):
                v=row['commands'][arm][phase];assert v['status']==0 and v['ns']==v['end_ns']-v['start_ns']>0
                assert v['cargo']==images[arm] and v['cpus']==[24,25,26,27]
                assert v['source']==plan['root_manifest']['P' if direction=='reverse' else 'H']
                assert v['stdout_sha256']==digest(b'') and len(v['stderr_lines'])==3
                assert v['stderr_lines'][0].strip().startswith('Finished ') and all('Executable ' in l for l in v['stderr_lines'][1:])
                assert v['argv_public']==plan['command'] and v['raw_argv_sha256']==plan['raw_argv_sha256']
                assert min(v['floors']['home'],v['floors']['scratch'])>=25*2**30
                ns[arm,phase]=v['ns']
            assert evidence['pair_products'][f'{i:02d}-{arm}']==digest(b'{}\n')
        for name, phases in {'edited':['edit'],'unchanged':['hit'],'sum':['edit','hit']}.items():
            result[name].append((sum(ns['A',q] for q in phases),sum(ns['B',q] for q in phases),(direction,row['order'])))
    metrics={k:metric(v,plan['bootstrap_seed']) for k,v in result.items()}
    assert metrics==load('result.json')['metrics']
    print(json.dumps(metrics,sort_keys=True,indent=2))

if __name__=='__main__':main()
