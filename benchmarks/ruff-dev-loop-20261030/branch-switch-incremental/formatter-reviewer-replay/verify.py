"""Verify independently acquired source, tool, ELF, compiler error and test evidence."""
from pathlib import Path
import copy
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parent
DRIVER='b2a7780120821b363986bccb91646050d963a644d13ae354ffb87348cdb20e0c'
CARGO='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add'
WILD='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
A='b5dba861cc38e3f7fb4524c9ceba3e01a474ea13';B='7b13f01ba1569887a25670820764b24c206da8e5'
ELFS={'A':'f4adc9d02e7830adb6d2ff7670b8588cf645fd1a39863dbc0c8abba270becd52','B':'0252a7a7873113c21cb22c81c186a3583dd0064d16912a400532e27b4c0a7ca9'}
INVENTORY='e488cde8272f1fed5a70417e6f39032f0e1065c3dcd8d2b434fc4c5229256f9a'
TESTS=['tests::basic','tests::string_processing','comments::tests::parenthesized_expression']
DIRTY=['ruff_db','ruff_python_ast','ruff_python_formatter','ruff_python_parser']
ORDER=['empty-B','first-A','return-B','return-A','invalid-A','recovered-A','unchanged-A']
def h(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def valid(d):
    data=d['raw_readback'];initial=d['enrollment'];end=d['terminal'];primary=d['collector']
    assert end['exit']==0 and initial['replay_sha256']==primary['replay_sha256']==h(ROOT/'replay_one.py') and d['readback_sha256']==h(ROOT/'readback.py')
    assert isinstance(initial['registered_ns'],int) and end['ns']>initial['registered_ns'];assert re.fullmatch(r'[a-f0-9]{64}',initial['formal_terminal'])
    assert primary['qualification_only'] and primary['original_raw_sha256']==data['history_sha256'] and primary['source']=='6b7f424ece4bc978ead5546b73e1b31d5ccb1e70'
    assert data['identity']['driver']==primary['driver']==DRIVER and data['identity']['cargo']==primary['cargo']==CARGO and data['identity']['stock_wild']==primary['wild']==WILD
    assert primary['matched_empty_elves']==ELFS and {k:v['sha256'] for k,v in data['executables'].items()}==ELFS and all(v['bytes']>0 for v in data['executables'].values())
    assert data['revisions']=={'A':A,'B':B} and data['identity']['cpus']==[28,29,30,31] and data['identity']['source']=={A:'2b61306d708a211b3725c8d920e7590be6da41ad',B:'97ca36909f1ae8fa028b2c1f48f452fbdcdbbd4c'}
    assert [r['case'] for r in data['commands']]==ORDER and set(primary['builds'])==set(ORDER)
    listing=None
    for i,r in enumerate(data['commands']):
        case=r['case'];c=primary['builds'][case];key='B' if case in ('empty-B','return-B') else 'A'
        assert r['source']==(B if key=='B' else A) and c['exit']==r['exit']
        assert all(re.fullmatch(r'[0-9a-f]{64}',v) for v in r['raw_sha256'].values()) and {'cargo.json','cargo.stdout','cargo.stderr'}<=r['raw_sha256'].keys()
        if case=='invalid-A':
            assert r['exit']==101 and c['diagnostic']=='E0308' and r['native_error']=={'code':'E0308','file':'crates/ruff_python_formatter/src/lib.rs','line':410,'column':45};continue
        assert r['exit']==0 and r['artifacts']==216 and r['ELF']==ELFS[key]==c['ELF'] and r['inventory']==INVENTORY==c['inventory']
        assert sorted(r['test_names'])==r['test_names'] and len(r['test_names'])==len(set(r['test_names']))==53 and set(TESTS)<=set(r['test_names']) and r['exact_tests']==TESTS
        if listing is None:listing=r['test_names']
        assert listing==r['test_names'] and c['three_exact_tests'] and c['two_abi_controls'] and c['dirty']==r['dirty']
        if case.startswith('return'):assert r['dirty']==DIRTY
        if case.startswith('unchanged'):assert r['dirty']==[]
        for n in (64,56):
            good=n==(64 if key=='A' else 56);assert r['abi'][str(n)]=={'exit':0 if good else 1,'diagnostics':[] if good else ['E0308']}
            assert 'size-'+str(n)+'.stderr' in r['raw_sha256']
        if case=='empty-B':assert {k:r['suite'][k] for k in ('passed','failed','ignored')}=={'passed':51,'failed':0,'ignored':2} and r['suite']['stdout']==r['raw_sha256']['all-tests.stdout'] and primary['complete_suite']==[51,0,2]

def main():
    files={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'};listed={}
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        sha,name=line.split('  ',1);assert name in files and name not in listed and sha==h(ROOT/name);listed[name]=sha
    assert set(listed)==files
    d=json.loads((ROOT/'qualification.json').read_bytes());valid(d)
    for label,change in [('return ELF',lambda x:x['raw_readback']['commands'][2].update(ELF=ELFS['A'])),('invalid diagnostic',lambda x:x['raw_readback']['commands'][4]['native_error'].update(line=409)),('ABI negative',lambda x:x['raw_readback']['commands'][2]['abi']['64'].update(exit=0)),('unchanged root work',lambda x:x['raw_readback']['commands'][6]['dirty'].append('x'))]:
        bad=copy.deepcopy(d);change(bad)
        try:valid(bad)
        except AssertionError:continue
        raise AssertionError('Accepted '+label)
    print('Verified seven Cargo invocations, both clean ELFs, six 53-test inventories, 18 executed assertions, six accepted and six rejected ABI readers, E0308/repair, and four adversarial mutations.')
if __name__=='__main__':main()
