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
pkg=read(root/'initial-install.json');asset=read(root/'release.json')['asset'];ref=read(root/'manifest.json')
assert asset['digest']=='sha256:'+pkg['package_sha256']=='sha256:bd17067e6ca3343050bf4c3c64bb1959b996479a82868d01fbec29c4c4f79bf4'
assert pkg['package_bytes']==asset['size']==359640412
assert sha(root/'hygiene-sites.py')=='605856ac0d151978f46100a0cec3de93625cad73c3d9557fcdd7432bbab648a2'
tools=read(ev/'tools.json');assert tools['cpu_affinity']==[28,29]
for name,key in [('cargo','cargo'),('rustc','rust')]:assert 'commit-hash: '+ref['sources'][key]['revision'] in pkg['versions'][name]
for proof,actual in [('cargo','cargo_sha256'),('driver','driver_sha256'),('frontend','frontend_sha256')]:assert pkg[proof]==tools[actual]
results=read(ev/'results.json');complete=read(ev/'complete.json')
assert complete['timings']==0 and complete['results_sha256']==sha(ev/'results.json') and set(results)=={'call','mixed','root','legacy'}
native=read(root/'native-digests.json');verified=set()
refs={'call':('#6','#9','373748..373780'),'mixed':('#7','#10','373749..373781'),'root':('#0','#0','373776..373786'),'legacy':('#9','#9','373748..373780')}
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
    affected=site in ('call','mixed')
    assert (sha(e/'warm/raw.rmeta')!=sha(e/'empty/raw.rmeta'))==affected
    assert (row['builds']['warm']['header']['private']!=row['builds']['empty']['header']['private'])==affected
    for own in ('warm','empty'):
        bridge=e/('bridge-'+own);args=read(bridge/'argv.json')
        assert status(bridge)==0 and args[:2]==['rustc','+ohm'] and '--extern' in args and not any(x.startswith('-Z') for x in args)
        b=str((bridge/'libbridge.rlib').relative_to(ev));assert native[b]['kind']=='archive';verified.add(b)
        for provider in ('warm','empty'):
            d=e/(own+'-caller-'+provider);v=row['readers'][own+'/from-'+provider]
            args=read(d/'argv.json');assert args[:2]==['rustc','+ohm'] and '--extern' in args and not any(x.startswith('-Z') for x in args)
            assert v['bridge_sha256']==native[site+'/bridge-'+provider+'/libbridge.rlib']['sha256'] and v['diagnostics_sha256']==sha(d/'stderr')
            fail=affected and own!=provider;assert v['compiler_status']==status(d)==int(fail)
            a=str((d/'app').relative_to(ev))
            if fail:
                assert 'error[E0460]' in (d/'stderr').read_text() and 'crate `test_unit` which `bridge` depends on' in (d/'stderr').read_text() and a not in native and v['runtime'] is None
            else:
                assert native[a]['kind']=='elf' and native[a]['size']>0;verified.add(a)
                assert status(d/'native')==0 and v['runtime']==(d/'native/stdout').read_text().strip()
                context=refs[site][own=='empty'];assert v['runtime']==f'8:{context} bytes({refs[site][2]})'
assert verified==set(native)
print('Verified the shipping compiler, 12 Cargo builds, eight ordinary bridges, 16 ordinary caller attempts, four E0460 diagnostics and 12 native program outputs.')
