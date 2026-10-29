from pathlib import Path
import json,hashlib
p=Path(__file__).resolve().parent
for line in (p/'SHA256SUMS').read_text().splitlines():
    h,n=line.split('  ',1);assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
x=json.loads((p/'result.json').read_bytes());name='compiler::relink_cache_tests::relink_manifest_reads_and_writes_do_not_follow_a_final_symlink'
cases=x['cases']
assert cases['red-regression']['tests']=={name:'FAILED'} and cases['red-regression']['exit']==101
assert cases['green-relink-cache']['tests'][name]=='ok'
for name in ('green-relink-cache','green-atomic-utility'):
    y=cases[name];assert y['exit']==0 and y['summary'][0]==len(y['tests']) and set(y['tests'].values())=={'ok'}
assert {y.rsplit('::',1)[-1] for y in cases['green-atomic-utility']['tests']}=={'write_atomic_works','write_atomic_permissions','write_atomic_symlink'}
old,new=[x['red_victim'][k] for k in ('original','overwritten')]
assert old['unused_extern_names']==['unused'] and 'unused_extern_names' not in new
assert old['input_checksum']==new['input_checksum'] and old['proof_checksum']!=new['proof_checksum']
binary=x['fixed_binary'];assert binary['source_fixed'] in binary['version'] and 'ohm-defaults' in binary['active_features'] and binary['noninstrumented']
assert hashlib.sha256((p/'parent-regression-test-only.patch').read_bytes()).hexdigest()==x['source']['red_test_diff']
print('Parent changed the victim. Fixed program and adjacent unit-test evidence verified.')
