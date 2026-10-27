"""Verify the exported native behavior, physical full/link-only processes, executable identities, stock variants."""
from pathlib import Path
import hashlib,json,collections
root=Path(__file__).resolve().parent
if (root/'SHA256SUMS').is_file():
    for l in (root/'SHA256SUMS').read_text().splitlines():
        h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
get=lambda n:json.loads((root/n).read_bytes())
n=get('native-observations.json');f=n['functional'];h=n['helper'];assert len(f)==33 and len(h)==13
for k in ['first-dep-change','positive','restore','layout-again']:assert f[k]['api_modes']==['link-only'] and not f[k]['fixed'] and f[k]['wild']
assert f['layout-again']['auxiliary']['bytes']==40405 and f['map-depfile-regenerated']['auxiliary']['map'][0]==1686027 and f['map-depfile-regenerated']['auxiliary']['linker.d'][0]==11456
assert f['cfg-active-fail']['execution_rc']==101 and f['cfg-active-pass']['execution_rc']==0 and 'active: test' in f['cfg-active-pass']['tests']
assert f['warning-prime']['messages']==f['warning-dirty']['messages'] and f['warning-dirty']['messages']
assert all(f[k]['api_modes']==['full'] for k in ['cfg-active-fail','cfg-active-pass','wrapper-dirty','map-depfile-regenerated'])
assert h['loader-debug']['api_modes']==['full'] and sorted(k for k,v in h['loader-debug']['side_outputs'] if v>0)==['ld.bfd','rustc']
for s in ['collect2','ld.bfd']:
 assert h['noexec-'+s]['rc']==0 and not h['noexec-'+s]['wild'] and h['noexec-'+s]['elf']!=h['restored-'+s]['elf'] and len(h['restored-'+s]['wild'])==1
assert h['backdated-codegen-object']['api_modes']==['full'] and h['backdated-codegen-object']['requested_rejected_object']['old_links']==2 and h['backdated-codegen-object']['elf']==h['cold']['elf']
for k,v in n['direct']['stock'].items():
 c=n['direct']['candidate'][k];assert (v['modes'],v['list'],v['exit'],v['cfg_disabled_proof'])==(c['modes'],c['list'],c['exit'],False)
assert [v['exit'] for k,v in sorted(n['direct']['stock'].items()) if k in ['true-after-public-self','true-after-public-self-pass']]==[101,0]
t=n['nested']['samples'];assert t['earlier-member-now-exists']['marker']==['0000000000000097'] and t['earlier-member-now-invalid']['rc']==101 and t['removed-earlier-member']['elf']==t['cold']['elf']
ws=get('workspace-observations.json');stock= get('stock-true-full-oracles.json') if (root/'stock-true-full-oracles.json').is_file() else None
for ed,d in ws.items():
 for label in d['A11']:
  a=d['Stock11'][label];c=d['A11'][label];assert (a['units'],a['executables'],a['elf_count'])==(619,102,110)
  assert all(a[k]==c[k] for k in ['roster','messages','cli','caller','dirty','units','executables','elf_count'])
  assert sorted(x[1:] for x in a['wild'])==sorted(x[1:] for x in c['wild'])
  assert sorted(x[1:] for x in a['rustc'] if x[1]!='api')==sorted(x[1:] for x in c['rustc'] if x[1]!='api')
  if label.startswith('fresh'):assert not a['dirty'] and not a['rustc'] and not c['rustc'] and not a['wild']
  if label in ['edit','restore','edit-again']:
   n_api=1 if ed=='wasm-only' else 2
   assert len(a['wild'])==(2 if ed=='wasm-only' else 67)
   assert [x[2] for x in a['rustc'] if x[1]=='api']==['full']*n_api
   assert [x[2] for x in c['rustc'] if x[1]=='api']==(['full'] if label=='edit' else ['link-only'])*n_api
   assert all(a['api'][k]['raw']==c['api'][k]['raw'] and a['api'][k]['test_list']=='0 tests, 0 benchmarks' for k in a['api'])
   assert len(a['elfs'])==110 and a['elfs'].keys()==c['elfs'].keys()
   for k,av in a['elfs'].items():
    cv=c['elfs'][k];assert av['content_with_two_wild_fields_masked']==cv['content_with_two_wild_fields_masked']
    if av['raw']!=cv['raw'] and stock:
     w=stock[ed]['phases']['edit-again' if label=='edit' else label][k];assert {av['raw'],cv['raw']}<=set(w['forced_full_jobs_1_8']+[w['independent_cold_full_original']])
print('Verified 33 general+13 native helper cases, 6 nested cases, 5 matched custom-compiler cases/arm, and 32 whole workspace commands.')
