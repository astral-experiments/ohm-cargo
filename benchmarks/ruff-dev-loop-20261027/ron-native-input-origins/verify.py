from pathlib import Path
import collections,hashlib,json
d=Path(__file__).resolve().parent
j=lambda f:json.loads((d/f).read_bytes());proof=j('verified.json');typed=j('inputs.json');mk=j('make-role-paths.json')
assert proof['actual_make_records']==mk and {x['exact_path_sha256'] for x in proof['input_roles']}==set(mk['C/cold/nested.d']['first_rule_real_path_sha256'])
assert sorted(x['exact_path_sha256'] for x in proof['input_roles'] if x['ordinary_first_make_prerequisite'])==mk['C/cold/ron.d']['first_rule_real_path_sha256']==mk['O/cold/ron.d']['first_rule_real_path_sha256']
assert sorted(x['exact_path_sha256'] for x in proof['input_roles'])==mk['B/first/ron.d']['first_rule_real_path_sha256']
assert [[r['scope'],r['exact_path_sha256'],'blake3',r['actual_blake3'],r['bytes']] for r in proof['input_roles']]==typed
assert dict(collections.Counter(x['role'] for x in proof['input_roles']))==proof['role_counts'] and sorted(proof['role_counts'].values())==[1,1,6,18,19]
assert sum(x['library_and_build_rust_sources_scanned'] for x in proof['registry_sources'].values())==130 and proof['inputs_exclusively_requiring_proc_macro_tracked_path']==0
print(json.dumps({'native_inputs':len(typed),'ordinary_inputs':19,'crate_store':26,'exclusively_proc_macro_tracked_path':0,'locked_rust_and_build_files_searched':130},sort_keys=True))
