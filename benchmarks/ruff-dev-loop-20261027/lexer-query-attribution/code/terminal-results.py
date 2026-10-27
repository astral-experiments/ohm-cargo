"""Join the actual seven or fewer possible frontend substitutions to their native products."""
from pathlib import Path
import hashlib,json
d=Path(__file__).resolve().parent;base=d.parent/'first-occurrence-native-results-v1/commands/test/B'
get=lambda p:json.loads(p.read_bytes());x=get(d/'nine-terminals.json');a=get(d/'terminal-closure.json');deps={j['stable_crate_id']:j for j in get(d/'retained-test-dep-info.json')}
elf={t:get(base/(t+'.json'))['workspace_elf_sha256'] for t in ['original-baseline','lexer-pending-indentation-edit','lexer-pending-indentation-restore']}
v=[]
for j in x['rows']:
 k=j['stable_crate_id'];cl,=[row for row in a['rows']if row['unit']==k];df=deps[k]
 path,=[n for n in elf['original-baseline']if n.endswith('/'+j['exe'])];hs={k:v[path]["raw"]for k,v in elf.items()}
 assert len(set(hs.values()))==1 and not j['link']['dirty_rust_rlibs'] and not j['link']['response_file']
 out=dict(crate=j['crate'],exe=j['exe'],source=j['source'],stable_crate_id=k,elf_sha256_by_observation=hs,dirty_rust_externs=j['dirty_extern_names'],changed_rust_libraries_in_genuine_Wild_argv=j['link']['dirty_rust_rlibs'],native_trace=j['link']['trace_sha256'],binary_order_edges=cl['binary_order_edges'],any_compile_tracked_binary=df['tracked_possible_bin_paths'],derived_from_stored_unused_extern_proof=cl['unused_proof'],remaining_eligible_with_current_native_exclusion=False)
 if cl['unused_proof']:
  assert not cl['used_root_reaches_dirty_workspace_packages'] and cl['exclusive_native_filter_hits']
  out['exclusive_native_outputs']=cl['exclusive_native_filter_hits'];out['possible_for_frontend_only_admission']=True
 else:out['possible_for_frontend_only_admission']=False
 v.append(out)
assert len(v)==9 and sum(i['possible_for_frontend_only_admission']for i in v)==7
(d/'terminal-results.json').write_text(json.dumps({'mode':'H2 B test, first lexer edit','all_full_census':93,'zero_parser_root_cases':9,'proven_unused_before_native_guards_at_most':7,'retain_current_native_guards':0,'rows':v},sort_keys=True,indent=2)+'\n')
