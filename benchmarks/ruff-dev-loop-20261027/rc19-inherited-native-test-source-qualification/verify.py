from pathlib import Path
import hashlib,json
q=Path(__file__).resolve().parent
for line in (q/'SHA256SUMS').read_text().splitlines():
 sha,fn=line.split('  ');assert hashlib.sha256((q/fn).read_bytes()).hexdigest()==sha
g=json.loads((q/'git.json').read_bytes())
assert len(g['pr_heads'])==233 and len({p['number'] for p in g['pr_heads']})==233 and g['branches']==289 and len(g['branch_names_without_cargo_sources'])==13
assert sum(g['counts'].values())==293 and g['counts']=={'no-gate':55,'current-package-only':225,'unbound':13}
assert all(len(p['module'])==1 for p in g['pr_heads'])
s=json.loads((q/'checked-in.json').read_bytes());a,b=[s['arms'][k] for k in ['matched-parent','candidate']]
assert a['test_exit']==101 and a['observed_mismatch']==[['left','17'],['right','29']] and b['test_exit']==0 and not b['observed_mismatch']
assert a['wrapped_jobs'].count('link:integration')==0 and b['wrapped_jobs'].count('link:integration')==2
assert '21 passed; 0 failed' in s['earlier_21_result']
d=json.loads((q/'deferred.json').read_bytes())
for arm in d:
 rows=d[arm]['rows'];assert len(rows)==7 and d[arm]['cargo']==s['arms'][arm]['cargo']
 assert [r['cargo_exit'] for r in rows]==[0,0,0,0,0,101,0] and [r.get('native_exit') for r in rows]==[0,0,0,83,0,None,0]
 assert [r.get('value') for r in rows]==[17,17,29,None,29,None,29] and [r['wild'] for r in rows]==[2,1,1,1,1,1,1]
 assert rows[5]['link_error'] and [p['names'] for p in d[arm]['proofs']]==[['unused']]
 for i in (1,2):assert 'accepted current unused-dependency proof' in rows[i]['deferred']
 for i in (3,5):assert 'native linker inputs require complete graph' in rows[i]['deferred'] and 'retrying complete graph' in rows[i]['deferred']
print('Verified 233 PR source heads, the staged failing and passing test, and 14 unwrapped native calls.')
