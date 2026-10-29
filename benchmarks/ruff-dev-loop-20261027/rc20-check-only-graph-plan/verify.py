import collections,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
p=Path(__file__).resolve().parent
def get(n):return json.loads((p/n).read_bytes())
def hashb(d):return hashlib.sha256(d).hexdigest()
def h(n):return hashb((p/n).read_bytes())
def ident(obj):return hashb(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())
def shape(files):
 exact={};groups={}
 for n,v in files.items():
  w=Path(n).parts;assert not Path(n).is_absolute() and '..' not in w
  if 'incremental' not in w or not any(x.startswith('s-')for x in w):exact[n]=v;continue
  i,=[i for i,x in enumerate(w) if re.fullmatch('s-[0-9a-z]{10}-[0-9a-z]{7}-[0-9a-z]{25}',x)]
  assert i==w.index('incremental')+3;groups.setdefault('/'.join(w[:i]),{}).setdefault(w[i],{})['/'.join(w[i+1:])]=v
 return {'literal':exact,'incremental':{k:sorted([sorted([n,*v]for n,v in g.items())for g in gs.values()])for k,gs in groups.items()}}
order=get('order.json');replayed=subprocess.check_output([sys.executable,'-ISB',p/'order.py']);assert replayed==(p/'order.json').read_bytes()
b=get('clock-binding.json');n=get('native-v3.json');q=get('qualification.json')
for key,f in [('order_sha256','order.json'),('inner_sha256','inner-clock.py'),('host_driver_sha256','score-driver.py'),('native_sha256','native-v3.json'),('analysis','analyze.py'),('patch_sha256','ordinary-ruff.patch')]:assert b[key]==h(f)
assert b['check_seed_commitment']==n['seeds']and b['experiment_sha256']==n['experiment']and b['case_support_sha256']==n['adapter']
assert [x['pair']for x in order['pairs']]==list(range(1,81))
for case,k,ks in [('chronological',16,32),('reverse',16,32),('source-only',8,16)]:
 rr=[v for v in order['pairs']if v['case']==case];assert len(rr)==ks
 for i in range(1,k+1):assert sorted(x['order']for x in rr if x['block']==i)==['AB','BA']
rows=json.loads(gzip.decompress((p/'native-states.json.gz').read_bytes()));assert len(rows)==18
for case in ('chronological','reverse','source-only'):
 for i,phase in enumerate(('settled','edited','repeat')):
  a,bb=[rows[f'{case}-{arm}/{phase}/result.json']for arm in 'AB']
  for arm,ev in zip('AB',(a,bb)):
   assert int(ev['markers']['.ohm-check-graphs/*'])>0 and ev['markers']['.ohm-built-registry-ready']==0 and not ev['native']
   assert ident(shape(ev['rmeta']))==ev['rmeta_shape']
   assert n['shapes'][case+'-'+arm][i]=={k:ev[k]for k in n['shapes'][case+'-'+arm][i]}
   assert n['raw'][case+'-'+arm][i]==hashb((json.dumps(ev,sort_keys=True,indent=2)+'\n').encode())
  assert shape(a['rmeta'])==shape(bb['rmeta'])
  assert all(a[k]==bb[k]for k in ('artifacts','source','native','rustc','markers'))
  assert [a['resolution'],bb['resolution']]==([2,1]if phase=='edited'and case!='source-only'else[1,1])
  expected=[] if phase!='edited'else ['ruff_python_trivia'] if case!='chronological' else ['ruff_python_trivia','tinyvec','tinyvec_macros','unicode_normalization']
  assert a['rustc']==expected
for arm in 'AB':
 t=q['feature_fixture'][arm]
 assert t['default']['phases']['invalid']['graphs']==(2 if arm=='A'else 1)
 assert t['default']['phases']['invalid']['diagnostics']==['E0308']
 chk=q['ruff_check_components'][arm]
 assert all(chk[k]['diagnostics']==['E0432'] and chk[k]['code']==101 for k in ('invalid-clean','invalid-unchanged','invalid-mixed'))
for pol in ('marker','off','explicit'):
 a,bb=[q['feature_fixture'][k][pol]['phases']for k in 'AB'];assert {k:v['graphs']for k,v in a.items()}=={k:v['graphs']for k,v in bb.items()}
assert [q['ruff_native']['runs'][k]['caller']for k in ('caller-original','caller-reverted','caller-restored')]==['false','true','false']
suite=q['rust_tests'];assert any(r['arm']=='B'and len(r['tests'])==13 and r['actual']==0 for r in suite)
for g in ('warm-lock','shared'):assert sorted(r['arm']for r in suite if r['group']==g and r['actual']==101)==['A','B']
print('Verified 80 counterbalanced pairs; 18 canonical Cargo/native anchors, two complete historical directions, the source-only guard and real diagnostics. No timing data.')
