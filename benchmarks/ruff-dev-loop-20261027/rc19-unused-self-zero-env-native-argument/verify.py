from pathlib import Path
import hashlib,gzip,json
s=Path(__file__).resolve().parent
for l in (s/'SHA256SUMS').read_text().splitlines():
 d,n=l.split('  ',1);assert hashlib.sha256((s/n).read_bytes()).hexdigest()==d,n
j=json.load(gzip.open(s/'native.json.gz'));assert len(j)==4
for name,arm in j.items():
 if name.startswith('default-dirs'):
  assert len(arm['archives'])>=2 and len(set(arm['archives'].values()))==1 and arm['all_native_absent_from_actual_L']
  for z in (arm['first'],arm['second']):assert z['status']==101 and z['build_scripts']==0 and z['rustc_has_dependency_dir'] and z['actual_rustc'] and z['actual_linker'] and not any(x['contains_either_private_dir'] for x in z['actual_linker'])
  continue
 a=list(arm['stages'].values());assert len(a)==9 and all(t['build_scripts']==0 for t in a);ld=lambda z:[x for x in z['processes'] if x['type']=='linker']
 assert all(x['early_ld_search']<x['late_ld_search'] and x['has_choice_flag'] for z in a for x in ld(z)) and a[0]['value']==a[1]['value']==a[8]['value']==17
 assert a[3]['value']==a[4]['value']==29 and a[4]['empty_at_start'] and a[7]['empty_at_start'] and a[6]['status']==a[7]['status']==101
 if arm['defaults_off']:assert a[2]['value']==29 and a[5]['status']==101 and ld(a[2]) and ld(a[5])
 else:assert a[2]['value']==17 and a[2]['elf']==a[0]['elf'] and a[5]['status']==0 and a[5]['elf']==a[3]['elf'] and not ld(a[2]) and not ld(a[5])
print('Verified no-environment GNU/native outcome on the Rust source argument and nonforwarding of both private Rust-only directory candidates, with 22 genuine Cargo commands.')
