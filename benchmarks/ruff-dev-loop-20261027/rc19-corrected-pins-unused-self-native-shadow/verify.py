from pathlib import Path
import gzip,hashlib,json
s=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
for line in (s/'SHA256SUMS').read_text().splitlines():
 digest,name=line.split('  ',1);assert digest==h((s/name).read_bytes()),name
r=json.load(gzip.open(s/'observations.json.gz'));summary=json.loads((s/'sources.json').read_bytes())
assert summary['ruff']=='93526150df078af7dd8fc4226cdcc469539d2001' and summary['historical']=='a50dc58628691ee00a21809e19bdea71958e4f3c'
assert len(summary['toolchain'])==2
G='generate_inline_tests';F='fixtures'
def run(series,n):return next(x for x in r[series] if x['phase'].startswith(f'{n:02d}-'))
def status(x,t):return x['products'][t]['list_exit']
def linked(x,t):return [v for v in x['native'] if v['file'].startswith(t+'-')]
def work(x,t):return [c for c in x['rustc'] if c['crate']==t]
for series in ('current','shipped','defaults_off'):
 orig=run(series,1);edit=run(series,2)
 assert orig['mode']=='original' and edit['mode']=='historical' and orig['exit']==edit['exit']==0
 assert status(orig,G)==status(orig,F)==0 and len(linked(orig,G))==1 and len(linked(orig,F))>=1
 assert status(edit,F)==83 and len(linked(edit,F))==1
 assert all(z['find_gcc_s'] and len(z['psm_families'])==1 for z in linked(orig,G)+linked(edit,F))
 assert orig['sources']!=edit['sources']
 if series!='defaults_off':
  assert not work(edit,G) and not linked(edit,G) and status(edit,G)==0 and edit['products'][G]['sha256']==orig['products'][G]['sha256']
  assert 'ruff_python_parser' in orig['products'][G]['unused_externs']
 else:
  assert work(edit,G) and linked(edit,G) and status(edit,G)==83
  bad=run(series,3);assert bad['exit']==101 and work(bad,G) and linked(bad,G) and bad['native_error_lines'] and not bad['products']
  assert status(run(series,4),G)==0
current=r['current'];cold,ed,forced,bad,forced_bad,recovered=current
assert status(forced,G)==83 and len(linked(forced,G))==1 and forced['products'][G]['sha256']!=ed['products'][G]['sha256']
assert bad['exit']==0 and status(bad,G)==83 and not linked(bad,G) and bad['products'][G]['sha256']==forced['products'][G]['sha256']
assert forced_bad['exit']==101 and len(linked(forced_bad,G))==1 and forced_bad['marker_diagnostic']
assert status(recovered,G)==0 and recovered['products'][G]['sha256']==cold['products'][G]['sha256']
old_bad=run('shipped',3);assert old_bad['exit']==0 and not work(old_bad,G) and not linked(old_bad,G)
assert r['shipped'][3]['exit']==0 and status(r['shipped'][3],G)==0
terminal=json.loads((s/'fresh.json').read_bytes())
for which,rc in [('valid',0),('invalid',101)]:
 e=terminal[which];a=r['empty_'+which][0];assert e['initial_target_files']==e['initial_shared_files']==0 and e['published_before_actual_link'] and e['real_search_exact']
 assert a['exit']==rc and len(linked(a,G))==1 and bool(work(a,G))
 if which=='valid':assert status(a,G)==83
 else:assert a['marker_diagnostic']
for series,x in r.items():
 for a in x:assert len(a['raw'])>=3 and all(len(h)==64 for h in a['raw'].values())
assert set(r['failed_predicted_empty'][0]['products'])=={G} and status(r['failed_predicted_empty'][0],G)==0
assert set(r['failed_ambiguous_empty'][0]['products'])=={G} and status(r['failed_ambiguous_empty'][0],G)==0
assert summary['psm_restored'] and summary['provider_before']==summary['provider_restored']=='absent'
print('Verified official -18 and corrected defaults, separately trained defaults-off, the exact Wild same-state forced links, independently empty valid/invalid native outcomes and both retained calibration failures.')
