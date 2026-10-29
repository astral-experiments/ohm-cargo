#!/usr/bin/env python3
"""Verify the portable compiler, program and diagnostics ledger for the synchronized inputs."""
import collections
import hashlib
import json
import re
from pathlib import Path
r=Path(__file__).resolve().parent
read=lambda n:json.loads((r/n).read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def d(e):return e['structured_sha256']
def ok(x):return re.fullmatch('[0-9a-f]{64}',x) is not None
images=read('identity.json'); hist=read('histories.json');refs=read('protocols.json')
assert set(hist)==set(images)=={'A','B'}
assert refs['established']['commit']=='17c7526dc1e5582a2728bcae6ec7ab290610c721'
assert refs['synchronized']['commit']=='d94e602e0f3b0eb357e9a386e3fc27971727937b'
assert refs['fixed-reader']['commit']=='e41b8d460f8f2607e572587c01ec56708bb2ddb4'
assert sha(r/'typed-dso.py')=='f244a8affb28b11af4b89e4ceefde3cd65a615a28a1f02adb13fec91fde5d728'
roles={'A':'3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7','B':'51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9'}
common={'rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60','driver':'a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','rustdoc':'dc6501f27285e927df450d559108a1e5609fc11d266e628d4f1b27d416b84cef'}
expected=set()
for stamp in ('current','preserved'):
    for kind in ('tracked-file','include-bytes','include-str'):
        expected|={f'{training}-{kind}-{stamp}' for training in ('trained','first')}
    for kind in ('dso','rmeta'):
        expected|={f'{style}-{kind}-{stamp}' for style in ('known','first','conventional')}
    expected.add(f'typed-dso-{stamp}')
assert all(set(cases)==expected for cases in hist.values())
stats={}
cross={}
for role,cases in hist.items():
    i=images[role];assert i['release_archive']=='629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8' and i['images']==dict(common,cargo=roles[role])
    s=collections.Counter();cross[role]={}
    for label,h in cases.items():
        assert h['seen_before_swap']=='17' and h['before']!=h['after'] and ok(h['before']) and ok(h['after'])
        stamp=label.rsplit('-',1)[1]
        if h['inode_changed'] is not None:
            assert h['inode_changed'] and h['mtime_preserved']==(stamp=='preserved')
        else:assert label.startswith('known-rmeta-')
        if 'dso_sections' in h:
            assert h['same_rust_source'] and h['mapped_old_native_dso']
            for k,pair in h['dso_sections'].items():assert (pair[0]==pair[1])==(k!='.text')
            assert h['before_nbytes']==h['after_nbytes']
        if 'rmeta_roots' in h:
            x=h['rmeta_roots'];assert x['old']['stable_id']==x['new']['stable_id'] and x['old']['svh']!=x['new']['svh'] and x['old']['public_hash']!=x['new']['public_hash']
        if 'legacy_assertion_rejected' in h:
            assert label.startswith('known-rmeta-') and ok(h['legacy_assertion_rejected']);s['historical_assertion_stop']+=1
        phases=h['phases'];old='change' if 'change' in phases else 'initial';assert set(phases).issuperset((old,'repeat','again','clean'))
        assert len(phases)==(7 if label.startswith(('known-','trained-','typed-')) else 4)
        for name,p in phases.items():
            assert p['native']['cargo']==1 and p['raw_traces'] and all(ok(s) for s in [*p['raw_traces'],p['stdout'],p['stderr'],p['original_row']])
            assert p['native']['target_rustc']==1
            s['commands']+=1
            if p['errors']:
                assert p['exit']==101 and p['fresh'] is None and p['native']['target_rustc']==1
                for e in p['errors']:
                    assert ok(d(e))
                    if e['code']=='E0308':s['E0308']+=1
                    else:
                        assert name==old and 'colliding StableCrateId values' in e['message'];s['identity_refusal']+=1
            else:assert p['exit']==0 and p['fresh'] is False
            if 'reopened' in p:
                val=p['reopened'];assert val['sample']==p['value']==29 and val['exit']==0 and ok(val['elf']) and ok(val['stdout']);s['reopened']+=1
        takes_check=('rmeta' in label or label.startswith('typed-'))
        for phase in ('repeat','again','clean'):
            p=phases[phase]
            if takes_check:assert p['exit']==101 and [e['code'] for e in p['errors']]==['E0308'] and p['errors']==phases['clean']['errors']
            else:assert p['exit']==0 and p['value']==29
        if not takes_check:assert phases['again']['reopened']['stdout']==phases['clean']['reopened']['stdout']
        if label.startswith('typed-'):assert phases[old]['exit']==0
        elif 'rmeta' in label or label.startswith('conventional-'):assert phases[old]['exit']==101
        else:assert phases[old]['exit']==0 and phases[old]['value']==17
        cross[role][label]={k:[v['exit'],v['value'],v['fresh'],v['errors']] for k,v in phases.items()}
    assert s=={'commands':140,'E0308':24,'identity_refusal':8,'reopened':36,'historical_assertion_stop':2},s
    stats[role]=dict(s)
assert cross['A']==cross['B']
oracles=read('oracles.json')
texts=oracles['terminal_stdout'];shapes=oracles['structured_diagnostics']
assert all(hashlib.sha256(v.encode()).hexdigest()==k for k,v in texts.items())
assert all(hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()==k for k,v in shapes.items())
assert {v['reopened']['stdout'] for arm in hist.values() for h in arm.values() for v in h['phases'].values() if 'reopened' in v}==set(texts)
assert {e['structured_sha256'] for arm in hist.values() for h in arm.values() for v in h['phases'].values() for e in v['errors']}==set(shapes)
assert all('sample=29' in v.splitlines() for v in texts.values())
assert any(x['code']=='E0308' and any('expected' in (y.get('label') or '') and 'i16' in (y.get('label') or '') for y in x['spans']) for x in shapes.values())
print('52 histories, 280 real Cargo invocations, 72 independently reopened programs at 29, 48 E0308 checks, 16 recorded StableCrateId refusals, 4 retained historical reader rejections.')
