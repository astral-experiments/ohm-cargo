from pathlib import Path
import hashlib,json,re
p=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def read(f):return json.loads((p/f).read_bytes())
for line in (p/'SHA256SUMS').read_text().splitlines():
 digest,name=line.split('  ');assert sha(p/name)==digest,name
subjects=read('subjects.json')
assert subjects['patch']==sha(p/'cargo.patch')
proof=read('native.json');wild=subjects['wild']
assert len(proof)==7
success=['01-first','02-unchanged','03-real-edit','04-same-state-forced','05-independent-empty-valid','06-real-restore-malformed','07-same-state-forced-malformed','08-independent-empty-malformed','09-remove-and-recover']
for name,arm in proof.items():
 stages=arm['commands'];assert not set(arm['environment_keys'])-{'HOME','PATH','LANG','RUSTUP_HOME','RUSTUP_AUTO_INSTALL','CARGO_HOME','CARGO_NET_OFFLINE'}
 for value in stages.values():
  assert value['build_scripts']==0
  assert value['trace_files'] and all(re.fullmatch('[0-9a-f]{64}',x) for x in value['trace_files'].values())
  assert re.fullmatch('[0-9a-f]{64}',value['raw_result_sha256'])
 if name in ['verbatim-v1-relative','verbatim-v2-control-abs']:
  assert list(stages)==['01-first'] and stages['01-first']['status']==101 and arm['terminal_sha256'] is None
  continue
 assert list(stages)==success and len(arm['terminal_sha256'])==64
 data=[stages[k] for k in success]
 is_parent=name in ('verbatim-v1-absolute','verbatim-v1-upward')
 is_stock=name=='verbatim-v2-control-upward'
 assert [v['status'] for v in data]==[0,0,0,0,0,0 if is_parent else 101,101,101,0]
 assert [v.get('value') for v in data]==[17,17,17 if is_parent else 29,29,29,29 if is_parent else None,None,None,17]
 assert data[0]['elf']==data[1]['elf']==data[-1]['elf'] and data[3]['elf']==data[4]['elf']
 assert data[2]['elf']==(data[0] if is_parent else data[4])['elf']
 assert not data[1]['execs']
 assert data[4]['empty_at_start'] and data[7]['empty_at_start']
 assert all(x['native_error'] for x in (data[6],data[7]))
 for idx in (2,5):
  v=data[idx]
  reader=[t for t in v['execs'] if t.get('crate')=='reader']
  links=[t for t in v['execs'] if t['type']=='linker']
  if is_parent:assert not reader and not links
  elif is_stock:assert reader and links and not any(t['link_only'] for t in reader)
  else:
   assert len(reader)==len(links)==1 and reader[0]['link_only'] and links[0]['exe']==wild and links[0]['has_choice_flag']
 assert arm['cargo_sha256']==subjects['parent_cargo_sha256' if is_parent or is_stock else 'candidate_cargo_sha256']
checks=read('check.json')
ch=checks['results'];assert checks['cargo']==subjects['candidate_cargo_sha256'] and len(ch)==7 and all(not v['linkers'] for v in ch.values())
assert not ch['initial-unchanged']['compiler_units'] and not ch['private-body-unchanged']['compiler_units']
assert ch['private-body']['compiler_units']==[['current_api','--emit=dep-info,metadata']]
assert all(ch[k]['diagnostics']==['E0061'] and ch[k]['status']==101 for k in ['public-api','empty-public-api'])
su=read('suite.json')
assert su['real-link-suite-v1-parent']['actual_expected']==[17,29] and su['real-link-suite-v1-parent']['exit']==101
assert su['real-link-suite-v1-fixed']['exit']==0 and su['real-link-suite-v1-fixed']['compiler'][-1]=='link:integration'
for n,k in [('real-link-unit2',38),('real-link-review-broad',37),('real-link-review-extra',2)]:
 assert su[n]['exit']==0 and len(su[n]['case_results'])==k and all(status=='ok' for _,status in su[n]['case_results'])
assert su['real-link-suite-v1-broad']['exit']==101 and [n for n,status in su['real-link-suite-v1-broad']['case_results'] if status=='FAILED']==['freshness::early_native_integration_tests_default_and_fallback']
print('Five complete nine-command native controls, two driver-specific initial rejections, seven real checks, 39 integration and 38 fingerprint tests verified.')
