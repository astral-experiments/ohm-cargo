"""Verify the changed inputs, raw Rust metadata, ordinary caller commands and native outputs."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(p):
    return json.loads(p.read_bytes())

def verify(folder):
    tools = load(folder/'tools.json')
    results = load(folder/'results.json')
    assert set(results) == {'track-before', 'track-after', 'span-after'}
    complete = load(folder/'complete.json')
    assert complete['results_sha256'] == sha(folder/'results.json') and complete['timings'] == 0
    outcome = {}
    for name, row in results.items():
        f = folder/name
        macro = (f/'maker.rs').read_text()
        observer = 'proc_macro::Span::call_site().source_text()' if name=='span-after' else 'proc_macro::tracked::path(&path)'
        assert (macro.index(observer) < macro.index('let parsed: TokenStream = text.parse()')) == (name=='track-before')
        assert (f/'training-input.txt').read_text() == '91' and (f/'edited-input.txt').read_text() == '379'
        src = (f/'unit-before.rs').read_text()
        assert src.replace('{ 7 }','{ 8 }') == (f/'unit-after.rs').read_text() and 'include_bytes!("../parse-input.txt")' in src
        shared=None
        for state in ('training','warm','empty'):
            path = f/state
            assert load(path/'argv.json') == ['cargo','+ohm','build','-p','test_unit','--locked','--offline','--message-format=json']
            assert load(path/'status.json')['returncode'] == load(path/'header/status.json')['returncode'] == 0
            msgs = [json.loads(line) for line in (path/'stdout').read_bytes().splitlines()]
            assert msgs[-1] == {'reason':'build-finished','success':True}
            units = {a['target']['name']:a['fresh'] for a in msgs if a['reason']=='compiler-artifact'}
            assert units == {'test_unit':False, 'macro_maker':state!='training'}
            saved = load(path/'result.json')
            assert saved['unit_fresh']==units and saved['rmeta_sha256']==sha(path/'raw.rmeta')
            if shared is not None: assert saved['proc_macro_sha256']==shared
            shared=saved['proc_macro_sha256']
            if state!='training': assert saved == row['builds'][state]
            assert saved['header']['private'] in (path/'header/stdout').read_text()
        actual = {}
        for own in ('warm','empty'):
            path = f/('bridge-'+own)
            assert load(path/'status.json')['returncode']==0
            argv=load(path/'argv.json')
            assert argv[:2]==['rustc','+ohm'] and '--extern' in argv and not any(arg.startswith('-Z') for arg in argv)
            for bridge in ('warm','empty'):
                path=f/(own+'-caller-'+bridge)
                argv=load(path/'argv.json')
                assert argv[:2]==['rustc','+ohm'] and '--extern' in argv and not any(arg.startswith('-Z') for arg in argv)
                key=own+'/from-'+bridge
                caller=row['readers'][key];status=load(path/'status.json')['returncode']
                assert caller['compiler_status']==status and sha(path/'stderr')==caller['diagnostics_sha256']
                if status==0:
                    result=(path/'native/stdout').read_text().strip()
                    assert load(path/'native/status.json')['returncode']==0 and result==caller['runtime']
                    assert re.fullmatch(r'8:#\d+ bytes\(\d+\.\.\d+\):379', result)
                    actual[key]=result
                else:
                    assert status==1 and bridge!=own and caller['runtime'] is None
                    err=(path/'stderr').read_text()
                    assert 'error[E0460]' in err and 'crate `test_unit` which `bridge` depends on' in err
                    actual[key]='E0460'
        outcome[name] = {'callers':actual,'metadata_equal':sha(f/'warm/raw.rmeta')==sha(f/'empty/raw.rmeta')}
    return {'driver':tools['driver_sha256'],'cargo':tools['cargo_sha256'],'cases':outcome}

if __name__=='__main__':
    summary = {p.name:verify(p) for p in sorted(root.glob('*-baseline'))}
    assert summary
    for group in ('shipping-baseline','parent-baseline'):
        if group in summary:
            assert all(x['metadata_equal'] and len(set(x['callers'].values()))==1 and 'E0460' not in x['callers'].values() for x in summary[group]['cases'].values())
    assert sha(root/'changed-input.py')=='e895739e87ee2f2481dc64ecd5237e39ad5772a3783a01dad62551c29e4f9da2'
    if (root/'results-summary.json').is_file(): assert load(root/'results-summary.json')==summary
    print(json.dumps(summary,indent=2,sort_keys=True))
