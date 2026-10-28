"""Check every command, independent closed-form statistics, per-arm complete post-state and precommitted family."""
from pathlib import Path
import hashlib,json,math,re,runpy,statistics,sys
w=Path(__file__).resolve().parent
read=lambda n:json.loads((w/n).read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
def digest(o):return sha(json.dumps(o,sort_keys=True,separators=(',',':')).encode())
P=read('plan.json');registered=runpy.run_path(str(w/'analyze.py'))['analyze'];reference=read('native-bindings.json');result={}
for role,fp in [('primary-linux','primary.json'),('independent-linux','independent.json')]:
 s=read(fp);assert s['role']==role and s['native_before']==reference[role]['before'] and s['source_plan']=='2d40c0ba8f68ba2bfadc489db876b49f5c442de4' and s['source']==reference[role]['worker']and s['native_release_ref']==reference[role]['native_release_ref']
 for i,z in enumerate(s['rows']):
  a,b=divmod(i,8);assert (a,b,z['arm'])==(z['stratum'],z['position'],P['domains'][role]['strata'][a][b]);assert z['end']-z['start']==z['elapsed_ns']>0
  assert sha(z['complete_stdout'].encode())==z['stdout']and sha(z['complete_stderr'].encode())==z['stderr']
  if s['terminal']:
   assert z['rc']==0 and z['complete_stdout']==''and z['fresh_text']and re.fullmatch(r'\s*Finished `dev` profile \[optimized \+ debuginfo\] target\(s\) in [0-9.]+s\s*',z['complete_stderr'])
 if not s['terminal']:
  assert s['first_failure_sha256'] and s['timing_estimate']is None;result[role]={'complete':False,'captured_commands':len(s['rows']),'first_failure_sha256':s['first_failure_sha256']};continue
 assert len(s['rows'])==384 and s['post_guards']
 for k in 'AB':
  m=s['per_arm_complete_post'][k];assert m['file_count']==330 and m['raw_complete_map']==reference[role]['filemaps'][k]
 r=registered(P,role,s['rows']);es=[];pos=0;neg=0
 for i in range(48):
  b=s['rows'][8*i:8*i+8];times={c:[z['elapsed_ns']for z in b if z['arm']==c]for c in 'AB'}
  ex=1-math.exp(statistics.mean(math.log(v)for v in times['B'])-statistics.mean(math.log(v)for v in times['A']));es.append(ex)
  mul={k:math.prod(v)for k,v in times.items()};pos+=mul['A']>mul['B'];neg+=mul['B']>mul['A']
 assert (r['positive'],r['negative'])==(pos,neg)and math.isclose(r['paired_median_reduction'],statistics.median(es),rel_tol=1e-10,abs_tol=1e-14)
 order=next(z for z in range(24,0,-1)if 2*sum(math.comb(48,j)for j in range(z))<=.05*2**48)
 assert all(abs(a-b)<1e-13 for a,b in zip(r['exact_95_ci'],[sorted(es)[order-1],sorted(es)[-order]]));n=pos+neg;p=min(1,2*sum(math.comb(n,j)for j in range(min(pos,neg)+1))/2**n)
 assert r['exact_two_sided_sign_p']==p
 result[role]={'complete':True,**r}
result['both_hosts_qualify']=all(q['complete'] and q['pass']for q in result.values());print(json.dumps(result,indent=2,sort_keys=True))
