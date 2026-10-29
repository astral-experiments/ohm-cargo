"""Verify all four original/fixed packages and the separately qualified combined source."""
from pathlib import Path
import hashlib,json,subprocess,sys
r=Path(__file__).resolve().parent
def h(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def read(f):return json.loads(f.read_bytes())
mapped={}
for line in (r/'SHA256SUMS').read_text().splitlines():
 hash_,name=line.split('  ',1); f=r/name; assert not f.is_symlink() and not Path(name).is_absolute() and '..' not in Path(name).parts and name not in mapped and h(f)==hash_; mapped[name]=hash_
assert set(mapped)=={str(f.relative_to(r)) for f in r.rglob('*') if f.is_file() and f!=r/'SHA256SUMS'}
i=read(r/'index.json');products=read(r/'raw-commands.json');proof=read(r/'source-graph.json');assert [p['pr'] for p in i['origins']]==[53,66,75,147]
def parents(commit):return proof['commits'][commit]['parents']
m=i['common_helper'];assert parents(m)==[i['origins'][0]['original']];n=0
for site in i['origins']:
 p=r/f"packet-{site['pr']}";j=read(p/'source.json');a=read(p/'summary.json')
 assert h(p/'SHA256SUMS')==site['packet_sha256'] and site['original']==j['current_publication']['head']==j['local_source']['source'] and not j['current_publication']['draft'] and j['current_publication']['state']=='open'
 assert site['local_fixed']==j['local_source']['fixed'] and site['fixed_tree']==j['local_source']['tree'] and proof['commits'][site['local_fixed']]['tree']==site['fixed_tree']
 old,fixed=a['original'],a['fixed-native'];assert site['original_cargo']==old['cargo'] and site['fixed_cargo']==fixed['cargo'] and site['caller_patch_sha256']==h(p/f"site-{site['pr']}.patch")
 if site['pr']!=53:assert parents(site['helper_integration'])==[site['original'],m] and parents(site['local_fixed'])==[site['helper_integration']]
 else:assert site['helper_integration']==m and parents(parents(site['local_fixed'])[0])==[m]
 subprocess.run([sys.executable,'-IB',str(p/'verify.py')],check=True)
 data=[x for x in products if x['pr']==site['pr']]
 commands=[]
 for scanner in ('controls','earlier-compiler-controls'):
  for f in (p/scanner).glob('*.json'):
   j=read(f);rs=j.get('rows',j.get('records'));commands.extend((f.name,c['phase'],c['stdout'],c['stderr']) for c in rs)
 assert sorted(commands)==sorted((v['casefile'],v['phase'],v['stdout'],v['stderr']) for v in data)
 assert len(data)==site['cargo_fixture_commands'];n+=len(data)
assert n==76 and len(products)==76 and all(r['exit']==0 for r in products)
c=i['combined'];assert c['source']==read(r/'packet-53-combined/source.json')['fixed'] and parents(c['source'])==c['parents'] and c['tree']==proof['commits'][c['source']]['tree'] and c['manifest']==h(r/'packet-53-combined/SHA256SUMS')
subprocess.run([sys.executable,'-IB',str(r/'packet-53-combined/verify.py')],check=True)
other=read(r/'additional-source-checks.json'); assert [(x['pr'],x['test']) for x in other]==[('147','recording_a_check_hint_replaces_a_symlink'),('66','workspaces::workspace_resolve_cache_replaces_a_symlink')]
assert all(proof['ordered_ancestor_results'])
print('Four original writers verified, 76 real Cargo commands, first incompatible invocation retained, combined successor and both additional source tests verified.')
