"""Verify the two source-test results, each additional native verdict and the Ohm source audit."""
from pathlib import Path
import hashlib,json

root=Path(__file__).resolve().parent
def load(name):return json.loads((root/name).read_bytes())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lines=(root/'SHA256SUMS').read_text().splitlines();files={}
for line in lines:
    sha,name=line.split('  ',1);p=root/name
    assert p.resolve().is_relative_to(root) and not p.is_symlink() and name not in files and digest(p)==sha
    files[name]=sha
assert set(files)=={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
stack=load('stack.json');build=load('cargo-build.json');tests=load('checked-in-tests.json');up=load('upstream.json')
assert (up['branches'],up['prs'],up['commits'],up['source_tips'],up['distinct_fingerprint_blobs'])==(293,237,297,284,74)
assert set(up['matching_prs'])=={282,283,284} and not any(v['collection'] for v in up['blob_evidence'].values())
assert all('collect_relink_cache' not in '\n'.join(lines) for v in up['blob_evidence'].values() for _,lines in v['salted'])
assert build['commit']==stack['qualified_root'] and build['parent']==stack['original']['282'] and build['ordered_externs']==239 and build['linker_inputs']==335
assert tests['source_files']==3108 and tests['inventory_length']==4821 and tests['initial_mount']['cargo_launches']==0
old,new=tests['old'],tests['fixed'];case='freshness::changing_relink_cache_collection_rebuilds_the_binary';guard='freshness::dependency_edit_reassembles_native_targets_by_default'
assert old['suite']==new['suite']==tests['source_suite_sha256'] and old['cargo']==build['parent_binary'] and new['cargo']==build['binary_sha256']
assert old['actual_cargo_execs']==3 and old['exit']==101 and old['test_cases']==[[case,'FAILED']]
assert any('left: ""' in l for l in old['log']) and any('right: "compile:app\\n"' in l for l in old['log'])
assert new['actual_cargo_execs']==10 and new['exit']==0 and set(map(tuple,new['test_cases']))=={(case,'ok'),(guard,'ok')}
srcs={p.relative_to(root/'fixture').as_posix():digest(p) for p in (root/'fixture').rglob('*') if p.is_file()}
controls=load('additional-error-controls.json');assert set(controls)=={'released-19','original-284'}
for name,arm in controls.items():
    rows=arm['rows'];m={(r['arm'],r['label']):r for r in rows};assert len(m)==len(rows)==(17 if name=='released-19' else 16) and arm['sources']==srcs
    errors=m['empty','no']['errors'];assert errors==[['link recipe was not requested',[['consumer/src/main.rs',1,28]]]]
    for r in rows:
        if r['exit']==0:assert r['runtime']=='17' and not r['errors']
        else:assert r['exit']==101 and r['root_rustc']==1 and r['root_emit']==[False] and r['errors']==errors
    for key in ('switch','switch-repeat'):
        assert m['implicit',key]['exit']==0 and m['implicit',key]['root_rustc']==0
        assert m['explicit',key]['exit']==(0 if name=='released-19' else 101)
    ev=m['implicit','evict-cargo-fingerprint'];assert ev['evicted'] and ev['exit']==101 and ev['errors']==errors
    assert m['implicit','restore']['root_emit']==[True] and m['implicit','restore-repeat']['root_rustc']==0
print('Verified both checked-in regression tests, 33 independent old compiler verdicts, and 297 Ohm branch/PR source heads.')
