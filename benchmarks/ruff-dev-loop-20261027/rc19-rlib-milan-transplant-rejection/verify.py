import hashlib,json
from pathlib import Path
r=json.loads((Path(__file__).resolve().parent/'initial.json').read_bytes())
assert r['cargo_exit']==0 and r['guard_exit']==1 and r['failed_assert']=='AssertionError: (248, 0, 248)'
assert r['stock_cargo_kernel_events']=={'cargo':1,'rustc-query':30,'rustc-full':252,'gcc':50,'collect2':50,'stock-wild':50}
assert r['actual_outputs_compared']==len(r['normalized_unit_rows'])==248 and all(len(v)==452 for v in r['path_sha256_file_sha256'].values())
roles=r['roles']
assert {v['id'] for v in roles.values()}=={258,260,261,262} or len({v['id']for v in roles.values()})==4
assert roles['imported']['context']=='320e0d0c58273350' and all(roles[k]['context']=='c125fcc98b3dd8b4' for k in ('H','P','rejected'))
assert roles['rejected']['fresh']==0 and roles['H']['fresh']==roles['P']['fresh']==roles['imported']['fresh']==248
assert r['scored_or_edit_commands']==0
for k,v in r['untimed_cold'].items():
 assert (v['cold_fresh'],v['repeat_fresh'],v['rows'],v['bytes'],v['caller_exit'])==(0,248,248,101719820,0)
 assert v['caller_stdout']==('1 SIM222\n'if k=='H' else'2 SIM222\n3 SIM222\n4 SIM222\n')
for n,a in r['sdk_file_stats']['original'].items():
 b=r['sdk_file_stats']['replacement'][n]
 assert a[0]==b[0] and a[4:]==b[4:] and a[1]!=b[1] and a[2]!=b[2] and a[3]!=b[3]
print('Transplanted command 0/248 fresh. Two independent local cold references and all underlying observations verified.')
