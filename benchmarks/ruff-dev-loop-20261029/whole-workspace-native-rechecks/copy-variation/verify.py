#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
p=Path(__file__).parent/'excluded-v1.json'
assert hashlib.sha256(p.read_bytes()).hexdigest()=='7e987e79b6eae15a52129d57cf7d5a7411c5a6ead4800c2fb4199ae96ac0f35f'
r=json.loads(p.read_bytes())
assert r['primary_three_arm']=='35171c6a4565a7b9f9535f4993aa015971de2914329e8a6067e506bf37fe0551' and r['plan']=='3154f5aa914d48aa4500b97a48a5fb0fc74626eeff5e27e3f9fd37bcccbba604' and r['workspace_provider_present_before_or_during'] is False
assert r['copied_members']==45543 and r['copied_unique_files']==34692 and r['internal_hardlink_groups']==4398 and not r['source_and_copy_shared_inodes']
a,b=[r['proof'][k] for k in ('00-baseline-one','01-baseline-two')]
assert a['full']==119 and b['full']==127 and not a['physical_extras']
for c in (a,b):
 assert (c['typed'],c['fresh'],c['cached'])==(619,433,0) and c['gcc_collect2_wild']=={'gcc':103,'collect2':103,'wild':103} and c['fixed50_original_ELF_and_listing'] and c['all_three_output_multisets_match']
 for name in ('cargo_stderr','cargo_stdout','jobs','case'):assert re.fullmatch('[a-f0-9]{64}',c[name])
extra=b['physical_extras']
assert sorted(e['crate'] for e in extra)==sorted(['cachedir','assert_fs','ruff','insta','insta_cmd','mdtest','ty_test','ruff_mdtest'])
assert len({e['unit'] for e in extra})==len({e['physical_argv'] for e in extra})==8 and all(e['emits']=='--emit=dep-info,metadata,link' for e in extra)
print('Verified the two initial Cargo invocations, eight additional nonlinking library compilers, 103 stock links and zero workspace provider observations.')
