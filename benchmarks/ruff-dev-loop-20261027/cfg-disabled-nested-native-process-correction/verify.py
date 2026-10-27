from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
for s in (p/'SHA256SUMS').read_text().splitlines():
 h,n=s.split('  ',1);assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
x=json.loads((p/'observations.json').read_bytes());assert len(x)==6
for label,s in x.items():
 t=s['phases'];assert len(t)==6
 for phase,c in t.items():
  assert len(c['actual_api_jobs'])==len(c['wild'])==len(c['prior_mode_label'])
  for job in c['actual_api_jobs']:
   assert (job['mode']=='link-only')==job['separate_Z_link_only']==job['source_or_recipe'].endswith('.rlink')
  if label.startswith(('tiny-baseline','tiny-a10c','tiny-a11c')):
   assert [a['mode'] for a in c['actual_api_jobs']]==(['full'] if phase in ('cold','removed-earlier-member') else ['link-only'])
  elif label.startswith('tiny-a9c'):
   assert [a['mode'] for a in c['actual_api_jobs']]==(['full'] if phase in ('cold','first-changed') else [])
  else:
   assert [a['mode'] for a in c['actual_api_jobs']]==(['link-only'] if phase=='earlier-member-now-invalid' else ['full'])
 assert t['earlier-member-now-invalid']['exit']==(0 if label.startswith('tiny-a9c') else 101)
 assert t['earlier-member-now-exists']['marker']==([] if label.startswith('tiny-a9c') else ['0000000000000097'])
print('Verified 36 raw-exec phase classifications, original link counts, genuine symbols and exit codes.')
