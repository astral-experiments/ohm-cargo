"""Verify the complete projection and challenge three independent decision boundaries."""
from pathlib import Path
from collections import Counter, defaultdict
from copy import deepcopy
import gzip, hashlib, json, re, sys

root = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load(name):
    return json.loads(gzip.decompress((root/name).read_bytes()))

def check(wire, artifacts):
    subjects = json.loads((root/'subjects.json').read_bytes())
    en = subjects['enrollment']
    assert subjects['terminal']['lower_unchanged'] and en['source_clean']
    assert en['cargo'] == '967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9'
    assert en['wild'] == '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    assert subjects['terminal']['raw_tar_sha256'] == '94efdc55e4645d7554bd5ecb25d7ac4e7064e5e03812e9ed39f61ccf7f06d830'
    units = wire['units']
    for key, data in units.items():
        encoded = (json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
        assert sha(encoded) == key
    rows = wire['commands']
    assert len(rows) == 22 and len(units) == 396
    assert sum(len(r['artifact_rows']) for r in rows) == 8371
    assert sum(len(r['raw_trace_files']) for r in rows) == 2224
    order = 'BBTTBTBTBTTBTBTBTBBTBT'
    edited = {7, 8, 9, 10, 15, 16, 17, 18}
    visits = {7, 8, 11, 12, 15, 16, 19, 20}
    results = {
        ('B', False): (151043112,'8b1a5a8891f967496460d7265650454cd733b72215c827629561295e6956e97f'),
        ('B', True): (151042424,'654c387f46038be7c1e0dae45d489787bb9f5e5fe9422ea9070d88f1529dff46'),
        ('T', False): (151154904,'cf926a8dde39f2f2537a38890901b42d5eee55fb8bd41ed9aea1102adcfcc42a'),
        ('T', True): (151154248,'bef2a496a2f4d3367ed27fb90a41dc2b19568f4312833b9548915c21ac1e16f2'),
    }
    total = Counter()
    inputs = defaultdict(set)
    direct = artifacts['dependencies']
    harness = '3b678d4bc421444f66a14a5f154f229538ecfcbc5ffdb58ba6fc0878ba7420c0'
    testlist = (root/'test-list.txt').read_bytes()
    assert testlist.count(b': test\n') == 97 and testlist.endswith(b'97 tests, 0 benchmarks\n')
    assert all(k+b': test\n' in testlist for k in (b'check_input_from_argfile',b'missing_argfile_reports_error'))
    prior = results['B',False][1]
    for idx,(mode, r) in enumerate(zip(order,rows,strict=True),1):
        is_edit = idx in edited
        is_test = mode=='T'
        assert (r['selector'], r['source_kind'], r['source_sha256']) == (mode, 'edited' if is_edit else 'original', en['reversed' if is_edit else 'pristine'])
        assert r['label'].startswith(f'{idx:02}-')
        assert r['argv'] == ['cargo','+ohm',*(['test','--test','integration_test','--no-run'] if is_test else ['build','--bin','ruff']),'-p','ruff','--locked','--offline','--message-format=json']
        assert r['prior_elf']==prior
        assert (r['elf']['bytes'],r['elf']['sha256'])==results[mode,is_edit]
        prior = r['elf']['sha256']
        rows_here=[(units[k],fresh) for k,fresh in r['artifact_rows']]
        assert len(rows_here)==(388 if is_test else 373)
        assert len({k for k,_ in r['artifact_rows']}) == len(rows_here)
        assert {u['target'] for u,fr in rows_here if u['kind']==['test']}==({'integration_test'} if is_test else set())
        expected = (24,4) if idx==3 else (1,1) if idx in visits|{1} else (0,0)
        dirty = [u for u,fr in rows_here if not fr]
        assert len(dirty)==expected[0]
        if idx in visits|{1}:
            assert [(u['target'],u['kind'],u['features']) for u in dirty]==[('ruff',['bin'],[])]
        linter,=[u for u,fr in rows_here if u['target']=='ruff_linter' and u['kind']==['lib']]
        colored,=[u for u,fr in rows_here if u['target']=='colored' and u['kind']==['lib']]
        assert linter['features']==['clap','default']+(['test-rules'] if is_test else [])
        assert colored['features']==(['no-color']if is_test else [])
        events=r['native']
        counts=Counter(e['tool']for e in events)
        total.update(counts)
        assert (counts['rustc'],counts['wild'])==expected
        assert counts['cc']==counts['collect2']==counts['wild']
        assert all(e['full'] for e in events if e['tool']=='rustc')
        assert all(e['pid_trace'] in [v[1]for v in r['raw_trace_files'].values()] for e in events)
        roots=[e for e in events if e.get('crate')=='ruff' and e.get('crate_type')=='bin']
        assert len(roots)==int(bool(expected[0]))
        for e in roots:
            assert not e['harness'] and e['source']=='main.rs'
            assert e['metadata']==('ef49c64f5fcc8e79'if is_test else '782083eccc4b187f')
            assert e['argv_sha256']==('48a586409fbca6f5943d56865114e9a2b602d6e09f21c2e26dcc33b9422789c3' if is_test else '3fe5fe425d4de4e4a01502dd5ee6aa157f38e61b0e8f80a4e567431ffab3dde3')
            for name,filename in e['externs']:
                if name in {'colored','ruff','ruff_linter','ruff_workspace'}:
                    assert r['label'] in direct[filename]['observed_in']
                    inputs[mode].add(filename)
        c={t['name']:t for t in r['checks']}
        assert set(c)==({'missing-argfile','working-argfile','format','gated-rule'}|({'test-list','historical-test','valid-argfile-test'}if is_test else set()))
        for name,t in c.items():
            assert t['run_elf_sha256']==(harness if name in ('test-list','historical-test','valid-argfile-test')else prior)
            for stream in ('stdout','stderr'):assert t[stream+'_sha256']==r['raw'][name+'.'+stream]
        assert (c['missing-argfile']['exit'],c['missing-argfile']['verdict'])==((101,'panic') if is_edit else (2,'handled-argfile-error'))
        assert (c['gated-rule']['exit'],c['gated-rule']['verdict'])==((0,'documented-rule')if is_test else(2,'unknown-rule'))
        assert (c['working-argfile']['exit'],c['working-argfile']['verdict'])==(0,'ruff 0.17.0')
        assert (c['format']['exit'],c['format']['stdout_sha256'])==(0,sha(b'x = 1\n'))
        if is_test:
            assert r['harness']=={'bytes':150812488,'sha256':harness}
            assert (c['test-list']['exit'],c['test-list']['stdout_sha256'])==(0,sha(testlist))
            assert c['historical-test']['exit']==(101 if is_edit else 0)
            assert c['valid-argfile-test']['exit']==0
            for t in (c['historical-test'],c['valid-argfile-test']):
                assert t['trace_sha256']==r['raw'][t['name']+'.exec']
                assert [x['sha256']for x in t['children']if x['name']=='ruff']==[prior]
        else: assert r['harness'] is None
        assert all(x>24*2**30+192*2**20 for x in r['minimum_free_bytes'][:2])
    assert total=={'rustc':33,'cc':13,'collect2':13,'wild':13}
    assert len(inputs['B'])==len(inputs['T'])==8 and not inputs['B']&inputs['T']
    assert set(direct)==inputs['B']|inputs['T'] and len({v['sha256']for v in direct.values()})==16
    objects=[]
    for mode,key in [('ordinary','B'),('integration','T')]:
        family=artifacts['codegen'][mode]
        assert family['elf']==results[key,False][1]
        assert family['recipe']['size']==127635
        assert len(family['objects'])==22 and sum(o['size']for o in family['objects'])==294952
        objects.append({o['sha256']for o in family['objects']})
    assert artifacts['codegen']['ordinary']['recipe']['sha256']!=artifacts['codegen']['integration']['recipe']['sha256']
    assert not objects[0]&objects[1]
    return '22 Cargo commands, 8 necessary BIN compiler/link pairs, 12 wholly fresh, 97 tests inventoried and two exercised in all 11 test selections; 44 objects and 16 dependency files checked'

def main():
    if (root/'SHA256SUMS').exists():
        for line in (root/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1)
            assert Path(name).name==name and re.fullmatch('[0-9a-f]{64}',digest)
            assert sha((root/name).read_bytes())==digest
    wire=load('commands.json.gz')
    artifacts=load('artifacts.json.gz')
    print(check(wire,artifacts))
    if sys.argv[1:]==['--self-test']:
        for mutate in ('wrong-family','missing-wild','unchanged-child'):
            w=deepcopy(wire)
            if mutate=='wrong-family': w['commands'][7]['elf']=w['commands'][6]['elf']
            elif mutate=='missing-wild': w['commands'][6]['native']=[e for e in w['commands'][6]['native']if e['tool']!='wild']
            else: next(c for c in w['commands'][5]['checks']if c['name']=='historical-test')['children'][1]['sha256']='0'*64
            try:check(w,artifacts)
            except AssertionError:continue
            raise AssertionError('accepted '+mutate)
        print('rejected three counterfactual mutations')

if __name__=='__main__':main()
