"""Check native Cargo records, compiler invocations, emitted wire bytes and cross-consumers."""
from pathlib import Path
from itertools import product
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile

root=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda f:json.loads(f.read_bytes())
def extract(f,target):
    with tarfile.open(f,'r:gz') as stream:
        seen=set()
        for m in stream:
            assert m.isfile() and m.name not in seen and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
            seen.add(m.name)
        stream.extractall(target,filter='data')

def verify(temp):
    sealed=read(root/'portable-members.json')
    alias=sealed['alias'].encode()
    if len(sys.argv)==2:
        original=sys.argv[1].encode();assert sha(original)==sealed['private_registry_basename_sha256']
    for part in ('parent','candidate','workspace'):
        extract(root/(part+'.tar.gz'),temp)
    for name,rec in sealed['members'].items():
        data=(temp/name).read_bytes();assert sha(data)==rec['portable']
        assert data.count(alias)==rec['replacements']
        if rec['replacements']==0:assert rec['portable']==rec['original']
        if len(sys.argv)==2:assert sha(data.replace(alias,original))==rec['original']
    assert {f.relative_to(temp).as_posix() for f in temp.rglob('*') if f.is_file()}==set(sealed['members'])
    subjects={};out={}
    for arm,driver in [('parent','36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05'),('candidate','4a993e1f78e3ec0122771380eadbf58ed5d467c058d314381e523f1bbe78d955')]:
        base=temp/arm
        subject=read(base/'subject.json')
        assert subject['driver_sha256']==driver and subject['timings']==0
        assert subject['cargo_sha256']=='0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1' and subject['frontend_sha256']=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
        source=subject['historical_source']
        assert len(source['original'])==len(source['edited'])==3 and sum(v is None for v in source['edited'].values())==2
        rows=read(base/'results.json');warm=rows['warm'];cold=rows['empty']
        assert read(base/'complete.json')['results_sha256']==sealed['members'][arm+'/results.json']['original']
        assert (base/'execution/exit').read_text()=='0'
        for history,row in rows.items():
            record=base/'records'/history
            assert read(record/'result.json')==row
            assert read(record/'argv.json')==['cargo','+ohm','build','--locked','--offline','--message-format=json']
            assert read(record/'status.json')=={'rc':0}
            output=[json.loads(line) for line in (record/'stdout').read_bytes().splitlines()]
            assert output[-1]['reason']=='build-finished' and output[-1]['success']
            units=[i for i in output if i['reason']=='compiler-artifact']
            assert len(units)==row['units']==501
            events=read(record/'compiler-processes.json')
            assert [v['argv'] for v in events]==row['dirty_rustc_argv']
            assert all(re.fullmatch(r'exec\.\d+',v['pid']) and v['exe'].endswith('/bin/rustc') for v in events)
            assert [[r['package_id'],r['target']['name']] for r in units if not r['fresh']]==row['dirty_units']
            if history in ('fresh','warm-fresh','empty-fresh'):
                assert not events and all(r['fresh'] for r in units)
            if history in ('train','warm','empty'):
                assert len(row['externs'])==16 and row['parser'] in row['dirty_rustc_argv'] and '-Zlink-only' not in row['parser']
            if history in ('warm','empty'):
                assert all(r['fresh'] for r in units if r['target']['name'] in ('ruff_python_ast','get_size_derive2'))
                assert read(record/'parser-header/status.json')=={'rc':0}
                head=(record/'parser-header/stdout').read_bytes()
                for key,field in [('private','private hash '),('public','public_hash '),('stable','StableCrateId(')]:
                    assert (field+row['header'][key]).encode() in head
                raw=(record/'parser.rmeta').read_bytes()
                assert raw==(record/'archived.rmeta').read_bytes()
                subprocess.run(['objcopy','--dump-section','.rmeta='+str(temp/'extract'),str(record/'archived-metadata.o'),str(temp/'object')],check=True)
                assert raw==(temp/'extract').read_bytes() and sha(raw)==row['rmeta_sha256']==row['archived_raw_sha256']
                diag=record/'native-ruff'
                assert read(diag/'status.json')=={'rc':1} and (diag/'stderr').read_bytes()==b''
                assert (diag/'stdin').read_bytes()==b"t'first' b'second'\n"
                assert [r['message'] for r in read(diag/'stdout')]==['Bytes literal cannot be mixed with non-bytes literals']
                assert sha((diag/'stdout').read_bytes())==row['native_ruff_diagnostic_sha256']
        assert set(rows)=={'train','fresh','warm','empty','warm-fresh','empty-fresh'}
        for k in ('header','externs','parser','get_size_sha256','native_ruff_diagnostic_sha256'):assert warm[k]==cold[k]
        assert warm['get_size_sha256']==rows['train']['get_size_sha256']=='b4fdb51067de47fa7ba8a6139de59a52d3ff09e8bce1356844b597bba179c1f4'
        raw_equal=warm['rmeta_sha256']==cold['rmeta_sha256'];want=arm=='candidate'
        assert raw_equal==want and read(base/'raw-gate.json')==dict(raw_equal=want,eligible=want,header_equal=True,timed_commands=0)
        readers=base/'readers';cli='Bytes literal cannot be mixed with non-bytes literals at byte range 0..18'
        closed=read(base/'complete.json')
        for state,bridge in product(('warm','empty'),repeat=2):
            compiled=readers/(bridge+'-bridge')
            assert read(compiled/'status.json')=={'rc':0}
            d=readers/(state+'-caller-'+bridge)
            assert read(d/'status.json')==read(d/'native/status.json')=={'rc':0}
            assert (d/'native/stdout').read_text().strip()==cli and not (d/'native/stderr').read_bytes()
            assert closed['callers'][state+'/'+bridge]==dict(native_stdout=cli,bridge_sha256=(compiled/'sha256').read_text())
        assert closed['source_index']=='11a0dc43212bb03ceeaea3dbb731207f2ce325a1be6f0da275b6125dc64dfa69'
        lengths=[(base/'records'/n/'parser.rmeta').stat().st_size for n in ('warm','empty')]
        assert lengths[0]-lengths[1]==(0 if want else 74)
        out[arm]=dict(raw_bytes_retained_and_empty=lengths,identical=raw_equal,native_callers=4,source_commands=6,fresh_controls=3,raw_sha256=[warm['rmeta_sha256'],cold['rmeta_sha256']])
        subjects[arm]=(source,cold)
    assert subjects['parent'][0]==subjects['candidate'][0]
    cold=subjects['candidate'][1];other=subjects['parent'][1]
    changed=[n for n,v in cold['externs'].items() if v['sha256']!=other['externs'][n]['sha256']]
    return dict(arms=out,cross_compiler_different_direct_externs=sorted(changed),timed_commands=0)

