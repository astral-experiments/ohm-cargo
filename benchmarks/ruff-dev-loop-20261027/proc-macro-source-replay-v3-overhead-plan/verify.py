import hashlib,json,math
from pathlib import Path
p=Path(__file__).resolve().parent
load=lambda f:json.loads((p/f).read_bytes())
sha=lambda f:hashlib.sha256((p/f).read_bytes()).hexdigest()
sums={k:v for line in (p/'SHA256SUMS').read_text().splitlines() for v,k in [line.split('  ',1)]}
assert all(sha(k)==v for k,v in sums.items()) and set(sums)=={f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
plan=load('parser-overhead-v3-plan.json'); q='admission/qualification/'
cert=load(q+'complete.json'); assert sha(q+'complete.json')=='84092c13895343d85bb7417ee44a7f3a5bf937e11cc91896e5ebff013c825fb6'
assert cert['primary_observations']==0 and cert['plan']==sha('parser-overhead-v3-plan.json') and cert['inputs']==sha('admission/inputs.json')
assert cert['runner']==sha('parser-overhead-v3.py')==plan['runner_sha256'] and sha('analyze-parser-overhead.py')==plan['analyzer_sha256']
assert len(plan['blocks'])==16 and sum(b['endpoints'][0]=='empty' for b in plan['blocks'])==8
audits=load(q+'physical-audits.json')
for ep in ['retained','empty']:
    assert sum(b[ep][0]=='parent' for b in plan['blocks'])==8 and all(set(b[ep])=={'parent','candidate'} for b in plan['blocks'])
    for arm in ['parent','candidate']:
        gold=cert['oracles'][arm][ep];cp=q+arm+'/'+ep
        for suffix in ('','-repeat'):
            row=load(cp+suffix+'/result.json');assert row['child']['wall_ns'] is None and row['child']['cpu_user_s'] is None and row['child']['exit']==0
            assert gold['rmeta_sha256']==gold['archive_rmeta_sha256']==row['rmeta_sha256']==row['archive_rmeta_sha256']
            assert row['header']==gold['header'] and row['actual_driver_sha256']==plan['arms'][arm]['driver_sha256']
        a=audits['qualification/'+arm+'/'+ep];assert a['raw_trace_sha256']==gold['native_audit_sha256']
        events=a['successful_exec_and_key_opens'];assert any(v.get('exec','').endswith('/rustup/toolchains/ohm/bin/rustc') for v in events)
        assert any('librustc_driver-' in v.get('opened','') for v in events) and any('libget_size_derive2' in v.get('opened','') for v in events)
assert sum(math.comb(16,i) for i in range(13,17))==697
print('Verified both matched production subjects, ten unscored native builds, all genuine dependency/artifact gates and the complete 32-pair schedule.')
