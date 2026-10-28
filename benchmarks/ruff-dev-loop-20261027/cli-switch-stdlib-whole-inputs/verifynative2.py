"""Reparse every historical selector/edit observation. Require real product and ordinary CLI oracles."""
from pathlib import Path
import ast,collections,re,itertools,json,hashlib,sys,os
import native3 as n
r=n.repo;H=n.H
def take(st,phase,pkg):
 d=r/f'{st}-{phase}-{pkg}';res=n.load(d/'result.json');pro=n.load(d/'products.json');units=n.load(d/'units.json')
 assert res['selector']==pkg and res['source_bytes']==n.binding['source_blobs'][res['source']]
 assert len(units)==res['units'] and sum(v['fresh']for v in units)==res['fresh']
 assert n.sha(d/'stdout')==res['raw_stdout_sha']and n.sha(d/'stderr')==res['raw_stderr_sha']
 sem={}
 for key,c in res['runtime'].items():
  so=(d/(key+'.stdout')).read_bytes();se=(d/(key+'.stderr')).read_bytes();assert H(so)==c['stdout_sha']and H(se)==c['stderr_sha']
  # Compare diagnostics at the same logical fixture filename. All other text/positions remain unmodified.
  normalized=so.replace(str(d/'typing.py').encode(),b'<sample>/typing.py');assert normalized.count(b'<sample>')<=1
  sem[key]={'status':c['exit'],'stdout_sha':H(so),'stderr_sha':H(se),'source_filename_only_normalized_sha':H(normalized),'semantic_text':normalized.decode(),'stderr_text':se.decode()}
 assert set(sem)=={'version','behavior314','behavior315'}
 return d,res,pro,units,sem
def rustc_rows(d,result,products,units):
 out=[];pids=set()
 for row in (v for v in result['native']if v['role']=='full'):
  raw=(d/row['pid']).read_bytes();assert H(raw)==row['raw_sha256'];matches=[]
  for line in raw.decode().splitlines():
   m=re.match(r'^execve\((".*?"), (\[.*\]), .* = 0$',line)
   if not m:continue
   argv=ast.literal_eval(m[2])
   if H(json.dumps(argv,separators=(',',':')).encode())==row['argv_sha256']:matches.append(argv)
  a,=matches;md=row['unit_id'];name=row['crate'];src=row['source']
  assert row['pid']not in pids;pids.add(row['pid'])
  direct={};o={}
  for j,k in enumerate(a[:-1]):
   if k=='--extern' and '='in a[j+1]:
    n,fn=a[j+1].split('=',1);direct.setdefault(n,[]).append([Path(fn).name,products.get(fn,{}).get('sha')])
   if k=='-C':
    v=a[j+1];o[v.split('=',1)[0]]=v.split('=',1)[1]if '='in v else True
  if 'extra-filename' in o:assert o['extra-filename']=='-'+md
  else:assert a[a.index('--crate-type')+1]=='bin' and src.endswith('/main.rs') and 'metadata'in o
  files=[v for v in units if not v['fresh'] and v['name']==name and any(md in Path(f).name for f in v['files'])]
  if not files:files=[v for v in units if not v['fresh'] and v['name']==name and 'bin' in v['kind']and src.endswith('/main.rs')]
  combo,=files;paths=sorted(set(k for k in combo['files']if k in products));assert paths,(name,combo,md)
  out.append({'name':name,'unit':md,'argv_sha':row['argv_sha256'],'raw_trace':row['raw_sha256'],'source':src,'features':combo['features'],'codegen_flags':o,'direct_externs':direct,'outputs':paths})
 return sorted(out,key=lambda z:z['unit'])