def transitions(temp):
    temp.mkdir();extract(root/'up-down.tar.gz',temp)
    records=read(temp/'results.json');cross=read(temp/'cross-wire.json')
    assert sha((temp/'results.json').read_bytes())==read(temp/'complete.json')['results_sha256']
    for label,row in records.items():
        epoch=3 if label in ('old-prime','downgrade','downgrade-empty') else 4
        assert row['header_hex']==(b'RSIC'+epoch.to_bytes(2,'little')).hex()
        d=temp/label
        assert read(d/'status.json')['returncode']==0 and sha((d/'raw.rmeta').read_bytes())==row['raw_rmeta_sha256']
        assert row['attribute_and_plain_derive_executed']==(label!='future-warm')
        if label!='old-prime':
            assert read(temp/(label+'-caller')/'status.json')['returncode']==0
            assert read(temp/(label+'-native')/'status.json')['returncode']==0
            assert (temp/(label+'-native')/'stdout').read_text().strip()==row['observed'] and row['observed'].endswith(':379')
    for a,b in [('upgrade','upgrade-empty'),('future-warm','future-empty'),('downgrade','downgrade-empty')]:
        for k in ('raw_rmeta_sha256','observed'):assert records[a][k]==records[b][k]
    for n,r in cross.items():
        assert read(temp/n/'status.json')['returncode']==read(temp/(n+'-native')/'status.json')['returncode']==0
        assert (temp/(n+'-native')/'stdout').read_bytes()==b'8\n' and r['native']=='8'
    assert len(records)==7 and len(cross)==8 and len(list(temp.glob('*/status.json')))==36
    return dict(release_epochs=[3,4,3],accepted_wire_consumers=len(cross),native_transition_commands=36)

with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    result=verify(path);result['upgrade_and_downgrade']=transitions(path/'transition')
    print(json.dumps(result,sort_keys=True,indent=2))
