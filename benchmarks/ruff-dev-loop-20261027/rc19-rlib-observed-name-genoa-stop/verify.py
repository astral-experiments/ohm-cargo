from pathlib import Path
import gzip,json,hashlib,collections
p=Path(__file__).resolve().parent
def read(n):
 b=(p/n).read_bytes()
 return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
s=read('result.json');o=read('unpaired-observation.json.gz');e=read('caller-elf.json.gz');r=read('raw-bindings.json');t=s['actual_executions'];assert s['registered_pairs']==8 and s['full_pairs']==t['accepted_pairs']==t['completed_B_visits']==t['ordinary_B_Cargo']==0 and t['ordinary_A_Cargo']==2 and t['A_edits']==t['A_immediate_repeats']==t['actual_linked_caller']==t['actual_caller_runtime']==1 and t['A_cargo_compile_lines']==10 and t['repeat_cargo_compile_lines']==0
assert s['exit_receipt']==r['clock/visit-01-A.exit.json']['sha256'] and s['go']==r['clock/grant.json']['sha256'] and s['protocol']=='86fd410922315ae22b9d3de58f50b30ba1e8939a'
c,g=s['observed_reader'],s['prior_accepted_reader'];assert c['exit']==g['exit']==0 and c['stdout']==g['stdout']=='2 SIM222\n3 SIM222\n4 SIM222\n' and c['stderr_sha256']==g['stderr_sha256']==hashlib.sha256(b'').hexdigest() and c['input']==g['input']
assert c['executable']==r['stopped/observed-elf']['sha256'] and g['executable']==r['stopped/qualified-elf']['sha256'] and e['raw_sha256']==[g['executable'],c['executable']] and c['executable']!=g['executable']
lit=o['full_native'];assert lit['objects']==256 and lit['fields']==512 and lit['bytes']==101719820 and lit['literal_equal'] and lit['actual_sha256']==lit['expected_sha256']==o['prediction_before_postcommand_current_file_read']['predicted']==o['real_raw_product']==r['stopped/emitted.rlib']['sha256']
assert o['phases']['edit']['ns']==o['observer']['edit']['command_ns'] and o['phases']['repeat']['ns']==o['observer']['repeat']['command_ns'];names=o['observer']['edit']['objects'];assert len({n['name'] for n in names})==len(names)==256 and all(n['mask']==0x100 for n in names) and o['observer']['repeat']['objects']==[]
assert e['bytes']==75800496 and e['all_elf_and_program_and_section_header_bytes_equal'] and e['outside_sections']==0 and sum(e['differing_bytes_by_section'].values())==e['differing_bytes']
assert e['differing_bytes_by_section']=={'.data.rel.ro':19711,'.note.gnu.build-id':20,'.rela.dyn':19707,'.rodata':412863,'.symtab':137,'.text':10870}
src=e['source'];assert src['qualified']['native_source_name_bytes']==70 and src['observed']['native_source_name_bytes']==77 and src['qualified']['name_in_whole_elf']==[1,0] and src['observed']['name_in_whole_elf']==[0,1] and src['qualified']['source_contents']==src['observed']['source_contents']==s['compared_source_bytes'];assert src['qualified']['name_in_rodata_at']==src['observed']['name_in_rodata_at']==0
assert all(v==[0,0] for v in e['nonce_bytes_found'].values())
delta=e['table_field_deltas'];assert delta['.rela.dyn']['deltas']==[{'0':19240},{'0':19240},{'7':15252,'8':3988}] and delta['.data.rel.ro']['deltas']==[{'7':15256,'8':3988}] and delta['.symtab']['deltas']==[{'0':132}]*4+[{'7':122,'8':10},{'0':132}]
assert not s['elapsed_claim'] and not s['freshness_explicit_typed_on_measured_commands'];print('First Genoa visit retained: 1 A edit and 1 immediate repeat, 256 kernel-delivered names, one 101719820-byte archive equal, both SIM222 verdicts agree; 2 different complete caller ELFs. Zero B visits or admitted pairs.')
