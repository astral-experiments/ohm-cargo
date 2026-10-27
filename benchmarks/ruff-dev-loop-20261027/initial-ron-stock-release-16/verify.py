"""Check the shipped release and the three untimed physical process and native output receipts."""
from pathlib import Path
import gzip,hashlib,json
p=Path(__file__).resolve().parent;o=json.loads(gzip.decompress((p/'receipts.json.gz').read_bytes()))
release=json.loads((p/'official.json').read_bytes());source=json.loads((p/'provenance.json').read_bytes());assert release['tag']==source['toolchain']=='ohm-1.99.0-16' and release['digest']=='957ca8144205008ddaee75ef35f9775b2e428271c6b044e38bbdd8196c6bbf3e'
assert o['release']['cargo_report']==o['version']['cargo'] and o['release']['rustc_report']==o['version']['rust']
assert o['release']['cargo']=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
assert o['release']['driver']=='c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4'
for idx,phase in enumerate(('cold','first','settled')):
    v=o['phases'][phase];r=v['summary'];q=r['processes'];assert v['status']['returncode']==0 and r['units']==619 and r['executables']==102 and len(v['native'])==r['native_files']==110
    assert (r['fresh'],len(q['full']),len(q['relink']),q['wild'],r['ron_checksums'])==[(0,636,0,200,0),(563,1,50,50,45),(619,0,0,0,45)][idx]
    assert sum(x[1] for x in v['physical_linkers'])==q['wild'] and sum(not x[1] for x in v['physical_linkers'])==q['system']
    assert r['ron_marker'] and r['ron_complete']==(idx!=0)
    if idx==1:assert q['full']==['ron']
assert o['phases']['first']['native']==o['phases']['settled']['native'] and o['oracle']['passed']
print('Official unmodified 1.99.0-16: 636/1/0 full rustc, 0/50/0 link-only, 200/50/0 bundled Wild.')
