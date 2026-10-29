from pathlib import Path
import hashlib,itertools,json,re,statistics
P=Path(__file__).resolve().parent
def rd(n):return json.loads((P/n).read_bytes())
def raw_sha(n):return hashlib.sha256((P/n).read_bytes()).hexdigest()
for l in (P/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert raw_sha(n)==h,n
term=rd('result.json');cfg=rd('registration.json');rows=term['raw'];logs=rd('commands.json');native=rd('native.json');cal=rd('calibrations.json');b=rd('source-bindings.json')
assert len(rows)==len(logs)==36 and b['protocol']=='aca896deb46d9df97c04264c9f2118081f35da6010b6d6b7ab09cf5091f3459e' and b['instruction_observer']==raw_sha('reproduce/counter.c')
for role in 'ABC':
 c=cal[role];assert c['sites']==cfg['site_rvas'][role] and c['actual']==cfg[role];qs=c['observations']
 for mode in ('thread','c','multi','inclusive'):
  lo,hi=[qs[mode+'-'+str(n)] for n in (1000,2001000)];delta=hi['ir']-lo['ir']
  if mode=='thread':assert abs(delta-4_000_000)<40_000
  if mode in ('c','multi'):assert abs(delta)<100_000
  if mode=='inclusive':assert (lo['inclusive'],hi['inclusive'])==(3004,6003004) and lo['suffix']==hi['suffix']==lo['finished']==hi['finished']==1
 for k,v in native.items():
  if k.startswith(role) and isinstance(v.get('reported'),dict):assert (v['reported']['units'],v['reported']['fresh'],v['reported']['products'],v['reported']['map'],v['reported']['physical_execs'])==(147,147,265,cfg['seed'],['proxy','cargo'])
 for phase in ('before','final'):
  assert sorted(x['names'] for x in native[role+'-behavior-'+phase+'/behavior.json']['tests'].values())==[1,558]
  assert native[role+'-conflict-'+phase+'/conflict.json']['errors']==[cfg['common_clean']['matched_triple_conflict']]
for row in rows:
 a=row['a'];i=row['block'];d=row['direction'];name='b%02d-%s-%s-unchanged'%(i,d,a);v=logs[name];r=[x.split() for x in v['counts']];tid=r[0][1];assert r[0][0]=='B' and r[-1]==['P',tid];ent=[x[1] for x in r if x[0]=='T'];ex=[x for x in r if x[0]=='F'];assert len(ent)==len(set(ent))==3 and sorted(ent)==sorted(x[1] for x in ex)
 ir,hit,fp,inc,finished,live=[sum(int(x[k]) for x in ex) for k in range(2,8)];assert (ir,hit,fp,inc,finished,live)==(row['ir'],int(a=='B'),1,row['inside_suffix_ir'],hit,0)
 assert not v['forked_processes'] and all(str(x[0])==tid for x in v['kernel_execs']) and [q for q in v['kernel_threads'] if not q[2]]==[] and v['physical_cargo']==cfg[a] and v['status']==0 and v['source_sha']==cfg['P' if d=='reverse' else 'H']
 t0,t1=v['monotonic_ns'];assert t1-t0==v['elapsed_ns_instrumented_only'] and t1>t0
for direction in ('reverse','restore'):
 assert set(cfg['order'][direction])==set(map(''.join,itertools.permutations('ABC')))
 group=[r for r in rows if r['direction']==direction];assert len(group)==18
 for pair in ('AB','AC','BC'):
  vals=[]
  for i in range(1,7):
   subset=[r for r in group if r['block']==i];assert ''.join(r['a'] for r in subset)==cfg['order'][direction][i-1];ab={r['a']:r['ir'] for r in subset};vals.append((ab[pair[0]]-ab[pair[1]])/ab[pair[0]])
  j=term['scores'][direction][pair];assert j['values']==vals and j['median']==statistics.median(vals) and j['favorable']==sum(x>0 for x in vals)
 frac=[v['inside_suffix_ir']/v['ir'] for v in group if v['a']=='B'];assert statistics.median(frac)==term['scores'][direction]['B_scope_fraction']['median']
s=term['scores'];criteria=s['restore']['BC']['median']>=.01 and s['restore']['BC']['favorable']>=5 and all(s[d]['AC']['median']>=-.02 for d in ('restore','reverse'));assert criteria==term['recommend_ordinary_wall']
print('Verified all 36 independent parent instruction rows and process/thread ledgers, 24 toy controls, complete 147-unit/265-file and native behavior gates, and the original follow-on criterion.')
