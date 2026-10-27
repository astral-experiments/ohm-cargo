"""Verify the documented whole-test cutoff counterexamples from the public-safe observations."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
j=json.loads((root/'observations.json').read_bytes())
w=j['same_linker_inputs_fixed_workers']; assert set(w)=={'ruff_wasm','ty_wasm'}
for key,v in w.items():
 x=v['elf']; assert x['width-1-0.elf']==x['width-1-4.elf']!=x['width-4-1.elf']==x['width-4-3.elf']==x['width-2-2.elf']
 assert len(v['inputs'])==48 and len(v['symbol_object_sha256'])==64
refs=j['same_state_full_replays']; assert set(refs)=={'AA1b','AA2','Cfull1','Cfull2','Cfull3'}
one=w['ruff_wasm']['elf']['width-1-0.elf'];many=w['ruff_wasm']['elf']['width-4-1.elf']
assert [refs[k]['after']['ruff_wasm']['elf'] for k in refs if k.startswith('AA')]==[many,many]
assert [refs[k]['after']['ruff_wasm']['elf'] for k in ('Cfull1','Cfull2','Cfull3')]==[one,many,many]
for r in refs.values():
 e=r['recorded_edited_command']; assert len(e['rustc'])==14 and [x[2] for x in e['rustc'] if x[1]=='api']==['full','full'];assert not r['initial_fresh']['rustc'] and not r['final_fresh']['rustc']
v=j['visible_elf_differences']['ruff_wasm'];assert set(v['changed_sections'])=={'.rodata','.note.gnu.build-id'} and not v['object_payloads_differ']
a,b=v['changed_sections']['.rodata'];assert a['sha256']==b['sha256'] and (a['entsize'],b['entsize'])==(8,0)
d=j['adversarial'];s=d['baseline233'];c=d['a8']
assert 'active: test' in s['rustc']['cases']['edit']['tests'] and c['rustc']['cases']['edit']['tests'].startswith('0 tests')
assert len(s['loader']['requested_loader_diagnostic_files_for_actual_api_processes'])==2 and not c['loader']['requested_loader_diagnostic_files_for_actual_api_processes']
for h in ('collect2','ld.bfd'):
 a=s['helpermode']['observations'][h];b=c['helpermode']['observations'][h];assert a['helper_sha256']==b['helper_sha256'] and a['elf']!=b['elf'] and 'api' in a['rustcs'] and 'api' not in b['rustcs']
for k in ('new-sdk-shadow','changed-resolved-native'):assert s['native_subset'][k]['rc']==c['native_subset'][k]['rc']==101
print('Verified two real worker-dependent binaries, five matched full replays and four authentic rejected side effects.')
