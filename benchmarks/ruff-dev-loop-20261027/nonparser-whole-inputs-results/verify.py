"""Verify the physical whole-workspace records, ordinary external callers, and two native selector controls."""
from pathlib import Path
import hashlib,json
O=Path(__file__).resolve().parent
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def J(p):return json.loads((O/p).read_bytes())
target={('build','ty-diagnostic'):(12,0,5,5,5),('test','ty-diagnostic'):(25,0,19,16,16),('build','formatter'):(3,6,8,8,8),('test','formatter'):(6,30,35,27,25)};work={'build':(501,922,15),'test':(619,1060,110)};p=J('phases.json');z=J('subject.json');assert h(O/'run/plan.json')==z['historical_path_sha256']['before-plan'];assert h(O/'run/formatter.patch')==z['historical_path_sha256']['formatter'] and h(O/'run/ty-diagnostic.patch')==z['historical_path_sha256']['ty'];rust=z['frontend'];wild=z['prior_fixed_host_manifest']['Wild']['sha256']
for (mode,case),(full,cached,links,changed,elfs) in target.items():
 for view in ('edit','restore'):
  label=case+'-'+view;a,=[v for v in p if v['mode']==mode and v['label']==label];f,=[v for v in p if v['mode']==mode and v['label']==label+'-fresh']
  for v in (a,f):assert (v['cargo_artifact_units'],v['published_files'],v['workspace_elf_count'])==work[mode] and v['missing_published_files']==0 and not v['executed_test_programs'] and v['setup']['rustc_driver']==z['driver'] and v['setup']['cargo']==z['cargo']
  assert (a['jobs'].get('rustc-full',0),a['jobs'].get('rustc-link-only',0),a['jobs'].get('wild',0),a['different_workspace_elfs'])==(full,cached,links,elfs);assert a['elf_map_sha256']==f['elf_map_sha256'] and f['fresh_units']==work[mode][0] and not f['jobs'] and f['different_published_files']==0
  changed_files=J(mode+'-'+label+'-all-changed-files.json');assert len(changed_files)==a['different_published_files'] and all(v['before']!=v['after'] for v in changed_files.values())
  cl=a['cli'];assert cl['ty']['returncode']==1 and cl['ty']['stdout'].count('invalid-argument-type')==(2 if case=='ty-diagnostic' and view=='edit' else 1);assert cl['ruff']['returncode']==0 and cl['ruff']['stdout']==('# Tabbed\npass  # Tabbed\n' if case=='formatter' and view=='edit' else '# \tTabbed\npass  # \tTabbed\n')
  rows=[q for q in J(mode+'-'+case+'-jobs.json') if q['side']==view];assert sum(r['kind']=='rustc-full' for r in rows)==full and sum(r['kind']=='rustc-link-only' for r in rows)==cached and sum(r['kind']=='wild' for r in rows)==links
  for r in rows:
   assert len(r['source_exec_trace_sha256'])==64
   if r['kind'] in ('rustc-full','rustc-link-only'): assert r['executable_sha256']==rust;assert bool(r['actual_full_or_link_only'])==(r['kind']=='rustc-link-only')
   elif r['kind']=='wild': assert r['executable_sha256']==wild
 j=J(mode+'-'+case+'-summary.json');assert (j['native_job_pairs'],j['actual_changed_input_link_pairs'])==(links,changed)
for case,targets,types,other in [('formatter',[100,77,79,76,176,119],'rustc-link-only',6),('ty-diagnostic',[176,119],'rustc-full',2)]:
 rows=[r for r in J(case+'-residuals.json') if r['physical_summary']['outcome'].startswith('no known')];assert len(rows)==other;assert [r['physical_summary']['matched_ordered_equal_args'] for r in rows]==targets
 assert all(all(p['rustc_kind']==types for p in q['phases']) for q in rows);assert [len(r['wild_argv_change']) for r in rows]==([3]*6 if case=='formatter' else [66,34])
from collections import Counter
readers=J('ordinary-new-callers/complete.json');assert len(readers)==6 and all(r['rustc_status']==0 and r['real_compiler_sha256']==z['driver'] for r in readers);formats=[r['runtime_stdout'] for r in readers if r['crate']=='ruff_python_formatter'];assert formats==['# \tTabbed\npass  # \tTabbed\n','# Tabbed\npass  # Tabbed\n','# \tTabbed\npass  # \tTabbed\n'];r=J('initial-test-freshness.json')['phases'];assert r['warm-1']['source_rustc']==['ron'] and len(r['warm-1']['changed_product_names'])==4 and r['warm-1']['receipt']['fresh']==563 and r['warm-2']['receipt']['fresh']==619 and not r['warm-2']['receipt']['jobs']
ind=J('independent-selector.json');base=O/'genuine-cgu-name-selector-v2'
for e in J('genuine-cgu-name-selector-v2/complete.json'):
 t=e['target'];assert h(base/t/'genuine-input.rcgu.o')==e['source_object_sha'] and h(base/t/'selector.ld')==e['selector_sha256']; names=[Path(n).name for n in e['actual_source_argv_paths']];assert len(set(names))==2;o=e['rows'];assert len(o)==4
 for n in o:
  assert n['gcc_status']==0 and (int(n['symbol_addresses']['picked_end'],16)-int(n['symbol_addresses']['picked_start'],16))==n['program_return'];assert n['input_sha256']==e['source_object_sha'] and n['sha256_executed_wild']==wild and len(n['successful_wild_exec_sha256'])==1
 for v in ('explicit-script','earlier-search-library'):
  b=[x for x in o if x['mode']==v];assert [x['program_return'] for x in b]==ind[t][v]==[e['section_size'],0]
print('Verified 8 edited/restored full-workspace endpoints, 8 immediate repeats, 6 ordinary Rust callers, 8 stock Wild selectors and 8 independently replayed selectors.')
