"""Check all frozen observations, native artifacts, hidden-tool traces and paired tests."""
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))


D = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
plan_hash = '03a651402afa58a11a4ff9fc952c486cb2f4b32088b3d546a054a00df284743f'
assert digest(D / 'screen4-registration.json') == plan_hash
plan = json.loads((D / 'screen4-registration.json').read_text())
subject = json.loads((D / 'subject.json').read_text())
assert subject['plan'] == plan_hash and subject['affinity'] == '0-3'
pins = plan['subject']
assert subject['sha256'] == {'P': pins['golden_Cargo_sha256'], 'V': pins['V']['cargo_sha256'],
        'C': pins['C']['cargo_sha256'], 'driver': pins['compiler_driver_sha256'], 'rustc': pins['frontend_sha256']}
assert digest(D / 'observer-edit-screen1.patch') == pins['C']['patch_sha256']
assert digest(D / 'heldout-fixture-sha256.json') == subject['source_manifest']
for f, expected in json.loads((D / 'heldout-fixture-sha256.json').read_text()).items():
    assert digest(D / 'heldout-fixture' / f) == expected

records=[json.loads(s) for s in (D/'command-records.jsonl').read_text().splitlines()]
assert len(records)==len({x['phase'] for x in records})==114
from collections import Counter,defaultdict
from pathlib import Path
with (D/'successful-execs.csv').open() as f:
    calls=list(csv.DictReader(f))
groups=defaultdict(list)
for item in calls: groups[item['phase']].append(item)
quality=json.loads((D/'trace-quality.json').read_text())
assert len(calls)==quality['completed_execve_events'] and len(groups)==quality['traced_invocations']==66
assert set(quality['unknown_unfinished_without_syscall_name_or_result']) <= set(groups)
items={}
for val in records:
    name=val['phase'];seen=groups[name] if not val['native_timing'] else []
    assert name not in items and val['success']
    assert len(seen)>0 if not val['native_timing'] else name not in groups
    if seen:
        assert [int(q['ordinal']) for q in seen]==list(range(1,len(seen)+1))
        assert [(q['local_process'],q['image']) for q in seen[:2]]==[('1','rustup-cargo-proxy'),('1','cargo')]
        assert all(q['image'] in ('rustup-cargo-proxy','cargo','rustc','cc','collect2','ld.bfd') for q in seen)
    roster=[{'crate':q['crate'],'mode':q['rustc_mode'],'capture':q['binary_depinfo']=='True','checksum':q['checksum_flag']=='True'} for q in seen if q['crate']]
    items[name]={'phase':name,'arm':val['arm'],'native_products':val['products'],'source':val['source_sha256'],
                 'readers':{k:dict(signed='stored_blake3' in v,complete=v['complete']) for k,v in val['readers'].items()},
                 'roster':roster,'timed':val['native_timing'],'ns':val['ns']}
    if name.startswith('audit-') and '-training-' not in name:
        count=3 if '-edit-' in name else 0
        for tool in ('cc','collect2','ld.bfd'):
            assert sum(q['image']==tool for q in seen)==count,(name,tool)
totals=Counter()
with (D/'library-reads.csv').open() as f:
    for x in csv.DictReader(f): totals[(x['phase'],x['process'],x['input_class'])]+=int(x['bytes'])
with (D/'process-reads.csv').open() as f:
    assert dict(totals)=={(x['phase'],x['process'],x['input_class']):int(x['bytes']) for x in csv.DictReader(f)}
golds = {False: items['empty-0'], True: items['empty-1']}
names = ('hold_direct', 'hold_indirect', 'hold_plain')
readers = {'hold_direct', 'hold_bridge'}
assert all(row['arm'] == 'P' and set(row['native_products']) == set(names) for row in golds.values())
for root in names:
    old = golds[False]['native_products'][root]
    new = golds[True]['native_products'][root]
    assert (old['output'] != new['output']) == (root != 'hold_plain')
    assert (old['sha256'] != new['sha256']) == (root != 'hold_plain')

raw = []
summary = {}
for phase in ('edit', 'noop'):
    ratios, ms, order, dirs = [], {'V': [], 'C': []}, [], []
    for block in plan['orders']:
        bid = block['block']
        is_edit = phase == 'edit'
        new = (block['edited_state'] == 'add') == is_edit
        alloc = block[phase]
        dirs.append(block['edited_state'])
        order.append(alloc)
        assert sorted(alloc) == ['C', 'V']
        arms = {}
        for k in alloc:
            native = items[f'native-{bid:02}-{phase}-{k}']
            audit = items[f'audit-{bid:02}-{phase}-{k}']
            for row in (native, audit):
                assert row['arm'] == k and row['native_products'] == golds[new]['native_products']
                assert row['source'] == golds[new]['source']
                assert len(row['readers']) == 2 and all(v['complete'] and v['signed'] for v in row['readers'].values())
            assert native['timed'] and not audit['timed']
            rr = audit['roster']
            assert len(rr) == (5 if is_edit else 0)
            assert {x['crate'] for x in rr if x['mode'] == 'full'} == (readers | {'hold_shapes','hold_indirect'} if is_edit else set())
            assert {x['crate'] for x in rr if x['mode'] == 'relink'} == ({'hold_plain'} if is_edit else set())
            assert {x['crate'] for x in rr if x['capture']} == (readers if is_edit else set())
            assert all(x['checksum'] for x in rr if x['capture'])
            ns = native['ns']
            ms[k].append(ns / 1e6)
            arms[k] = ns
            raw.append({'block':str(bid),'phase':phase,'order':alloc,'arm':k,'nanoseconds':str(ns),
                        'source_sha256':native['source'],**{n:native['native_products'][n]['sha256'] for n in names}})
        ratios.append(math.log(arms['V'] / arms['C']))
    pct = sorted(-100 * math.expm1(-x) for x in ratios)
    result = {'v3_ms': statistics.median(ms['V']), 'v4_ms': statistics.median(ms['C']),
              'paired_median_reduction_pct': statistics.median(pct), 'paired_median_CI_pct': [pct[2],pct[9]],
              'favorable': sum(x > 0 for x in pct), 'n': len(ratios)}
    if phase == 'edit':
        groups = [[i for i,x in enumerate(dirs) if x == d] for d in ('add','remove')]
        assert all(len(g) == 6 and sum(order[i] == 'VC' for i in g) == 3 for g in groups)
        first_minus_second = [x if a == 'VC' else -x for x, a in zip(ratios, order)]
        null = []
        for halves in itertools.product(*(itertools.combinations(g,3) for g in groups)):
            v_first = set(itertools.chain.from_iterable(halves))
            null.append(sum(x * (1 if i in v_first else -1) for i,x in enumerate(first_minus_second)))
        assert len(null) == 400
        hits = sum(t >= sum(ratios) - 1e-12 for t in null)
        result.update({'one_sided_exact_p':hits / len(null),'assignments':len(null),'upper_tail_assignments':hits,
                       'qualified':pct[2] > 0 and result['favorable'] >= 10 and hits / len(null) < 0.05})
    else:
        assert order.count('VC') == order.count('CV') == 6
        result['lower_bound_above_negative_5_pct'] = pct[2] >= -5
    summary[phase] = result
with (D/'native.csv').open() as f:
    recorded = list(csv.DictReader(f))
assert sorted(recorded,key=lambda r: (int(r['block']),r['phase'],r['arm'])) == sorted(raw,key=lambda r: (int(r['block']),r['phase'],r['arm']))
assert summary==json.loads((D/'summary.json').read_bytes())
print(json.dumps(summary, indent=2))
