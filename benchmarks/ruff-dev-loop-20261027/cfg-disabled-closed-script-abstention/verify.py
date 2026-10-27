"""Offline verification of the selected, successful traced and unsuccessful ordinary link observations."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
if (p/'SHA256SUMS').is_file():
    for row in (p/'SHA256SUMS').read_text().splitlines():
        digest,name=row.split('  ',1);assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest,name
v=json.loads((p/'observations.json').read_bytes());assert v['selected_ELF_or_ar_or_closed_scripts']=={'libc.so':True,'libm.so':True,'libgcc_s.so':False}
assert hashlib.sha256((p/'parser.patch').read_bytes()).hexdigest()=='08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff'
for n,x in v['nested'].items():
    t=x['phases'];assert len(t)==6 and all(r['full']==['full'] and not r['fixed'] for r in t.values()),n
    for k,r in t.items():
        assert sum(f.startswith('api-') for f in r['wild'])==1,(n,k)
        if k=='earlier-member-now-invalid':
            assert r['rc']==101 and r['elf'] is None and len(r['errors'])==1 and 'linking with' in r['errors'][0]
        else:
            assert r['rc']==0 and len(r['elf'])==64 and r['tests'].strip()=='0 tests, 0 benchmarks'
            assert r['marker']==(['0000000000000097'] if k=='earlier-member-now-exists' else [])
    assert t['cold']['elf']==t['removed-earlier-member']['elf']!=t['earlier-member-now-exists']['elf']
w=v['workspace']
for phase,x in w.items():
    assert x['elf_count']==110 and x['roster']==w['seed']['roster'] and x['scope'].startswith('619-unit')
    assert len(x['api'])==2 and all(not r['fixed_certificate'] and r['list']=='0 tests, 0 benchmarks' for r in x['api'].values())
    msg=x['diagnostics']['parser'][0]['message'];assert msg==('Bytes literal cannot be mixed with non-bytes literals' if x['source']=='edited' else 'Cannot mix t-string literals with string or bytes literals')
    if phase in ['edit','restore','edit-again']:
        assert (x['full'],x['link_only'],x['total_rustc'],x['wild'])==(6,62,68,67)
        assert sorted((r[3],r[2],r[4]) for r in x['actual_API_rustc'])==[('ruff_wasm','full',False),('ty_wasm','full',False)]
        assert len(x['actual_API_wild'])==2 and all(r[2:] == [True,False] for r in x['actual_API_wild'])
    elif phase.startswith('fresh'):
        assert (x['dirty_count'],x['full'],x['link_only'],x['wild'])==(0,0,0,0)
    else:assert phase=='seed' and (x['full'],x['link_only'],x['wild'])==(1,50,50)
s=v['rejected_extra_synthetic_positive'];assert not s['root_certified'] and not s['fixed_width'] and not s['elapsed_scored']
print('Two 6-phase native controls, complete 619-unit edit/reversal/repeat and four all-fresh no-ops passed. No timing comparison.')
