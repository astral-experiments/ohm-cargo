import hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parent
results=json.loads((r/'outcomes.json').read_bytes())
assert set(results)=={'released17','released18','released19','parent','fixed','fixed-on-19'}
expected_images={'released17':'4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','released18':'02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573','released19':'789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1','parent':'aa886cc519dd9f1cd97db76c52228dde1b25d08d3b367c067211aa42bc472add','fixed':'8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5'}
expected_images['fixed-on-19']=expected_images['fixed']
assert results['parent']['compiler']==results['fixed']['compiler']
assert results['released19']['compiler']==results['fixed-on-19']['compiler']
build=json.loads((r/'release-builds.json').read_bytes())
assert build['8dc33c9cc']['binary_sha256']==results['fixed']['cargo']
assert build['5394ce881']['binary_sha256']==results['parent']['cargo']
assert build['8dc33c9cc']['profile_sha256']==build['5394ce881']['profile_sha256']
n=0
for arm,run in results.items():
    bad=arm not in ('fixed','fixed-on-19')
    assert run['cargo']==expected_images[arm]
    assert set(run['cases'])=={'public-api','resolve','provenance','check-hint'}
    for case,rec in run['cases'].items():
        assert rec['case']==case and rec['cargo']==run['cargo'] and rec['compiler']==run['compiler']
        if case in ('resolve','public-api'):
            rows=rec['records']
            assert [x['value'] for x in rows]==[17,29,29]
            assert rec['sentinel_replaced']==rec['cache_symlink']==bad
            assert (rec['before_sha']!=rec['after_sha'])==bad and rec['inode_preserved']!=bad
        else:
            rows=rec['rows']
            assert [x['phase'] for x in rows]==['cold','during','before','repeat']
            assert [x['verdict'] for x in rows]==([17,29,31,31] if case=='provenance' else ['checked']*4)
            for x in rows:
                changed=bad and x['phase']=='during'
                assert x['changed']==x['record_is_symlink']==changed
                assert x['inode_preserved']!=changed and (x['prior']!=x['after'])==changed
        assert all(row['exit']==0 and len(row['stdout'])==len(row['stderr'])==64 for row in rows)
        assert all(fresh for name,fresh in rows[-1]['typed'])
        n+=len(rows)
assert n==84
print('84 actual Cargo commands and every generated-entry disposition verified')
