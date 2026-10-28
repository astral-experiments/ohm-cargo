"""Reconstruct the native reduction independently from the terminal PID and ELF records."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

here=Path(__file__).resolve().parent
def dec(f):return json.loads(gzip.decompress((here/f).read_bytes()))
def dig(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def text_hash(s):return hashlib.sha256(s.encode()).hexdigest()
data=dec('products.json.gz');trace=dec('native-traces.json.gz')
plan=json.loads((here/'plan.json').read_bytes());subjects=json.loads((here/'images.json').read_bytes())
assert {r['arm']:r['sha256'] for r in subjects}==plan['cargo']
assert trace['registration']==data['registration']=={'ref':'d45eb59141a0913ca429f6b44a56b9adf68ea35d','sha256':'190e3b2e9a954a08274912df804a9582fe61645e078a8b47c093c9fed3e1a000'}
assert data['exit']=='0' and trace['sdk']=={k:plan['sdk'][k] for k in ('wild','rustc')}
assert json.loads(trace['api']['before-build']['api-rustc.status.json'])['exit']==1
assert 'E0599' in trace['api']['before-build']['api-rustc.stderr'] and 'to_std_range' in trace['api']['before-build']['api-rustc.stderr']
assert json.loads(trace['api']['after-build']['api-rustc.status.json'])['exit']==0 and trace['api']['after-build']['api-run.stdout']=='1..4\n'
assert trace['api']['after-build']['api-probe.rs']==trace['api']['before-build']['api-probe.rs']
assert set(trace['runs'])==set(data['receipts'])
assert len(trace['runs'])==11
names=set(plan['expected_harnesses']);num={};references={};elf_hashes=None;listed={}
total_children=0
for phase in data['receipts']:
    cap=data['receipts'][phase];actual=trace['runs'][phase];prod=cap['products'];children=actual['children'];count=collections.Counter()
    original={j['raw']:j for j in cap['jobs']}
    assert collections.Counter(j['raw'] for j in cap['jobs'])==collections.Counter(c['original_exec'] for c in children)
    assert len({(c['trace'],c['original_exec']) for c in children})==len(children)
    assert actual['source_sha256']==cap['files']['cargo.stdout']['sha256'] and actual['products_sha256']==cap['files']['products.json']['sha256']
    assert len(actual['typed_cargo_rows'])==prod['units'] and dig(actual['typed_cargo_rows'])==prod['roster']
    sel=collections.Counter();links=collections.Counter()
    for c in children:
        j=original[c['original_exec']]
        assert c['trace_sha256']==cap['process_trace_digests'][c['trace']] and c['original_argv']==j['argv']
        assert c['exit']==j['exit']==0 and c['binary']==trace['sdk'][c['kind']]
        a=c['argv']
        if c['kind']=='wild':
            kind='wild';dest=Path(a[a.index('-o')+1]).name;assert dest==j['target'];links[dest]+=1
        else:
            assert c['kind']=='rustc'
            kind='link-only' if any(v=='link-only' or v.startswith('-Zlink-only') for v in a) else 'full'
            crate=a[a.index('--crate-name')+1];assert crate==j['target']
            if '--test' in a and crate in names:sel[crate]+=1
        assert kind==j['kind'];count[kind]+=1
    assert dict(count)==prod['work'] and not prod['diag'];total_children+=len(children)
    if phase=='settled-build':assert prod['fresh']==prod['units'] and not count
    if not phase[0].isdigit():continue
    i,arm,step=phase.split('-');assert plan['order'][int(i)-1]==arm
    assert set(prod['harness'])==names and prod['units']==11
    retained=actual['terminal_elf'];assert {key:v['sha256'] for key,v in retained.items()}==prod['elf'] and len(retained)==6
    raw=tuple(sorted(prod['elf'].items()))
    if elf_hashes is None:elf_hashes=raw
    assert raw==elf_hashes
    for t in sorted(names):
        item=prod['harness'][t];listing=cap['verbatim']['list-'+t+'.stdout']
        assert item['listing']==cap['files']['list-'+t+'.stdout']['sha256']==text_hash(listing)
        assert item['sha256']==prod['elf'][item['file']] and cap['files']['list-'+t+'.stderr']['size']==0
        if t in listed:assert listed[t]==listing
        else:listed[t]=listing
    key=['units','fresh','roster','diag','harness','elf']
    snapshot={k:prod[k] for k in key}
    if step in references:assert references[step]==snapshot
    else:references[step]=snapshot
    if step=='repeat':assert not count and prod['fresh']==11;continue
    expected=2 if arm=='B' else 1
    assert sel=={t:expected for t in names}
    assert all(links[retained[prod['harness'][t]['file']]['basename']]==expected for t in names)
    by=({'full':14,'wild':10} if arm=='B' else {'full':10,'wild':6})
    assert dict(count)==by
    num[phase]=by
assert len(num)==4 and data['outcome']['admitted'] is True and data['outcome']['timing_observations']==0
assert references['first']['roster']==references['repeat']['roster']
print(json.dumps(dict(first_selections=num,four_matching_harnesses=sorted(names),raw_equal_elf=len(elf_hashes),
                      listed_tests={t:s.strip().splitlines()[-1] for t,s in sorted(listed.items())},
                      native_processes_checked=total_children,unchanged_builds_with_zero_work=4,changed_api_output='1..4',
                      no_run=True,timing_samples=0),sort_keys=True,indent=2))
