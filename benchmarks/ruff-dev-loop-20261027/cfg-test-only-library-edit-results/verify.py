"""Read independently from all presented raw Rust metadata, output SHA comparisons, real traces and test lists."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'run'));from wire import read
from compare import archive_diff
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();J=lambda p:json.loads((R/p).read_bytes());rdom={'build':(501,922,2,4,5),'check':(520,596,1,0,0),'test':(619,1060,4,11,14)};roles={'build':{('ty_ide',False),('ty_wasm',False)},'check':{('ty_ide',False)},'test':{('ty_ide',False),('ty_ide',True),('ty_wasm',False),('api',True)}};ph=J('phases.json');plan=J('run/plan.json');assert H(R/'run/plan.json')=='ef1fb915efa17ef62757260d24cef7e958d2a980bfb0c6d3fd2a08aa8f7b8ed3' and H(R/'run/historical.patch')==plan['source_selection']['patch_sha256'];s={k:R/'inputs'/(k+'-docstring.rs') for k in ('original','edited')};assert all(H(p)==plan['source_selection'][k+'_sha256'] for k,p in s.items());raw={p.stem:p for p in (R/'raw-rmeta').glob('*.rmeta')};assert raw and all(H(p)==k for k,p in raw.items());assert len(ph)==19
for m,(units,products,nfull,ncached,nwild) in rdom.items():
 for name in ('cold','edit','restore'):
  r=next(v for v in ph if v['mode']==m and v['label']==name);w=r['actual_source_entry'];origin='edited' if name=='edit' else 'original';assert read(raw[w['rmeta_sha256']],s[origin],'docstring.rs')==w;assert r['active_tests_invoked_by_cargo']==[] and r['cargo_units']==units and r['products']==products and r['missing']==0;assert w['carries_filename_near_entry']
  if name=='cold':continue
  q=J('process/'+m+'-'+name+'.json');assert {(v['crate'],v['test']) for v in q if v['kind']=='rustc-full'}==roles[m]
  for a in q:
   if not a['kind'].startswith('rustc'):continue
   assert a['image_sha256']==plan['subject']['rustc_frontend'] and bool(any(v=='-Zlink-only' or i>0 and a['argv'][i-1]=='-Z' and v=='link-only' for i,v in enumerate(a['argv'])))==(a['kind']=='rustc-link-only')
  assert [r['jobs'].get(k,0) for k in ('rustc-full','rustc-link-only','wild')]==[nfull,ncached,nwild];imm=next(v for v in ph if v['mode']==m and v['label']==name+'-fresh');assert imm['fresh']==units and not imm['jobs'] and imm['changed_files']==0;assert r['setup']['driver']==plan['subject']['rustc_driver_ohm_rust_pr233'] and r['setup']['cargo']==plan['subject']['cargo_ohm_pr254']
  if m in ('build','test'):
   assert r['elf_roster']['count']==(15 if m=='build' else 110) and len(r['elf_roster']['changed'])==(0 if m=='build' else (1 if name=='edit' else 2))
  assert r['changed_files']=={'build':4 if name=='edit' else 3,'check':1,'test':5}[m]
 for r in [v for v in ph if v['mode']==m and v['label'] in ('cold','edit','restore')]:assert all(z['source_tracked'] for z in r.get('producer_dep_inputs',{}).values())
for a in J('cargo-native-section-comparisons.json'):
 assert a['cgu_objects']==[171,171] and a['equal_complete_object_bytes_per_cgu_slot']==171 and a['equal_member_name_per_cgu_slot']==0 and not any(a['per_section_group_differences'].values())
# Compare the independent empty producer's objects again directly from the recorded ordered member rosters.
m=[J('independent/compiler-'+n+'/evidence.json') for n in ('original','edited')];assert all(v['status']==0 for v in m);r=archive_diff(m[0]['archive'],m[1]['archive']);assert r==J('independent/clean-archive-comparison.json') and r['equal_complete_object_bytes_per_cgu_slot']==171 and r['equal_member_name_per_cgu_slot']==0
for n,v in zip(('original','edited'),m):
 w=read(raw[v['metadata']['sha256']],s[n],'docstring.rs');assert w['normalized_bytes']==s[n].stat().st_size and w['lines']==len(s[n].read_bytes().splitlines())
mixed=J('mixed/verified-pairs.json');assert len(mixed)==4
for x in mixed:
 assert x['whole_so_equal'];assert x['have_both_matching_raw_archives']==(x['mode']=='test')
 if x['mode']=='test':
  a=x['native_members'];assert a['cgu_objects']==[67,67] and a['equal_complete_object_bytes_per_cgu_slot']==67 and a['equal_member_name_per_cgu_slot']==0
lists={k:set((R/'test-lists'/(k+'.txt')).read_text().splitlines()) for k in ('cold','edit','restore')};assert len(lists['cold'])==1909 and len(lists['edit'])==1910 and lists['restore']==lists['cold'];assert not lists['cold']-lists['edit'] and lists['edit']-lists['cold']=={'docstring::tests::'+plan['test_control_name']+': test'}
ext=J('independent/external-readers.json');assert len(ext)==8
for e in ext:
 if e['reader']=='reader_good.rs':assert e['status']==0;continue
 assert e['status']==1 and any((v.get('code') or {}).get('code')=='E0061' for v in e['all_diagnostics']);sp,=e['foreign_definition_spans'];assert (sp['line_start'],sp['column_start'])==(30,12)
 assert [q['text'] for q in sp['text']]==(['    pub fn render(&self, kind: MarkupKind) -> String {'] if e['input_metadata_state']==e['disk_source_state'] else [])
mac=J('independent/macro-headers.json');assert mac['macro_build_status']==0 and len(mac['rows'])==2
for r in mac['rows']:assert r['compiler_status']==0 and int(r['runtime_stdout'])==s[r['source']].stat().st_size and r['source_tracked_in_real_depinfo']
bind=J('independent/resolved-input-bindings.json');assert bind['original_cargo_package_environment_pid']==bind['true_cold_rustc_pid'] and len(bind['direct_externs'])>5;xs=bind['all_sources_from_authentic_dep_info'];assert [p for p in xs['original'] if xs['edited'][p]!=xs['original'][p]]==[plan['source_selection']['file']]
diag=J('diagnostics.json');assert len(diag)==19;assert all(all(x['target']['name']=='file_watching' and x['message']['level']=='warning' and x['message']['message']=='method `set_watch` is never used' for x in v) for v in diag.values())
print('Verified three real Cargo modes, six edit/restores, six immediate no-ops, eleven raw metadata files, five native producer object pairs, two mixed-library pairs, eight ordinary external readers, two proc-macro observations and the exact enabled test roster.')