labels={};nominal={};diffs={};no_input_outputs=[]
for state in ('R-T','T-R'):
 hist={}
 for tag in ['original','first-edit','repeat-edit','restore','repeat-restore']:
  name=state+'/'+tag;hist[tag]={}
  for prog in ('ruff','ty'):
   d,z,prod,us,sem=take(state,tag,prog)
   before=take(state,'original' if tag in ('original','first-edit','repeat-edit') else 'first-edit',prog)[2]
   assert before.keys()==prod.keys()
   jobs=rustc_rows(d,z,prod,us)
   facts=[]
   for v in jobs:
    paths=v.pop('outputs')
    pp=[{'path':Path(f).name,'prior':before[f]['sha'],'after':prod[f]['sha'],'size':prod[f]['size']} for f in paths]
    facts.append({**v,'products':pp})
    if all(k['prior']==k['after']for k in pp):no_input_outputs.append([state,tag,prog,v['name'],v['unit']])
   labels[name+'/'+prog]={'fresh':z['fresh'],'units':z['units'],'native':z['physical'],'jobs':facts,'cli':z['cli']['sha'],'runtime':sem,'physical_process_sha':H(json.dumps(z['native'],sort_keys=True).encode()),'stdout_sha':z['raw_stdout_sha'],'stderr_sha':z['raw_stderr_sha']}
   hist[tag][prog]=set(v['unit'] for v in jobs)
   assert len(jobs)==z['physical'].get('full',0)
   if tag in ('first-edit','restore'):
    assert z['physical']['wild']==1
    if z['cli']['sha']==before[z['cli']['path']]['sha']:no_input_outputs.append([state,tag,prog,'wild-terminal-same',prog])
   else:assert not z['physical'] and z['units']==z['fresh']
  for prog in ('ruff','ty'):
   assert len(hist[tag][prog])==len(labels[name+'/'+prog]['jobs'])
  assert not(hist[tag]['ruff']&hist[tag]['ty'])
  if tag in ('first-edit','restore'):assert len(hist[tag]['ruff']|hist[tag]['ty'])==18
  diff=labels[name+'/ruff']['jobs']+labels[name+'/ty']['jobs']
  diffs[name]={k:[{t:v[t]for t in ('unit','codegen_flags','direct_externs','features')}for v in diff if v['name']==k]for k,count in collections.Counter(v['name']for v in diff).items()if count>1}
  if 'ty_module_resolver'in diffs[name]:
   aa,bb=diffs[name]['ty_module_resolver'];assert aa['unit']!=bb['unit']and aa['codegen_flags']['metadata']!=bb['codegen_flags']['metadata']
  nominal[name]=sorted(k for k in hist[tag]['ruff']|hist[tag]['ty'])
out={'observation_counts':{'alternated_commands':20,'distinct_compiler_units_per_edit_or_restore':18},'orders':labels,'unit_sets':nominal,'repeated_names_different_units':diffs,'unchanged_all_reported_paths':no_input_outputs}
for state in ('seed','gold'):
 tag='original'if state=='seed'else'first-edit';probes={}
 for prog in ('ruff','ty'):
  d,m,prod,units,sm=take(state,'settle-1',prog);assert not m['native'] and m['units']==m['fresh'];cases={};key=m['cli']['path']
  for direction in ('R-T','T-R'):
   d2,m2,p2,_,s2=take(direction,tag,prog)
   assert all([v['status'],v['source_filename_only_normalized_sha'],v['stderr_sha']]==[s2[k]['status'],s2[k]['source_filename_only_normalized_sha'],s2[k]['stderr_sha']]for k,v in sm.items())
   cases[direction]={'same_cli_bytes':m2['cli']['sha']==m['cli']['sha'],'raw':[m2['cli']['sha'],m['cli']['sha']],'same_products':sum(prod[k]['sha']==p2.get(k,{}).get('sha')for k in prod),'whole_products':len(prod),'same_behavior_and_diagnostics':True}
  probes[prog]=cases
 out[state+'_oracles']=probes
# Preserve h3-specific raw paths privately; a public report includes only source labels and input basenames.
n.dump(r/'verified-609e.json',out)
print(json.dumps({'unchanged_reported':no_input_outputs,'oracles':{s:out[s+'_oracles']for s in ('seed','gold')},'sha':n.sha(r/'verified-609e.json')},sort_keys=True))
