"""Verify the stock early-test process census and native output comparisons."""
from pathlib import Path
from collections import Counter
import hashlib,json,tarfile

p=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:json.loads((p/n).read_bytes())
ledger=read('originals.json')
seen={}
for f in sorted(p.glob('*.tar.gz')):
    with tarfile.open(f) as tar:
        for obj in tar:
            assert obj.isfile() and obj.name not in seen and not obj.name.startswith('/') and '..' not in Path(obj.name).parts
            b=tar.extractfile(obj).read()
            assert h(b)==ledger['members'][obj.name]['portable']
            seen[obj.name]=b
assert set(seen)==set(ledger['members'])
get=lambda n:json.loads(seen[n])
arms=('default','disabled')
products={a:get(a+'/products.json') for a in arms}
elf={a:get(a+'/elf.json') for a in arms}
logs={a:get(a+'.json') for a in arms}
rep=read('result.json')
ts=read('thirteen-targets.json')
for a in arms:
    settings=get(a+'/inputs.json')
    assert settings['sdk']==rep['cargo_sdk'] and settings['source']==rep['source']
    assert settings['empty_shared'] and settings['empty_target'] and not settings['trust_overrides']
    command=settings['command']
    assert command[:2]==['cargo','+ohm'] and (('-Zohm-early-tests=no' in command)==(a=='disabled'))
    assert get(a+'/cargo-exit.json')['returncode']==0
    assert products[a]['units']==len(products[a]['roster'])==len(products[a]['dirty'])==619
    assert len(products[a]['executables'])==102 and len(elf[a])==110
    std=[json.loads(b) for b in seen[a+'/stdout.raw'].splitlines()]
    arts=[r for r in std if r.get('reason')=='compiler-artifact']
    assert len(arts)==619 and all(not r['fresh'] for r in arts)
    assert dict(Counter(r['profile']['test'] for r in arts if r.get('executable')))=={True:84,False:18}
    assert all(0<=row[0]<row[0]+row[1] and row[2]>0 for row in (json.loads(l) for l in seen[a+'/stdout.clock.jsonl'].splitlines()))
    ls=logs[a];jobs=ls['jobs'];wild=ls['wild']
    assert all(j['kind']=='full' and j['terminal'] for j in jobs)
    assert all(w['terminal']['result']==0 for w in wild)
    keys=Counter(j['argv_sha256'] for j in jobs)
    assert len(set(j['pid'] for j in jobs))==len(jobs)
    assert len(keys)==623 and max(keys.values())==(2 if a=='default' else 1)
    assert len(wild)==(200 if a=='default' else 188) and len(set(w['out'] for w in wild))==188
    assert len(jobs)==(636 if a=='default' else 623) and ls['counts']==rep['actual'][a]
    assert ls['counts']['rustc_queries']==36
    assert not ls['unassigned_policy']
    for ev in ls['all_policy_events']:
        marker=('accepted early ' if ev['action']=='accepted' else 'retrying ')+ev['target']
        assert any(marker.encode() in line for line in seen[a+'/stderr.raw'].splitlines())
    assert Counter(e['action'] for e in ls['all_policy_events'])==({'accepted':21,'retry':13} if a=='default' else {})
assert products['default']['roster_sha256']==products['disabled']['roster_sha256']
assert elf['default']==elf['disabled']
assert get('default/cargo-registry.json')==get('disabled/cargo-registry.json') and len(get('default/cargo-registry.json'))==872
assert len(ts)==13 and len(read('integration-policy.json'))==43
late=overlap=sibling=linked=0
for src,t in ts.items():
    a=t['default_tests'];b=t['disabled_test']
    assert len(a)==2 and len(b)==1 and a[0]['argv_sha256']==a[1]['argv_sha256']==t['default_argv_sha256']
    assert all(any(e['code']=='CLD_EXITED' and int(e['value'])==j['terminal']['result'] for e in j['sigchld']) for j in a+b)
    assert a[1]['terminal']['result']==b[0]['terminal']['result']==0
    w=t['default_wilds'];assert all(r['terminal']['result']==0 and r['own_rlib_exact_path'] for r in w+t['disabled_wild'])
    linked+=len(w);sibling+=bool(t['earlier_sibling_authoritative_wait'])
    bounds=t['bounds'];first=a[0];producer=t['own_producer']
    assert producer['terminal']['result']==0
    if first['terminal']['result']==0:
        assert len(w)==2 and bounds['producer_terminal_ns']<bounds['first_test_exec_ns']
        assert bounds['last_producer_raw_debug_end_received_ns']<bounds['producer_terminal_ns']
        assert bounds['artifact_arrival_ns']<bounds['earliest_test_scheduler_start_ns'];late+=1
    else:
        assert first['terminal']['result']==1 and bounds['first_test_exec_ns']<bounds['producer_terminal_ns'] and len(w)==1
        overlap+=1
assert (late,overlap,sibling,linked)==(12,1,3,25)
for line in (p/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1);assert h((p/name).read_bytes())==expected,name
print('Verified 619 units, 102 executables, 110 identical ELF files, 13 duplicate argv, 12 early tests after producer exit, 1 overlap, 21 accepted early.')
