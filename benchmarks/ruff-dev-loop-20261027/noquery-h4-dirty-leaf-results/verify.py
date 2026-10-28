"""Independently validate every scored call and reference, then recompute the registered block analysis."""
from pathlib import Path
from collections import Counter
import csv,gzip,hashlib,io,json,re,sys
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here));from analyze import evaluate
from design import schedule
h=lambda x:hashlib.sha256(x).hexdigest();read=lambda n:json.loads((here/n).read_bytes())
def native(r):
 out=[]
 for k in r['members'] or []:
  if k['kind']=='codegen':
   m=re.fullmatch(r'(ruff_text_size-[0-9a-f]{16}\.[0-9a-z]+)\.[0-9a-z]+(\.rcgu\.o)',k['label']);assert m
   out.append((m[1]+m[2],k['size'],k['sha']))
  elif k['kind']=='lib.rmeta-link':
   assert k['label']==k['kind'];out.append((k['label'],k['size'],k['exact_member_names_folded']))
  else:
   assert k['label']==k['kind']=='lib.rmeta';out.append((k['label'],k['size'],k['sha']))
 assert not out or [x['kind'] for x in r['members']]==['lib.rmeta','lib.rmeta-link','codegen','codegen']
 return (r['outputs']['.rmeta'],out,r['ordinary_api'],r['source'],r['checksummed_sources'],r['foreign_marker'],r['depinfo_sha256'])
if (here/'SHA256SUMS').exists():
 for row in (here/'SHA256SUMS').read_text().splitlines():
  sig,name=row.split('  ');assert Path(name).name==name and sig==h((here/name).read_bytes())
terminal=read('terminal.json');reg=terminal['authority'];assert reg['upstream_registration']=='869cb9b4d76cf2864efaa32e60f60c31b7ac0969' and reg['native_admission']=='9ea6f62e8e3a96a49f9d80a62f516afd532602ce' and reg['source_provenance']=='4fa4cc2e5f3256b57e5b6e7b1c70ce0d32456061'
assert terminal['exit_code']==0 and terminal['commands']==5184 and terminal['terminal']['times']==h((here/'wall.csv').read_bytes())
assert terminal['activation_sha256']=='81d885091186a0c3b445587e74b2714b3ad2780ce2454989506bcf189eb505f6'
ref=json.loads(gzip.decompress((here/'accepted-native.json.gz').read_bytes()));assert ref['binding']==terminal['terminal']['binding']=='f3e6f93431a3af20a422171dfd6e3f49649d0f6eedb7148cb003c0a11d126e81'
natives={}
for kind in ('check','build'):
 for direction in ('edit','restore'):
  rr=[native(ref['controls'][kind+'-'+a][direction]) for a in ('B','P','N','B2','P2','N2')]
  assert rr==rr[:1]*6;natives[kind,direction]=rr[0]
for v in read('pre-post.json').values():
 t=v['actual_processes'];assert not t['jobs'] and not t['observer_probes'] and len(v['raw_trace_files_sha256'])>0
assert len(read('pre-post.json'))==terminal['actual_before_and_after_fresh_qualified_commands']==12
with (here/'wall.csv').open(newline='') as f:times=list(csv.DictReader(f))
observations=gzip.decompress((here/'rows.jsonl.gz').read_bytes()).splitlines();assert len(observations)==len(times)==5184
counts=Counter();callers=set();codes=Counter()
for raw,t in zip(observations,times,strict=True):
 row=json.loads(raw);slot=row['slot'];assert all(str(x)==t[n] for n,x in slot.items()) and set(slot)==set(t)-{'elapsed_ns'}
 k,d,a=slot['kind'],slot['direction'],slot['arm'];r=row['observation'];assert r['elapsed_ns']==int(t['elapsed_ns']) and r['trace'] is None and not r['fresh'] and r['units']==1 and native(r)==natives[k,d]
 cc=row['cargo_and_external_oracle_commands'];assert [x['inside_cargo_timer'] for x in cc]==[True]+[False]*(len(cc)-1)
 assert len(cc)==(3 if k=='build' and d=='restore' else 2) and [x['status'] for x in cc]==([0,1] if d=='edit' else [0]*len(cc))
 assert all(len(x['stdout'])==len(x['stderr'])==64 for x in cc)
 cat=row['cargo_artifact'];assert cat['name']=='ruff_text_size' and cat['kind']==['lib'] and cat['artifacts'] and all(re.fullmatch(r'libruff_text_size(?:-[0-9a-f]{16})?\.(rmeta|rlib)',s) for s in cat['artifacts'])
 if d=='restore':
  sha0=r['native_caller_file_sha256'];assert len(sha0)==64;callers.add(sha0)
  if k=='build':assert r['ordinary_api']=={'rc':0,'ordinary_output':'2-6'} and cc[2]['stdout']==h(b'2-6\n')
  else:assert r['ordinary_api']=={'rc':0,'metadata':True}
 else:assert r['ordinary_api']=={'rc':1,'code':'E0599'} and 'native_caller_file_sha256' not in r
 assert not r['foreign_marker'] and r['checksummed_sources']==4
 counts[k,a]+=1;codes[k,d]+=1
assert callers==set(terminal['retained_caller_sha256'])
assert counts=={(k,a):n for k,n in [('check',1584),('build',144)] for a in 'BPN'}
result=evaluate(schedule(),times);assert read('analysis.json')==result
print(json.dumps({'ordinary_dirty_cargo_commands':5184,'blocks':24,'paired_check_edits':1584,'paired_build_edits':144,'native_admission':60,'pre_and_post_settled':12,'all_output_and_registered_order_guards':True,'passes_baseline_overhead':result['passes_baseline_overhead'],'reproduces_build_probe_effect':result['reproduces_build_probe_effect'],'elapsed_data_sha256':terminal['terminal']['times']},sort_keys=True,indent=2))
