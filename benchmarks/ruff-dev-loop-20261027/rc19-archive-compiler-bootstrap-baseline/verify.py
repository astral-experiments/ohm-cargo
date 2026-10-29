from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parent
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
rows=(p/'SHA256SUMS').read_text().splitlines(); expected={n:h for h,n in (r.split('  ',1) for r in rows)}
assert set(expected)=={f.name for f in p.iterdir() if f.is_file() and f.name!='SHA256SUMS'}
assert all(sha(p/n)==h for n,h in expected.items())
a=json.loads((p/'result.json').read_bytes()); ledger=json.loads((p/'raw-sha256.json').read_bytes()); std=json.loads((p/'standard-library.json').read_bytes())
assert a['compiler_commit']=='5cf1bf9cd196046897a7aeeaf128833d6a464dfe' and a['compiler_tree']=='47e23eb4bab742e271ca9a3cf1bbd583d5b4a640' and a['cargo_commit']=='235f9228651b74c591e6f62cae4c9b761448dd2d'
assert a['stage']==1 and (a['pgo'],a['bolt'],a['build_exit'],a['first_packaging_probe_exit'],a['final_packaging_exit'])==(False,False,0,127,0)
assert a['actual_uid']==1000 and a['root_owned_ancestors'] and a['build_upper_cap_bytes']==12*2**30 and a['reserve_abort'] is None
assert min(a['minimum_free'][k] for k in ['home','scratch'])>25*2**30 and a['minimum_free']['upper']>2**30
assert a['original_stock_wild_same_inode'] and a['actual_new_rustc_inodes_verified'] and a['all_private_mounts_detached'] and a['matching_loaded_driver_and_llvm']
assert a['terminal_raw_sha256']==ledger['reports/baseline-final.json'] and a['bootstrap_lower_verified_names']==85286
assert len(std)==a['std_file_count']==53 and any(k.startswith('libstd-') and k.endswith('.rlib') for k in std) and all(re.fullmatch('[a-f0-9]{64}',h) for h in std.values())
assert a['compiled_cache']['verified_frame'] and a['compiled_cache']['compressed_bytes']==1390947066
s=a['smoke']; keys=['full_rustcs','link_only_rustcs','actual_stock_wild','runtime']; assert [[s[n][k] for k in keys] for n in ['initial','edited','repeat']]==[[2,0,1,17],[1,1,1,29],[0,0,0,29]]
for n,r in s.items():
    assert r['exit']==0 and r['cargo_argv'][:3]==['cargo','+ohm','build']
    assert r['native']==(['cc','collect2','ld.bfd'] if n!='repeat' else [])
    assert len(r['artifacts'])==2 and all(v==(n=='repeat') for v in r['artifacts'].values())
    assert r['rlib_size']==6264 and any(k.endswith('.o') for k in r['ar_members'])
    assert all(r[k]==ledger['smoke-v1/raw/'+n+'/'+f] for k,f in [('trace_sha256','exec'),('stdout_sha256','stdout'),('stderr_sha256','stderr')])
for k in ['rlib_sha256','elf_sha256']:assert s['initial'][k]!=s['edited'][k]==s['repeat'][k]
print('PASS: clean stage1 identities, 53 std files, 3 ordinary Cargo phases, actual stock Wild 1/1/0, separately retained first packaging failure and compiled lower')
