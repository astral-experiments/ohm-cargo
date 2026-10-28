"""Replay the lossless assertions from the portable child records."""
import collections, hashlib, json
from pathlib import Path
p=Path(__file__).resolve().parent
r=json.loads((p/'native.json').read_bytes())['records']; assert len(r)==22
for fork in ('default','no-fork'):
    rows=[r[f'job-{fork}-{t}-{m}'] for t in (0,3) for m in ('full','save')]
    zero,a,three,b=rows
    assert a['argv']==b['argv']==three['argv']==zero['argv'] and a['saved']==b['saved'] and a['saved_path_bytes_sha256']==b['saved_path_bytes_sha256']
    assert zero['return']==three['return']==42 and zero['after']!=three['after']
    assert (zero['rodata_entsize'],three['rodata_entsize'])==(0,8)
    assert (three['tokens_before'],three['tokens_after'],b['tokens_before'],b['tokens_after'])==(3,3,3,0)
versions=[r['version-'+stage+'-save'] for stage in ('valid','malformed','absent')]
assert all(v['saved']==versions[0]['saved'] and v['status']==0 and v['argv']==versions[0]['argv'] for v in versions)
assert [r['version-'+s+'-full']['status'] for s in ('valid','malformed','absent')]==[0,1,1]
assert 'Failed to parse version script' in r['version-malformed-full']['stderr'] and 'Failed to read script' in r['version-absent-full']['stderr']
assert [r['shadow-'+s+'-full']['return'] for s in ('lower','earlier')]==[41,83]
assert r['shadow-lower-save']['saved']!=r['shadow-earlier-save']['saved']
assert all(r['shadow-'+s+'-full']['status']==1 and r['shadow-'+s+'-save']['status']==0 for s in ('malformed','missing'))
w=json.loads((p/'wrapper.json').read_bytes()); assert len(w['records'])==8
for row in w['records']:
    assert not row['status'] and row['gcc_argv']==w['records'][0]['gcc_argv']
    if row['via']=='guard':
        assert collections.Counter(row['tokens_in'])==collections.Counter(row['tokens_out'])
        assert row['width']==len(row['tokens_in'])+1 and row['image_sha256']==w['ordinary_images'][str(row['width'])]
        assert '-plugin' in row['final_argv'] and any(a.startswith('-plugin-opt=-fresolution=') for a in row['final_argv'])
h=json.loads((p/'historical-e2e.json').read_bytes())
assert h['identity']==['ty_server','e2e',['test']] and h['input_bytes']==615586261 and h['input_file_count']==411
assert sorted(q['width'] for q in h['widths'])==list(range(1,17))
assert len(h['bodies'])==2 and len(set(q['raw_sha256'] for q in h['widths'] if q['width']>1))==1
assert all(q['status']==0 and q['raw_sha256'] in h['bodies'] for q in h['widths'])
print('PASS: 22 stock requests, 8 real GCC calls, 16 historical Ruff worker widths')
