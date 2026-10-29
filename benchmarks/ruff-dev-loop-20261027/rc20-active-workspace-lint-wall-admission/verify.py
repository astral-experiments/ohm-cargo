from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
def j(s):return json.loads((p/s).read_bytes())
def h(s):return hashlib.sha256((p/s).read_bytes()).hexdigest()
a=j('diagnostic-amendment.json');b=j('first-stop.json')
assert b['first']['events']==['full-registry-register-patch-entries','cached-workspace-resolve'] and b['repeat']['events']==['cached-workspace-resolve']
assert a['original_first']['raw']==b['first']['sha256'] and a['original_unchanged']['raw']==b['repeat']['sha256'] and a['zero_score_observations']==0
assert h('controller-v2.py')==a['replacement_controller'] and h('run-series-v2.py')==a['replacement_driver']
g=j('native-eligibility.json');assert g['clock_count']==0 and g['controller']==j('logger-environment.json')['controller'] and g['plan']==a['plan']
for name,e in g['gates'].items():
 assert e['eligible'] and len(e['logger'])==8;assert {(x['arm'],x['from_state'],x['tag'])for x in e['logger']}=={(a,s,t)for a in 'AB'for s in ('original','older')for t in ('first','repeat')}
 for x in e['logger']:
  assert (x['full_registry_witnesses']>0)==(x['arm']=='A' and x['tag']=='first')
  assert x['full_registry_witnesses']>0 or x['cache_reuses']>0
  assert x['work']==(2 if name=='serde'else 1)*(x['tag']=='first') and x['links']==(name=='serde'and x['tag']=='first')
e=j('logger-environment.json');assert h('controller-v3.py')==e['controller'] and h('run-series-v3.py')==e['driver'] and e['zero_scored']==0 and len(e['rows'])==4
assert {(r['arm'],r['phase'],r['full'],r['hit']) for r in e['rows']}=={(a,t,int(t=='first'),1) for a in 'AB' for t in ('first','repeat')}
print('three native admissions verified, 24 transition/repeat calls, 24 logging setup/settled calls and zero score observations')
