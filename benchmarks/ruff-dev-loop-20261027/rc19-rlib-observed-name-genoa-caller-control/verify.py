import hashlib,gzip,json
from pathlib import Path
p=Path(__file__).resolve().parent
def r(f):
 x=(p/f).read_bytes();return json.loads(gzip.decompress(x)if f.endswith('.gz')else x)
s=r('result.json');records=r('callers.json.gz');argv=r('compiler-argv.json.gz');raw=r('raw-bindings.json')
assert s['actual_callers']==s['actual_compilers']==3 and s['Cargo_runs']==s['stage_pairs']==0 and s['unscored'] and s['physical_source_pair_identical_by_bytes']
assert s['terminal']==raw['enrollment/complete.json']['sha256'] and s['enrollment']==raw['enrollment/registration.json']['sha256']
k=s['tests'];assert k==['earlier-copy-path','canonical-captured','canonical-reference']
d=[records[n]for n in k];v=[argv[n] for n in k];sha=lambda x:hashlib.sha256(x).hexdigest()
assert v[1]['full_rustc']==v[2]['full_rustc'] and v[1]['request']==v[2]['request'];changes=[i for i,(a,b)in enumerate(zip(v[0]['full_rustc'],v[1]['full_rustc'],strict=True)) if a!=b];assert changes==s['changed_arg_indices'] and len(changes)==1
expect=changes[0];assert [x['full_rustc'][expect]['arg'] for x in v]==['<copied-reader>/reader.rs','<original-reader>/reader.rs','<original-reader>/reader.rs']
assert len({x['cwd_sha256'] for x in d})==len({x['effective_env_sha256']for x in d})==len({x['logical_argv_root_sha256']for x in d})==1
assert all(vv['actual_reader_source']['sha256']==s['nominal_src']=='1b51d29cfcb474133d2c9a41f70295355c46f4ca1abd7111929f9a00317f058b' for vv in d) and [x['actual_reader_source']['path_bytes']for x in d]==[77,70,70]
assert d[0]['externs']==d[1]['externs'] and d[1]['externs']['ruff_python_ast']==d[2]['externs']['ruff_python_ast'] and d[1]['externs']['ruff_linter']['path_sha256']==d[2]['externs']['ruff_linter']['path_sha256'] and d[1]['externs']['ruff_linter']['sha256']!=d[2]['externs']['ruff_linter']['sha256']
assert [x['result']['executable']for x in d]==[s['rejected_original'],s['literal_gold'],s['literal_gold']] and s['rejected_original']!=s['literal_gold'] and all(x['raw_caller_compared_bytewise']for x in d)
assert all(x['all_source_inputs_readonly'] and x['result']['stdout']=='2 SIM222\n3 SIM222\n4 SIM222\n' and x['result']['exit']==x['compiler_root_exit']==0 and x['result']['stderr_sha256']==sha(b'') for x in d)
assert len({x['result']['input']for x in d})==1 and all(len(x['full_rustc'])==457 and len(x['request'])==458 for x in v)
assert [x['fixture_static_tests']for x in d]==[1,0,0]
for nm,x in zip(k,d):
 proc=x['events'];assert all(y['exit']==0 for y in proc) and 'cargo' not in {y['role'] for y in proc}
 rust,=[y for y in proc if y['role']=='rustc-full'];assert rust['raw_argv_sha256']==argv[nm]['effective_sha256']
 assert raw[nm+'/actual-request.argv']['sha256']==argv[nm]['request_sha256'] and raw[nm+'/emission/caller/lint-cli']['sha256']==x['result']['executable'] and raw[nm+'/runtime.stdout']['sha256']==sha(x['result']['stdout'].encode())
 if nm!='earlier-copy-path':
  assert [(i['role'],i['interpreted_image'])for i in proc]==[('probe','rustup'),('rustc-full','rustc'),('gcc','x86_64-linux-gnu-gcc-13'),('collect2','collect2'),('native-other','x86_64-linux-gnu-ld.bfd')]
  assert all(i['physical_path_captured_from_proc_exe'] for i in proc)
assert [r['image_sha256']for r in d[1]['events']]==[r['image_sha256']for r in d[2]['events']]
print('Three actual rustc builds and three native program executions passed independent whole-ELF comparison. One compiler argv element selects the reader spelling; the original-path current/reference pair has all 457 argv elements identical. Zero Cargo or timed comparisons.')
