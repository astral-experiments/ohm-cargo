"""Verify source and release identities, observed marker contents, native work, and both test controls."""
from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def read(f):return json.loads((p/f).read_bytes())
def H(b):return hashlib.sha256(b).hexdigest()
lines=(p/'SHA256SUMS').read_text().splitlines()
names=set()
for line in lines:
 d,k=line.split('  ',1)
 assert k not in names and not Path(k).is_absolute() and '..' not in Path(k).parts and sha(p/k)==d,k
 names.add(k)
assert names=={str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and f.name!='SHA256SUMS'}
assert sha(p/'fix.patch')=='7e2e16dc6bb0ad18be9eca7b35c57f4799f4d990f0b0ad4bddd441a0b9c63d4a'
assert sha(p/'reproduce.py')=='19e190c0cb713dcbb5f717444d26ee1277294ef8e29d6088c3c0a120476eb7e0'
patch=read('build/final-source.json');commit=read('build/committed-tree.json');build=read('build/final-build.json');initial=read('build/initial-build.json');sdk=read('build/official.json')
assert patch['base']==commit['parent']=='7caf39914da1e28a67744ecbc963a5f26361474d' and commit['head']=='235f9228651b74c591e6f62cae4c9b761448dd2d'
assert patch['tracked']==3108 and len(patch['files'])==5 and patch['final_patch']=='79cec59831c4259d5caca42a07ed29930033e6180a400659cce9277720b1f2fb'
z=read('build/qualified-tests-source.json');assert z['previous_full_patch']==patch['final_patch'] and z['patch']==sha(p/'fix.patch') and z['files']==commit['files'] and {k for k in patch['files'] if patch['files'][k]!=z['files'][k]}=={'tests/testsuite/ohm_worktree.rs'} and z['runtime_cargo']==build['cargo_sha256']
assert sdk['archive']=='629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8' and sdk['images']['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert build['source']==sha(p/'build/final-source.json') and build['version_stderr']=='' and initial['version_stderr']==''
assert build['previous_cargo']==initial['cargo_sha256']=='a19d515cc301c05ad345ad0d657508905c28a2c900e01963632724cfd3b7289a'
assert build['same_entire_elf']==(build['cargo_sha256']==initial['cargo_sha256'])
assert sdk['images']['cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573'
policy={'seed':b'7\n','deny':b'untrusted compile-time inputs\n','macro':b'local procedural-macro outputs require trust at import time\n','depinfo':b'untracked Cargo output path in compiled code\n'}
shots=read('native/receipts.json')
for label,sha256 in [('published',sdk['images']['cargo']),('initial-fixed',initial['cargo_sha256']),('final-fixed',build['cargo_sha256'])]:
 f='native/'+label+'.json';row=read(f);s=shots[label]
 assert s['raw_stdout']==sha(p/f) and s['exit']==0 and s['stderr']==H(b'')
 assert row['cargo_sha256']==sha256 and row['rustc_sha256']==sdk['images']['rustc']=='c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'
 shipped=label=='published';assert row['expect']==('vulnerable' if shipped else 'protected')
 builds=row['builds'];assert [r['name'] for r in builds]==['opt-out-no-previous','cold','warm','ordinary-fresh-seed','ordinary-fresh-deny','ordinary-fresh-macro','actual-script-rerun','post-script-depinfo']
 assert builds[0]['options']==['-Zohm-worktree-seeds=no'];assert all(r['rc']==0 and len(r['artifacts'])==3 for r in builds)
 for r in builds[2:6]:
  assert all(f for _,f in r['artifacts']) and not r['compiler_or_script_execs']
 assert all(r['compiler_or_script_execs'] for r in [*builds[:2],*builds[6:]])
 assert set(row['cases'])==set(policy)|{'script'}
 for k,c in row['cases'].items():
  a,b=c['victim_before'],c['victim_after'];init=bytes.fromhex(a['hex']);after=bytes.fromhex(b['hex']);m=bytes.fromhex(c['final_marker_hex']);assert a['sha256']==H(init) and b['sha256']==H(after)
  assert init==('dummy owner data for '+k+'\n').encode() and c['final_marker_is_link']==shipped
  if k=='script':assert re.fullmatch(rb'[a-f0-9]{64}\n',m)
  else:assert m==policy[k]
  assert (a['inode']!=b['inode'] and after==m and after!=init) if shipped else (a==b)
 for phase,kind in [(3,'seed'),(4,'deny'),(5,'macro'),(6,'script'),(7,'depinfo')]:
  calls=builds[phase]['relevant_syscalls'];assert calls
  marker=row['cases'][kind]['marker'];victim='/victims/'+kind+'.txt'
  dest=victim if shipped else '/'+marker
  assert any(' rename' in c and c.endswith(' = 0') and (dest+'")') in c for c in calls),(label,kind,dest)
tests=read('tests/complete.json');assert tests['tested_on']==sdk['images'] and tests['util_raw']==sha(p/'tests/atomic.out')
assert '3 passed; 0 failed; 0 ignored;' in (p/'tests/atomic.out').read_text()
expected={'seed_markers_replace_symlinks','creates_a_worktree_without_a_previous_build','git_failure_preserves_an_existing_destination'}
assert len(tests['checks'])==4 and {z['test'].split('::')[-1] for z in tests['checks'] if z['subject']=='fixed'}==expected
for z in tests['checks']:
 label=z['subject'];spec=z['test'].split('::')[-1];a=read('tests/'+label+'-'+spec+'.json')
 assert z['cargo_execs']>0 and a['actual_successful_cargo_execve']==z['cargo_execs'] and z['trace_sha256']==a['raw_strace']
 assert a['raw_stdout']==z['out_sha256'] and a['raw_stderr']==z['err_sha256']
 std='\n'.join(a['observed_lines'])
 if label=='fixed':assert z['exit']==a['exit']==0 and z['cargo_sha256']==build['cargo_sha256'] and '1 passed; 0 failed; 0 ignored' in std
 else:assert label=='shipped' and spec=='seed_markers_replace_symlinks' and z['exit']==a['exit']==101 and z['cargo_sha256']==sdk['images']['cargo'] and '1 failed;' in std and 'panicked at' in std
err=read('tests/first-uncompiled.json');assert err['exit']==101 and 'E0425' in err['diagnostic'] and err['original_patch']==patch['previous_patch']
layout=read('tests/layout-controls.json');assert layout['original']['new-test']['exit']==layout['original']['unchanged-neighbor']['exit']==101
assert 'Option::unwrap' in layout['original']['new-test']['diagnostic'] and layout['original']['unchanged-neighbor']['diagnostic']=='assertion `left == right` failed'
a,b=layout['neutral']['fixed'],layout['neutral']['shipped'];assert a['suite']==b['suite']==tests['suite_sha256'] and a['cargo']==build['cargo_sha256'] and b['cargo']==sdk['images']['cargo']
assert a['source_line']==b['source_line']=='53:9' and a['normalized_stderr']==b['normalized_stderr'] and a['normalized_stderr_sha256']==b['normalized_stderr_sha256']==H(a['normalized_stderr'].encode())
assert 'no compatible build snapshot seeded' in a['normalized_stderr'] and 'Skipped 1 unprepared or unsupported build profiles' in a['normalized_stderr']
for z in (a,b):assert z['result']['exit']==101 and z['result']['successful_cargo_execs']>=2 and z['result']['seen_workspaces']==1
w=read('tests/ordinary-worktree.json');assert w['fixed']['worktree_add_stderr']==w['shipped']['worktree_add_stderr'] and w['fixed']['cargo_sha256']==build['cargo_sha256'] and w['shipped']['cargo_sha256']==sdk['images']['cargo']
for z in w.values():
 assert z['ficlone_errno']==95 and not z['path_uses_symlink'] and not z['canonical_path_has_target_component'] and z['git_worktree_count']==2 and z['donor_namespace_count']==1
 assert [c['units'] for c in z['commands']]==[[['marker_clone_fixture',f]] for f in (False,True,False,True)] and all(c['native_stdout']=='repro-29' for c in z['commands'])
print('Verified 24 marker-fixture builds and all five mutation paths, three atomic-write unit tests, three fixed integration tests, the released integration failure and four native worktree builds per Cargo.')
