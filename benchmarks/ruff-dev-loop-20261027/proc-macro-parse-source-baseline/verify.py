"""Offline verifier for the natural Cargo builds and separately compiled ordinary Rust users."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
load=lambda f:json.loads(f.read_bytes())
fs={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
checked=set()
for row in (p/'SHA256SUMS').read_text().splitlines():
    h,n=row.split('  ',1);assert n in fs and n not in checked and sha(p/n)==h,n;checked.add(n)
assert fs==checked
driver={'r233':'dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f','r232':'051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518','shipped-r14':'97a8910a6d8a8ac54936f9373f7940525b2f46ec5f005421b3913a21d9a6fa9b'}
variants={'parse','programmatic','legacy'}
for tag in ('r233-basic','r232-basic','shipped-r14-basic','r233-native-span','r232-native-span'):
    d=p/tag/'evidence'; tool=load(d/'tools.json'); release=next(x for x in driver if tag.startswith(x+'-'));assert tool['driver_sha256']==driver[release]
    if release=='shipped-r14':
        assert tool['cargo_sha256']=='9be48c4b02669047975662348a3f134d0abcd247d70d13c55ab024f806320590' and tool['frontend_sha256']=='a63a2a6506be83dfd6cd853e9807897b120660c056a8774011d82396ef549b13'
    else:
        assert tool['cargo_sha256']=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'
    res=load(d/'results.json');assert set(res)==variants and load(d/'complete.json')['results_sha256']==sha(d/'results.json')
    binary_digests=load(p/tag/'product-digests.json')
    for case,values in res.items():
        at=d/case;assert (at/'unit-before.rs').read_text().replace('{ 7 }','{ 8 }')==(at/'unit-after.rs').read_text()
        headers={}
        for mode in ['training','warm','empty']:
            st=at/mode;r=load(st/'result.json');argv=load(st/'argv.json')
            assert argv[:2]==['cargo','+ohm'] and ('-Zohm-defaults=no' in argv)==(case=='legacy')
            assert load(st/'status.json')['returncode']==0
            assert r['rmeta_sha256']==sha(st/'raw.rmeta') and r['header']['private'] in (st/'header/stdout').read_text()
            assert (st/'header/argv.json').read_text().find('-Zls=root')!=-1
            if mode=='training':train=r;continue
            assert r==values['builds'][mode] and r['proc_macro_sha256']==train['proc_macro_sha256']
            assert r['unit_fresh']=={'macro_maker':True,'test_unit':False}
            headers[mode]=r['header']
        assert headers['warm']['stable']==headers['empty']['stable']
        assert (headers['warm']['private']!=headers['empty']['private'])==(case=='parse')
        if case=='parse' and tag.endswith('basic'):assert headers['warm']['public']==headers['empty']['public']
        native={}
        for own in ('warm','empty'):
            bridge=at/('bridge-'+own);assert load(bridge/'status.json')['returncode']==0 and 'public-api-hash' not in str(load(bridge/'argv.json'))
            for provider in ('warm','empty'):
                path=at/(own+'-caller-'+provider);r=values['readers'][own+'/from-'+provider];err=(path/'stderr').read_text();code=load(path/'status.json')['returncode']
                assert r['bridge_sha256']==binary_digests['evidence/'+case+'/bridge-'+provider+'/libbridge.rlib']['sha256']
                assert r['compiler_status']==code and r['diagnostics_sha256']==sha(path/'stderr')
                expect_fail=release=='r233' and case=='parse' and own!=provider
                assert (code!=0)==expect_fail
                if expect_fail:assert code==1 and 'error[E0460]' in err and 'crate `test_unit` which `bridge` depends on' in err
                else:
                    value=(path/'native/stdout').read_text().strip()
                    assert value==r['runtime'] and load(path/'native/status.json')['returncode']==0
                    if own==provider:native[own]=value
                    if tag.endswith('basic'):assert value=='8'
        if tag.endswith('native-span'):
            if case=='parse':
                assert native=={'warm':'8:#0 bytes(373862..373872)','empty':'8:#0 bytes(373864..373874)'}
            else:assert native['warm']==native['empty'] and native['warm'].startswith('8:#0 bytes(')
assert not (p/'historical-old-bridge-assert/evidence/complete.json').exists()
assert not (p/'invalid-initial-native-fixture/evidence/complete.json').exists()
print("Verified 45 ordinary Cargo builds, 30 ordinary bridges and 60 fresh external callers across five completed fixture/compiler combinations.")
