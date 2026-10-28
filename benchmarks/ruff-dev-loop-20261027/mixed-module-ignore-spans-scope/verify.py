import gzip,hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
x=json.loads(gzip.decompress((p/'controls.json.gz').read_bytes()))
for arm in ('fixed2','distributed'):
    a=x['fallback-screen'][arm]['cases']
    for n,fail in [('forced-ordinary-writer-moved-and-body',False),('forced-ordinary-writer-position-only',True),('forced-ordinary-writer-position-and-new-child',False),('ordinary-both-position-only',True),('current-flag-moved-and-body',True),('current-flag-position-only',True)]:
        r=a[n];assert [v['reader_status'] for v in r]==[0,101 if fail else 0,0]
        assert r[1]['reader_ice']==fail
    for nm in ('force-ordinary-writer','both-ordinary','request-both','default','disabled-no-ignore'):
        r=x['cargo-heterogeneous'][arm]['cases'][nm]
        fail=nm in ('force-ordinary-writer','both-ordinary')
        assert [v['status'] for v in r]==[0,101 if fail else 0,0]
        assert r[1]['ice']==fail
        assert [v['runtime'] for v in r]==['17',None if fail else '17','17']
        assert all({z['crate'] for z in v['rustc']}=={'input','reader'} for v in r)
    rs=x['position-diagnostic'][arm]['cases']['ordinary-both-position-only']
    assert [r['reader_status'] for r in rs]==[0,101,0]
    assert [r['fresh_error']['notes'][0]['location'][2] for r in rs]==[8,19,19]
    assert rs[0]['rmeta_sha256']!=rs[1]['rmeta_sha256']==rs[2]['rmeta_sha256']
r=x['position-diagnostic']['upstream']['cases']['ordinary-both-position-only']
assert [z['reader_status'] for z in r]==[0,0,0]
assert [z['fresh_error']['notes'][0]['location'][2] for z in r]==[8,8,19]
assert r[0]['rmeta_sha256']==r[1]['rmeta_sha256']!=r[2]['rmeta_sha256']
if (p/'SHA256SUMS').is_file():
    for line in (p/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1);assert h==hashlib.sha256((p/n).read_bytes()).hexdigest(),n
print('PASS: direct writer/reader, actual two-crate Cargo, upstream old declaration note')
