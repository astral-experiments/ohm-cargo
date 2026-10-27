import gzip,hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
def data(path):
    f=p/path
    if f.exists():return f.read_bytes()
    return gzip.decompress(Path(str(f)+'.gz').read_bytes())
def obj(path):return json.loads(data(path))
def lines(path):return [json.loads(x) for x in data(path).splitlines()]
sha=lambda b:hashlib.sha256(b).hexdigest()
listed=set();files={str(x.relative_to(p)) for x in p.rglob('*') if x.is_file() and x.name!='SHA256SUMS'}
for row in (p/'SHA256SUMS').read_text().splitlines():
    h,s=row.split('  ',1);assert s in files and s not in listed and h==sha((p/s).read_bytes());listed.add(s)
assert listed==files
driver='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
headers={'all':('b13e40456fbc350d83d8a68dd1f0a9ef7d8cff339ec03f42991b6830e7ca8e8c','8738be14814a2dad789dee6fb3ba1914'), 'empty':('9ef170ebfc6e0a62e047ba377512574eee99db2968453dee172aba387c5c18b1','4b38929971381640e894a8a9ecce65a0')}
h='4175462a3d5d2dd2d422d26af13a9c63'
cases=['native-private-hash-readback','native-source-ids-readback-v2','native-source-acquisition']
for case in cases:
    r=obj(case+'/results.json');probe=obj(case+'/probe.json');assert probe['driver']==driver
    done=obj(case+'/complete.json');assert done['instrumented'] and done['scored']==0 and done['results']==sha(data(case+'/results.json'))
    for mode,(ident,svh) in headers.items():
        v=r[mode];o=v['observed'];assert (v['driver'],v['output_rmeta'],v['output_private'])==(driver,ident,svh)
        assert o['frozen_map_entries']==67 and o['processed']+o['buffered']==(176753 if mode=='all' else 176769)
        assert svh.encode() in data(case+'/'+mode+'/rmeta.root.txt') and lines(case+'/'+mode+'/raw.jsonl')==[o]
        if case!=cases[0]:
            ids=v['source_ids']['stable_source_ids_le'];assert len(ids)==len(set(ids))==v['source_ids']['entries']==(20 if mode=='all' else 21)
            assert lines(case+'/'+mode+'/files.jsonl')==[v['source_ids']]
    if case!=cases[0]:
        a,b=(set(r[k]['source_ids']['stable_source_ids_le']) for k in ['all','empty']);assert b-a=={h} and not a-b
for mode in ['all','empty']:
    d=cases[-1]+'/'+mode;got=lines(d+'/acquire.jsonl');cov=obj(d+'/acquisition-coverage.json')
    assert cov['covered']==(20 if mode=='all' else 21) and not cov['missing']
    hot=[x for x in got if x['id']==h];assert cov['target']==hot and len(hot)==(0 if mode=='all' else 168)
    for x in hot:
        assert (x['file_name_tag'],x['prefix_hex'],x['length'])==(4,'30',1)
        assert x['frames'][1:3]==[['librustc_driver-774a793a844d5500.so','6a03835'],['librustc_driver-774a793a844d5500.so','6a036b5']]
        assert any('libget_size_derive2-' in file for file,_ in x['frames'])
s=obj('backtrace/symbols.json')
assert s['actual_driver']['sha256']==driver and s['actual_driver']['frames']['6a036b5']['symbol'].endswith('::ts_from_str')
assert s['proc_macro']['sha256']=='056eb80114e17f1b1c834813683c4efaa746d18bd1d88f4ac481fee1385c69d7' and any('TokenStream' in r['symbol'] and 'from_str' in r['symbol'] for r in s['proc_macro']['frames'].values())
assert not (p/'native-source-ids-readback/complete.json').exists()
print('Verified six full native parser diagnostic runs, exact uninstrumented metadata bytes, all sorted source IDs and the 168 cold parse observations.')
