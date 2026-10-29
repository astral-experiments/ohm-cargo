from pathlib import Path
import gzip
import hashlib
import json

p=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
for line in (p/'SHA256SUMS').read_text().splitlines():
    h,n=line.split('  ',1);assert sha((p/n).read_bytes())==h,n
plan=json.loads((p/'plan.json').read_bytes())
admit=json.loads((p/'admission.json').read_bytes())
final=json.loads((p/'terminal.json').read_bytes())
data=json.loads(gzip.decompress((p/'observations.json.gz').read_bytes()))
assert admit['plan']==sha((p/'plan.json').read_bytes()) and final['admission']==sha((p/'admission.json').read_bytes())
assert sha((p/'reproduce.py').read_bytes())==plan['driver']
assert set(data)==set(final['cases'])=={c['name'] for c in plan['cases']}
assert len(data)==8
def reader(row):
    return [r for r in row['processes'] if r.get('unit')=='reader']
def opens(row,missing=False):
    return [o for o in row['asset_opens'] if o['nearest_compiler']=='reader' and (o['missing'] if missing else o['open_successful'])]
def linker(row):return [r for r in row['processes'] if r['type']=='linker']
def one_test(row):assert row['status']==0 and len(row['test_stdout_sha'])==64 and len(row['elf'])==64
def full(row,inc):
    compilers=reader(row);assert compilers and all(not r['link_only'] and r['incremental']==bool(inc) for r in compilers)
def zero(row):assert row['processes']==[] and row['asset_opens']==[]
totals=0
for cfg in plan['cases']:
    rec=data[cfg['name']];t=rec['terminal']
    assert sha((json.dumps(t,indent=2,sort_keys=True)+'\n').encode())==final['cases'][cfg['name']]
    assert t['cargo']==cfg['cargo'] and t['defaults_off']==cfg['defaults_off'] and t['incremental']==cfg['incremental'] and t['relationship']==cfg['relationship']
    phases={r['phase']:r for r in rec['phases']};assert set(phases)==set(t['phases'])
    inc=cfg['incremental'];on=not cfg['defaults_off'];used=cfg['relationship']=='used-private';base_rust=6 if used else 0;edited_rust=10 if used else 0
    assert len(phases)==9+inc;totals+=len(phases)
    cold=phases['01-cold'];no=phases['02-unchanged'];edit=phases['03-edit-and-new-asset'];clean=phases['04-independent-clean'];force=phases['05-forced-full-keep-incremental'];bad=phases['07-source-restore-missing-asset'];empty_bad=phases['08-independent-missing'];forced_bad=phases['09-forced-same-missing'];restore=phases['10-recovered']
    for x in (cold,no,edit,clean,force,restore):one_test(x)
    for x in phases.values():
        assert x['expected_incremental']==inc and any(k=='stdout' for k in x['raw']) and any(k.startswith('trace.') for k in x['raw'])
        assert all(isinstance(y['mentions_payload'],bool) for y in x['depinfo'].values())
    assert cold['empty'] and clean['empty'] and empty_bad['empty'] and not edit['empty']
    full(cold,inc);full(clean,inc);full(force,inc);full(empty_bad,inc);full(forced_bad,inc)
    assert opens(cold) and opens(clean) and opens(empty_bad,True) and opens(forced_bad,True)
    assert len(linker(clean))==1 and len(linker(cold))==1 and not linker(empty_bad) and not linker(forced_bad)
    zero(no)
    assert cold['native']==no['native']==restore['native']==17 and cold['rust']==no['rust']==restore['rust']==base_rust
    assert no['elf']==cold['elf'] and clean['native']==29 and clean['rust']==edited_rust==edit['rust']
    assert clean['asset']==edit['asset']==sha(bytes([29])) and cold['asset']==restore['asset']==sha(bytes([17])) and bad['asset'] is None
    assert empty_bad['status']==forced_bad['status']==101 and empty_bad['diagnostic_mentions_incbin'] and forced_bad['diagnostic_mentions_incbin']
    if inc:
        fix=phases['06-forced-full-evacuated-incremental'];one_test(fix);full(fix,inc);assert opens(fix) and fix['native']==29
    else:assert opens(force) and force['native']==29
    if cfg['defaults_off']:
        full(edit,inc);full(bad,inc)
    assert len([z for r in phases.values() for z in r['depinfo'].values()])>0
    assert all(not d['mentions_payload'] and d['mentions_reader_source'] for r in phases.values() for d in r['depinfo'].values())
    tool_prefix='0d633580' if on else 'e9ceb054'
    assert all(z['exe'].startswith(tool_prefix) for r in phases.values() for z in linker(r))
    assert all(z['exe'].startswith('fa2ed3ec') for r in phases.values() for z in r['processes'] if z['type']=='rustc')
    if on:
        assert cold['unused']==([] if used else ['assembler_reader'])
        assert edit['native']==17 and not opens(edit) and bad['status']==0 and bad['native']==29 and not opens(bad,True)
        if cfg['role']=='native-guard-parent' and not used:
            assert reader(edit)==linker(edit)==reader(bad)==linker(bad)==[]
        else:
            assert len(linker(edit))==len(linker(bad))==1 and all(len(reader(q))==1 and reader(q)[0]['link_only'] for q in (edit,bad))
    elif inc:
        assert edit['native']==force['native']==17 and bad['status']==0 and bad['native']==29 and not opens(edit) and not opens(bad,True)
    else:
        assert edit['native']==force['native']==29 and opens(edit) and bad['status']==101 and opens(bad,True)
    print(cfg['name'],'changed',edit.get('native'),[r['link_only'] for r in reader(edit)],'opens',len(opens(edit)),'forced',force['native'],'missing',bad['status'],'clean',clean['native'],empty_bad['status'])
print('Replayed',totals,'ordinary Cargo commands, eight independent settings, and all retained compiler/linker/acquisition/digest checks.')
