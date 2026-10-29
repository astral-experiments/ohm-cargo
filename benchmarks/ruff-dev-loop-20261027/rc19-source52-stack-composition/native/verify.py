"""Verify the exact source merge, artifacts, tested functions and command results."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def load(f):return json.loads((r/f).read_bytes())
items={}
for entry in (r/'SHA256SUMS').read_text().splitlines():
 d,n=entry.split('  ',1);assert n not in items and '..' not in Path(n).parts and not Path(n).is_absolute()
 f=r/n;assert not f.is_symlink() and sha(f)==d;items[n]=d
assert set(items)=={str(f.relative_to(r)) for f in r.rglob('*') if f.is_file() and f!=r/'SHA256SUMS'}
src=load('source.json');stats=load('source-contents.json');t=load('native-terminal.json');im=load('build.json')
assert t['source']==src and not t['failed'] and set(t['gates'])=={'public-hash','metadata','genuine-consumer','source-five','source-unit'}
assert src['fixed']=='756f52243de60b645e132d5aca95944cca5ce030' and src['tree']=='903c2baf771803bf449357f7a369085ede89bcc0'
assert src['parents']==['30004d93bdf3b07003fb8cd7097be81d862a9f41','ae0256548547cc6f5490097cad6362e13358d274']
assert stats['original_freshness_tests']==stats['merged_freshness_tests'] and stats['changed_files']==['crates/cargo-util/src/paths.rs','src/compiler/fingerprint/mod.rs']
assert t['cargo']==im['cargo']=='740e39ed21737a28a7edfbc4d779c20420f1f518d4187cfbb953c426a61767f6' and im['source']==src['fixed'] and im['tree']==src['tree'] and im['source'] in im['version'] and not im['fresh_cargo_exe'] and not im['fresh_cargo_lib']
assert t['free']>24*2**30 and im['minimum_free_bytes'][0]>24*2**30
for name,h in t['gates'].items():assert sha(r/'cases'/(name+'.json'))==h
for x in load('cases/public-hash.json'):
 row=x['case'];rr=row.get('rows',row.get('records'));assert row['cargo']==im['cargo'] and row['compiler']==im['qualified_genuine_compiler']
 assert [z['value'] for z in rr]==[17,29,29] and all(z['exit']==0 for z in rr) and len(rr[-1]['typed'])==2 and all(z[1] for z in rr[-1]['typed'])
 if x['name']=='disabled':assert row['disabled']
 else:
  assert not row['sentinel_replaced'] and not row['cache_symlink']
  if x['name']=='dangling':assert not row['victim_existed_after']
  else:assert row['inode_preserved'] and row['before_sha']==row['after_sha']
meta=load('cases/metadata.json');assert len(meta)==5
for m in meta:
 rs=m['rows'];assert [a['success'] for a in rs]==[True,True,False,False,False,True,True]
 diag=rs[2]['diag'];assert diag==rs[3]['diag']==rs[4]['diag'] and diag['code']=='E0034' and diag['line']==3 and diag['file']=='client/src/main.rs' and diag['rendered']=='f56ad66c2eeaeee09d18d874b7c52f8929edc44bdef3c993ce34c380741dde56'
 for i in (1,6):assert len(rs[i]['units'])==4 and all(z[1] for z in rs[i]['units'])
 if m['method']=='ordered':
  a=m['actual_order'];assert a['public_api']==m['flag'] and a['target']==m['requested_order'] and m['raw_events']
  assert a['publication']==('release-fd' if a['target']=='provider-first' else 'timeout-fd')
 else:assert m['actual_order'] is None and m['raw_events'] is None
j=load('cases/genuine-consumer.json');assert j['cargo']==im['cargo'] and j['rustc']==im['qualified_genuine_compiler']
rows={a['phase']:a for a in j['cases']};assert len(rows)==12
vals={'original':17,'original-repeat':17,'native-relinked':29,'native-repeat':29,'private-rust-edit':30,'private-rust-repeat':30,'private-rust-independent':30,'restored':17,'restored-repeat':17}
for phase,val in vals.items():
 x=rows[phase];assert x['exit']==0 and x['program']['value']==val
 for n in ('stdout','stderr','raw_exec'):assert len(x[n])==64
 assert x['raw_children']
for ph,crates in [('native-producer',{'producer'}),('native-relinked',{'app'}),('private-rust-edit',{'producer','app'}),('private-rust-independent',{'build_script_build','producer','middle','app'}),('restored',{'producer','app'})]:
 assert set(rows[ph]['real_compilers'])==crates
for name in ('original-repeat','native-repeat','private-rust-repeat','restored-repeat'):
 x=rows[name];assert not x['real_compilers'] and not x['native_commands'] and all(z[1] for z in x['typed'])
for name in ('invalid-warm','invalid-vacant'): assert rows[name]['exit']==101 and 'cc' in rows[name]['native_commands'] and not rows[name]['program']
for name in ('native-relinked','private-rust-edit','private-rust-independent','restored'):assert 'rust-lld' in rows[name]['native_commands']
assert {'ar','cc'}<=set(rows['native-producer']['native_commands'])
for a,b in [('original','restored'),('private-rust-edit','private-rust-independent'),('native-relinked','native-repeat')]:assert rows[a]['program']==rows[b]['program']
for name in ('native-producer','native-relinked','private-rust-edit','restored'):
 assert rows[name]['middle_metadata']==rows['original']['middle_metadata']
assert len(set(x['program']['elf_sha256'] for x in rows.values() if x['program']))==3
five=load('cases/source-five.json');assert len(five['tests'])==5 and len(set(five['tests']))==5 and all(n.startswith('freshness::') for n in five['tests']) and len(five['authenticated_child_exec_files'])>=15 and five['cargo']==five['bound_cargo']==t['cargo'] and src['fixed'] in five['version']
units=load('cases/source-unit.json');assert units['count']==len(set(units['tests'])) and units['count']>=58 and any('changed_or_pending_metadata_dependency' in x for x in units['tests']) and any('public_api_hash_replaces_a_symlink' in x for x in units['tests'])
initial=load('initial-path-controls.json');assert initial['initial_command_exit']==101 and len(initial['initial_tests'])==5 and sum(s=='FAILED' for _,s in initial['initial_tests'])==3 and initial['snapshot_root_was_alias'] and initial['fixed_root_matches_exact_compile_time_path'] and initial['verified_same_binary']==t['cargo'] and initial['verified_same_suite_bytes']==five['suite'] and not initial['genuine_tests_launched_by_unsupported_preflight']
print('Original #52 composition verified: nine writer commands, 35 conditional checks, 12 wrapperless native build commands, five original source regressions and',units['count'],'fingerprint tests.')
