"""Verify the ordinary developer commands, complete-file link oracles, and counterexample."""
from pathlib import Path
import collections,hashlib,json,tarfile
root=Path(__file__).resolve().parent
H=lambda b:hashlib.sha256(b).hexdigest()
def archive(n):
 with tarfile.open(root/(n+'.tar.gz'))as t:return {m.name:t.extractfile(m).read()for m in t}
def read(z,s):return json.loads(next(v for n,v in z.items()if n.endswith('/'+s)))
plan=json.loads((root/'plan.json').read_bytes());armed={};ordinary={}
for tag in ('A-train-0','A-train-1','B-edit','B-repeat','A-restore','A-repeat'):
 a=archive('ordinary-'+tag);v=read(a,'result.json');jobs=read(a,'procs.json');raw=next(b for n,b in a.items()if n.endswith('/stdout'));lines=list(map(json.loads,raw.splitlines()))
 assert lines[-1]=={'reason':'build-finished','success':True}
 arts=[x for x in lines if x['reason']=='compiler-artifact'];assert len(arts)==v['units']==373
 assert sum(x['fresh']for x in arts)==v['fresh'];counts=collections.Counter(x['kind']for x in jobs);assert counts==v['physical'] and all(x['exit']==0 for x in jobs)
 if tag in ('B-edit','A-restore'):
  assert (counts['full'],counts['partial'],counts['wild'],counts['script'])==(2,0,1,1)and v['fresh']==371
  types=[x['crate_type']for x in jobs if x['kind']=='full'and x['name']=='ruff'];assert sorted(types)==['bin','lib']
 elif tag!='A-train-0': assert not counts and v['fresh']==373
 cli=next(p for p in v['deps']if p.endswith('/ruff.d'));d=v['deps'][cli];assert not d['env_deps']
 dl,=[d for k,d in v['deps'].items()if k!=cli];assert sum(x.startswith('# env-dep:RUFF_COMMIT_')for x in dl['env_deps'])==3
 head=plan['heads'][tag[0]];ver=json.loads(v['oracles']['version']['stdout'])
 assert ver['commit_info']['commit_hash']==v['head']==head and ver['commit_info']['short_commit_hash']==head[:9]
 assert v['oracles']['short_version']['stdout']=='ruff 0.17.0\n' and ver['commit_info']['commit_date']in v['oracles']['detailed_version']['stdout']
 assert v['oracles']['lint']['status']==1 and 'F821'in v['oracles']['lint']['stdout'] and v['oracles']['format']['stdout']=='x = 1\n'
 ordinary[tag]=v
for x,y in [('A-train-1','B-edit'),('B-repeat','A-restore')]:
 a,b=(ordinary[n]for n in (x,y));assert a['lib']['public']==b['lib']['public'] and a['lib']['private']!=b['lib']['private'] and a['cli']['sha256']!=b['cli']['sha256']
 left,right=({k:v for k,v in st['stored_terminal']['original'].items()if k.endswith('.o')}for st in(a,b));assert len(left)==len(right)==22 and not(set(left)&set(right))
 assert collections.Counter(map(tuple,left.values()))==collections.Counter(map(tuple,right.values()))
for name,heads in [('A-to-B','B'),('B-to-A','A')]:
 a=archive('manual-'+name);v=read(a,'result.json');assert v['same_raw']and v['same_semantics'];results=v['observed'];elf=v['natural_elf']
 assert results['partial']['elf']==results['empty_full']['elf']==elf and results['partial']['oracles']==results['empty_full']['oracles']and results['empty_full']['physically_empty_before']
 for kind in ('partial','empty-full'):
  procs=json.loads(next(raw for n,raw in a.items()if n.endswith('/'+kind+'/procs.json')))
  actual=[p for p in procs if p['image'].endswith('/toolchains/ohm/bin/rustc')];assert len(actual)==1 and actual[0]['kind']==('full'if kind=='empty-full'else'partial') and sum(v['kind']=='wild'for v in procs)==1
 for path in [k for k in a if k.endswith('/version.out')]:
  assert json.loads(a[path])['commit_info']['commit_hash']==plan['heads'][heads]
for n,activated,expanded in [('unread',0,False),('wrapped',0,False),('rawA',1,True),('rawB',1,True),('ruff-head-A',23,False)]:
 a=archive('expansion-'+n);v=read(a,'result.json');assert len(v['binary_dep_dynamic'])==activated
 assert sum('calling init:' in line for line in v['native_workload_loaded'])==activated and any(v['event_dictionary_occurrences'].values())==expanded
 if n in('rawA','rawB'):assert not v['all_env_deps']and v['runtime'].strip()==plan['heads'][n[-1]]
 if n=='wrapped':assert any('RUFF_COMMIT_HASH'in t for t in v['all_env_deps'])
for tag,expected in [('initial','old'),('settled','old'),('changed','new'),('repeat','new'),('restore','old')]:
 a=archive('constructor-'+tag);v=read(a,'result.json');assert v['runtime']==v['after']==expected
 assert v['warned']==(expected=='new')
 if tag in('changed','restore'):
  assert v['compiler']['app']['full']and v['before']!=expected and not any('env-dep:OHM_CTOR'in x for x in v['compiler']['d_inputs'])
controls=archive('physically-verified-controls');con=json.loads(controls['constructor/done.json'])
assert con['status']==0 and con['silent_first']and not con['no_custom_expansion_profile']and con['probe_dll_listed']
assert len(json.loads(controls['macro-dso-survey/records.json']))==23
print('Verified six authentic Cargo commands, two exact link/full comparisons and both types of native macro observers.')
