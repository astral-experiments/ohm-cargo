"""Verify the packaged toolchain, all Cargo and Rust invocations, raw metadata and native results."""
from pathlib import Path
import hashlib
import json
import re

root=Path(__file__).resolve().parent
ev=root/'evidence'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def read(f):return json.loads(f.read_bytes())
def status(d):return read(d/'status.json')['returncode']
enrolled=read(ev/'enrolled.json')
tools=read(ev/'tools.json')
assert tools['cpu_affinity']==enrolled['affinity']==[28,29]
assert sha(root/'hygiene-sites.py')==enrolled['fixture_sha256']=='605856ac0d151978f46100a0cec3de93625cad73c3d9557fcdd7432bbab648a2'
assert tools['driver_sha256']==enrolled['driver_sha256']=='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05'
assert tools['cargo_sha256']==enrolled['cargo_sha256']=='dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1'
assert tools['frontend_sha256']=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
ship=read(root/'shipping-results.json')
assert sha(root/'shipping-results.json')=='d6134e34ac7ef1b04c465f74e7191c985996abe17a5fb77ea92cdb7a350fe198'
assert read(root/'initial-install.json')['package_sha256']=='bd17067e6ca3343050bf4c3c64bb1959b996479a82868d01fbec29c4c4f79bf4'
results=read(ev/'results.json');complete=read(ev/'complete.json')
assert complete['timings']==0 and complete['results_sha256']==sha(ev/'results.json') and set(results)=={'call','mixed','root','legacy'}
native=read(root/'native-digests.json');verified=set()
refs={'call':('#9','#9','373748..373780'),'mixed':('#10','#10','373749..373781'),'root':('#0','#0','373776..373786'),'legacy':('#9','#9','373748..373780')}
for site,row in results.items():
    e=ev/site;maker=(e/'maker.rs').read_text()
    assert 'TokenStream::new()' in maker and '.parse' not in maker and 'from_str' not in maker
    if site in ('call','legacy'):assert 'proc_macro::Span::call_site()' in maker
    if site=='mixed':assert 'proc_macro::Span::mixed_site()' in maker
    if site=='root':assert 't.into_iter().next().unwrap().span()' in maker
    assert (e/'unit-before.rs').read_text().replace('{ 7 }','{ 8 }')==(e/'unit-after.rs').read_text()
    plugin=[]
    for mode in ('training','warm','empty'):
        d=e/mode;cfg=['-Zohm-defaults=no'] if site=='legacy' else []
        assert read(d/'argv.json')==['cargo','+ohm',*cfg,'build','-p','test_unit','--locked','--offline','--message-format=json']
        assert status(d)==status(d/'header')==0
        msgs=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()]
        assert msgs[-1]=={'reason':'build-finished','success':True}
        units={a['target']['name']:a['fresh'] for a in msgs if a['reason']=='compiler-artifact'}
        assert units=={'test_unit':False,'macro_maker':mode!='training'}
        out=read(d/'result.json');plugin.append(out['proc_macro_sha256'])
        assert out['rmeta_sha256']==sha(d/'raw.rmeta') and out['unit_fresh']==units
        assert out['header']['private'] in (d/'header/stdout').read_text()
        if mode!='training':assert out==row['builds'][mode]
    assert len(set(plugin))==1
    assert (e/'warm/raw.rmeta').read_bytes()==(e/'empty/raw.rmeta').read_bytes()
    assert row['builds']['warm']['header']==row['builds']['empty']['header']
    old=ship[site]['readers']
    assert all(v['compiler_status']==int(site in ('call','mixed') and pair.split('/from-')[0]!=pair.split('/from-')[1]) for pair,v in old.items())
    for own in ('warm','empty'):
        bridge=e/('bridge-'+own);args=read(bridge/'argv.json')
        assert status(bridge)==0 and args[:2]==['rustc','+ohm'] and '--extern' in args and not any(x.startswith('-Z') for x in args)
        b=str((bridge/'libbridge.rlib').relative_to(ev));assert native[b]['kind']=='archive';verified.add(b)
        for provider in ('warm','empty'):
            d=e/(own+'-caller-'+provider);v=row['readers'][own+'/from-'+provider]
            args=read(d/'argv.json');assert args[:2]==['rustc','+ohm'] and '--extern' in args and not any(x.startswith('-Z') for x in args)
            assert v['bridge_sha256']==native[site+'/bridge-'+provider+'/libbridge.rlib']['sha256'] and v['diagnostics_sha256']==sha(d/'stderr')
            assert v['compiler_status']==status(d)==0
            a=str((d/'app').relative_to(ev))
            assert native[a]['kind']=='elf' and native[a]['size']>0
            verified.add(a)
            assert status(d/'native')==0 and v['runtime']==(d/'native/stdout').read_text().strip()
            assert v['runtime']==f'8:{refs[site][0]} bytes({refs[site][2]})'
            assert v['runtime']==old['empty/from-empty']['runtime']
            if site=='call':assert v['runtime']==ship['legacy']['readers']['warm/from-warm']['runtime']
assert verified==set(native)
print('Verified 12 Cargo builds, eight ordinary bridges, sixteen ordinary clients and sixteen executed ELFs. All warm/empty raw metadata matches. Clean shipping native output matches for each input.')
