"""Verify the observed successful compiles, unchanged certificate, positive symbol and negative link."""
import hashlib
import json
from pathlib import Path
r=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
obs=json.loads((r/'observations.json').read_bytes())
assert h(r/'probe.py')==obs['fixture_sha256'] and h(r/'tiny-guards-233a9.py')==obs['base_fixture_sha256']
arms=obs['arms'];assert set(arms)=={'baseline','a9b','a9c'}
assert len({a['rust'] for a in arms.values()})==len({a['wild'] for a in arms.values()})==1
for key in ('added_object_sha','system_script_sha','ordinary_fallback_sha'):
    assert len({a[key] for a in arms.values()})==1
assert arms['a9c']['ordinary_fallback_sha']==hashlib.sha256(b'!<arch>\n').hexdigest()
assert arms['a9c']['system_script_sha']==hashlib.sha256(b'INPUT ( x86_64-linux-gnu/librt.a )\n').hexdigest()
for arm,info in arms.items():
    ph=info['phases'];ref=ph['ordinary-or-reuse']
    assert ph['cold']['full']==ph['first-changed']['full']==['full'] and not ph['cold']['fixed']
    assert bool(ph['first-changed']['fixed'])==(arm!='baseline')
    for name,p in ph.items():
        rust=sorted(ev['crate'] for ev in p['physical'] if ev['role']=='rustc')
        assert rust==sorted(p['rustcs'])
        for role in ('cc','collect2','Wild'):
            assert sum(ev['role']==role for ev in p['physical'])==sum(v.startswith('api-') for v in p['wild'])
        assert all(len(ev['file_sha256'])==len(ev['exec_record_sha256'])==64 for ev in p['physical'])
    if arm!='a9c':
        added,invalid,removed=[ph[s] for s in ('earlier-member-now-exists','earlier-member-now-invalid','removed-earlier-member')]
        assert added['rc']==0 and added['marker']==['0000000000000097'] and added['elf']!=ref['elf']
        assert invalid['rc']==101 and any('__ohm_nested_input_no_such_file__' in ' '.join(z['evidence']) for z in invalid['unresolved_input_errors'])
        assert removed['rc']==0 and removed['marker']==[] and removed['elf']==ref['elf']
        assert all(p['full']==['full'] for p in (added,invalid,removed))
    else:
        assert ref['native_certificate']['fixed_worker'] and ref['includes_sdk_directory'] and not ref['includes_nested_directory']
        for n in ('ordinary-or-reuse','earlier-member-now-exists','earlier-member-now-invalid','removed-earlier-member'):
            z=ph[n];assert z['rc']==0 and z['elf']==ref['elf'] and z['marker']==[] and not z['full'] and not z['wild'] and z['rustcs']==['leaf']
            assert z['native_certificate']==ref['native_certificate'] and not z['unresolved_input_errors']
print('Verified all 18 native command records. Two ordinary controls added the new symbol, failed on an invalid input, and recovered. The candidate returned the old successful ELF throughout.')
