from pathlib import Path
import hashlib,json,statistics
D=Path(__file__).resolve().parent
q=json.loads((D/'observations.json').read_bytes());p=json.loads((D/'plan.json').read_bytes());rows=q['observations'];assert len(rows)==50 and q['plan']==hashlib.sha256((D/'plan.json').read_bytes()).hexdigest();assert [r['json_fresh'] for r in rows[:2]]==[182,182];assert q['cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573' and p['source_sha256']==hashlib.sha256((D/'reproduce/align.c').read_bytes()).hexdigest()
expected={1:1787150,2:554093,3:5577690};assert sum(expected.values())==p['size_unique'];order=[(1,16384),(2,16384),(1,65536),(2,65536),(3,16384),(3,65536)];assert len(p['orders'])==24 and p['orders'].count('AB')==p['orders'].count('BA')==12
for r in rows:
 assert r['rc']==0 and [(s['id'],s['request'])for s in r['streams']]==order
 for s in r['streams']:
  bits=s['request'];offset=p['offsets'][s['id']-1];assert s['issued']==(bits-offset%bits if r['arm']=='B'and bits==16384 else bits);assert s['later']==bits and s['bytes']==expected[s['id']] and s['ns']>0
results={}
for phase in ('first','second','whole'):
 a=[];b=[]
 for i,o in enumerate(p['orders']):
  g=rows[2+2*i:4+2*i];assert ''.join(r['arm']for r in g)==o
  v={r['arm']:r['elapsed_ns'] if phase=='whole'else sum(s['ns'] for s in r['streams']if s['request']==(16384 if phase=='first'else 65536))for r in g};a.append(v['A']);b.append(v['B'])
 ds=[x-y for x,y in zip(a,b)];results[phase]={'median_A_ns':statistics.median(a),'median_B_ns':statistics.median(b),'paired_saving_ns':statistics.median(ds),'favorable':sum(n>0 for n in ds)}
assert results['first']['paired_saving_ns']==1870308 and results['first']['favorable']==24
assert results['second']['paired_saving_ns']==-8672 and results['second']['favorable']==10
assert results['whole']['paired_saving_ns']==4918775 and results['whole']['favorable']==20
p=json.loads((D/'profile.json').read_bytes());assert p['resolved_whole_Cargo_AVX2_ir']==59076207 and p['resolved_whole_Cargo_AVX2_calls']==7162
print(json.dumps(results,indent=2,sort_keys=True))
