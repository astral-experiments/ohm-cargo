"""Verify chronology, individual waits, all program oracles and every analysis row."""
from pathlib import Path
import collections,copy,gzip,hashlib,json,re,statistics,sys
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));from analyze import calculate
def load(n):
 raw=(ROOT/n).read_bytes()
 return json.loads(gzip.decompress(raw)if n.endswith('.gz')else raw)
def sha(b):return hashlib.sha256(b).hexdigest()
def verify(pairs=None):
 p=load('protocol.json');b=load('binding.json.gz');cap=load('timer.json.gz');native=load('native.json.gz');products=load('products.json')
 assert b['protocol']==sha((ROOT/'protocol.json').read_bytes())=='85b654185b85e9b71e49c7369c0cd4aa9bd9f4ad1cd8cb4e518501a84745e1cf' and b['analysis']==sha((ROOT/'analyze.py').read_bytes()) and b['implementation']==sha((ROOT/'worker.py').read_bytes())
 assert b['zero_clock_admission']==0 and b['frozen_admission']=='3d27e9a932a076ae79cd4afa2ad6adebdba41eef1335fa1ae24017232ebf4949' and b['terminal']=='b8d59fb4b4422381b1ebd7c5fc2a44a195c4910fa4ac3262981042f5baba3989'
 ids=[tuple(v[k])for v in b['seed']['independent_state_inodes'].values()for k in ('products','shared')];assert len(set(ids))==6 and b['seed']['count']==59
 assert all(r['read_only']and r['exit']==0 and r['euid']==1000 and r['verdict']=='17 29 12'and r['stdout']==sha(b'17 29 12\n')and r['stderr']==sha(b'')for r in products.values())
 witness={'.'+k:x['sha256']for k,x in products['C']['files'].items()if k in ('rmeta','rlib')}
 assert sorted(witness.values())==sorted(b['seed']['files'].values())
 for a in 'CAB':
  f=products[a]['files']
  assert f['caller']['sha256']==b['seed']['caller'] and all(f[k]['sha256']==p['toolchain'][k]for k in ('rustc','wild'))and f['cargo']['sha256']==p['toolchain']['candidate'if a=='B'else'baseline'] and f['lock']['sha256']==p['toolchain']['lockfile'] and f['manifest']['sha256']==p['historical']['original']and all(f[k[1:]]['sha256']==v for k,v in witness.items())
 assert len(native)==22
 for r in native.values():
  a=r['arm'];phase=r['flank'];cold=phase=='common-cold';assert r['files']==witness and r['consumer']==b['seed']['caller']and r['consumer_value']=='17 29 12' and r['roster']==['ruff_text_size',['lib'],[]]and r['fresh']==(not cold)and r['cargo_exit']==0
  assert [v[2]for v in r['execs'][:2]]==['launch','launch'] and r['work']==([['rustc','ruff_text_size']]if cold else[])and (sum(v[2]=='source-ruff_text_size' for v in r['execs']),len(r['execs'])==2)==(int(cold),not cold)
  if phase.startswith(('pre-','post-')):assert (r['marker'][0]!=r['marker'][1])==(phase.split('-',1)[1] in ('reverse','restore'))
 assert cap['resolution_ns']<=1000 and len(cap['rows'])==28 and [x['pid']for x in cap['rows']]==cap['waits']['actual_blocking_kernel_pids']
 raw=cap['kernel'];assert sha(raw.encode())==cap['waits']['raw']
 starts=[int(re.match(r'wait4\((\d+), .*?, 0, NULL\)\s+=\s+(\d+)$',l)[1])for l in raw.splitlines()if l.startswith('wait4(')]
 assert starts==cap['waits']['actual_blocking_kernel_pids']
 for d in (0,5,15,25):
  ns=[x['ns']for x in cap['rows']if x['delay_ms']==d];assert len(ns)==7 and cap['medians_ms'][str(d)]==statistics.median(ns)/1e6
 assert all(r['status']==0 and r['ns']==r['ended_ns']-r['started_ns']for r in cap['rows'])
 if pairs is None:pairs=load('pairs.json.gz')
 assert len(pairs)==len(p['schedule'])==32 and [r['pair']for r in pairs]==list(range(1,33))
 pids=set();last=0;errors=load('observed-stderr.json.gz')
 assert all(sha(s.encode())==k and 'Finished' in s and all(m not in s for m in ('Compiling','Checking','Running ','error:'))for k,s in errors.items())
 for r,reg in zip(pairs,p['schedule']):
  assert {k:r[k]for k in reg}==reg and set(r['arms'])==set('AB')
  for a in r['order']:
   child=r['arms'][a]
   assert min(child['room'][:2])>24*2**30 and child['room'][2]>16*2**30
   assert child['files']==witness and child['consumer']==b['seed']['caller']and child['lock']==p['toolchain']['lockfile']and child['source_sha']==p['historical']['reversed'if r['direction']=='reverse'else'original']
   assert child['tool']==p['toolchain']['candidate'if a=='B'else'baseline']
   before,mid,after=child['marker'];assert before!=mid==after and [before,mid]==native[a+'/pre-'+r['direction']]['marker']
   for k in ('edit','repeat'):
    v=child[k];assert v['status']==0 and v['pid']not in pids and v['started_ns']>=last and v['ended_ns']-v['started_ns']==v['ns']>0
    last=v['ended_ns'];pids.add(v['pid']);assert child['streams'][k+'.stdout']==sha(b'')and child['streams'][k+'.stderr']in errors
 assert len(pids)==128 and sum(len(v['arms'])for v in pairs)==64
 assert collections.Counter((v['direction'],v['order'])for v in pairs)=={(d,o):8 for d in ('reverse','restore')for o in ('AB','BA')}
 assert calculate(pairs,p)==load('statistics.json')
if __name__=='__main__':
 verify()
 if '--self-test'in sys.argv:
  base=load('pairs.json.gz')
  for kind in ('pid','clock','missing','wrong-image','verdict','order'):
   rr=copy.deepcopy(base);arm=rr[0]['arms']['A'];v=arm['edit']
   if kind=='pid':v['pid']=arm['repeat']['pid']
   elif kind=='clock':v['ns']+=3
   elif kind=='missing':rr.pop()
   elif kind=='wrong-image':arm['tool']='0'*64
   elif kind=='verdict':arm['consumer']='0'*64
   else:rr[0]['order']=rr[0]['order'][::-1]
   try:verify(rr)
   except AssertionError:pass
   else:raise RuntimeError('accepted '+kind)
 print('32 pairs, 128 clocks, 28 proven blocking timer waits, 22 native Cargo controls, three read-only final product executions and complete paired analysis verified.')
