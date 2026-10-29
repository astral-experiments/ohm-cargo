"""Independently decode every measured ordinary command from the original terminal native event clocks."""
from pathlib import Path
import argparse,hashlib,json,re,runpy

root=Path(__file__).resolve().parent
schedule=runpy.run_path(str(root/'screen.py'))
window=runpy.run_path(str(root/'window.py'))
names=runpy.run_path(str(root/'name_oracle.py'))
R=sorted('ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value'.split())
def digest(o):return hashlib.sha256(o).hexdigest()
def check(r):
 assert r['no_replacements'] and r['schedule']==[list(x)for x in schedule['schedule']('milan')]
 assert r['grant_sha256']=='b9243fe575b5e98131f32677ce3ba3a81b158773a45fdf68dff6421ac1e85b7e'
 assert r['prepared_sha256']=='0a5252a7911761b7dc66287efce56942a77c7d5b8a2382878edaf9afc3b6b96d'
 assert r['grant']['genoa_native_sha256']=='165c876d4d9050b7f80f5688ca8135b75a7976b521a8940ed97d2f5214b2577b'and r['grant']['milan_native_sha256']=='36f81452fe7d4b51bc3fbab1768ede3558faf5b0f5b1c02a113d1f701921be02'
 assert r['enrolled_bidirectional_golden']['parent']['archive_sha256']=='80f07ae75685b8fc2f39e5a4d401d0b84b2a557a0114c02cbd0bb1f75133b322'
 assert r['enrolled_bidirectional_golden']['historical']['archive_sha256']=='8f70068d10b763a31ea84bc6f36fc65d19010366bdec9b5ecb9edcf149599eea'
 order=[(i,k,a)for i,(o,k)in enumerate(r['schedule'],1)for a in o]
 complete=[]
 by_pair={}
 previous={a:r['initial_sha256']for a in 'AB'}
 for n,e in enumerate(r['all_16_slots']):
  i,k,a=order[n];assert(i,k,a)==(e['pair'],e['direction'],e['arm'])
  for phase in ('edit','repeat'):
   v=e[phase]
   for step in ('out','err'):
    if step not in v:continue
    log=v[step];assert e['raw_files'][phase+'.'+step]==log['original_sha256']
    if not any(z in log['text']for z in ['<toolchain-stage>','<canonical-build>','<ruff>','<study>','<home>','<scratch>']):
     assert digest(log['text'].encode())==log['original_sha256']
   if 'watch' in v:
    assert isinstance(v['watch']['returncode'],int) and v['watch']['command_ns']>=0
    assert digest((json.dumps(v['watch'],sort_keys=True,indent=2)+'\n').encode())==e['raw_files'][phase+'-events.json']
  if 'after' not in e:continue
  assert len(complete)==n
  after=e['after'];base=e['result'];assert base['mode']=='ordinary'and base['source']==k and base['arm']==a and after['registered']==r['prepared_sha256']
  bounds={}
  for phase in ('edit','repeat'):
   w=e[phase]['watch']; rolled=window['bounds'](w,phase=='edit'); parts=base['phases'][phase]
   assert parts['bounds']==rolled and parts['ns']==w['command_ns']==after[phase+'_ns']
   assert parts['stdout']==e[phase]['out']['original_sha256'] and parts['stderr']==e[phase]['err']['original_sha256']
   jobs=sorted(re.findall(r'^\s*Compiling ([A-Za-z0-9_-]+) v',e[phase]['err']['text'],re.M))
   assert jobs==parts['dirty']==(R if phase=='edit'else[])
   assert w['returncode']==0 and w['observer_cpu_ns']>=0
   if phase=='edit':
    assert rolled['lo']==after['archive_lower_ns']and rolled['hi']==after['archive_upper_ns']
    keys=names['by_stem']([v['name']for v in w['objects']])
    assert len(keys)==256 and after['oracle']['current_nonce']==next(iter(keys.values())).decode()
    assert after['oracle']['names_sha256']==digest(b'\0'.join(sorted(v['name'].encode()for v in w['objects'])))
   else:assert not w['objects']and not w['events']
  literal=e['products']['native-literal.json']
  assert after['oracle']==literal and literal['literal_equal'] and literal['fields']==512 and literal['objects']==256
  assert base['rlib_sha256']==after['rlib_sha256']==literal['actual_sha256']==literal['expected_sha256']==e['products']['before-reading-current.json']['predicted']==e['raw_files']['verified-current.rlib']
  assert base['prior_sha256']==after['prior_sha256']==previous[a] and after['rlib_sha256']!=previous[a];previous[a]=after['rlib_sha256']
  assert literal['reference_sha256']==r['enrolled_bidirectional_golden'][k]['archive_sha256']
  assert e['products']['before-reading-current.json']['inotify']==e['raw_files']['edit-events.json']
  assert base['caller']==e['products']['caller/result.json'] and base['caller']['executable']==after['true_reader_sha256']==r['enrolled_bidirectional_golden'][k]['caller']==e['raw_files']['caller/lint-cli']
  assert base['caller']['exit']==0 and after['caller']==([2,3,4]if k=='parent'else[1])and base['caller']['stdout']==''.join(f'{v} SIM222\n'for v in after['caller'])
  assert after['typed_path_count']==452
  assert all(v[label]>=floor for v in (after['before'],after['after'])for label,floor in [('home',25*2**30),('scratch',25*2**30),('image',2*2**30)])
  by_pair.setdefault(i,{'direction':k,'order':e['order'],'roster_verified':True,'native_verified':True})[a]=after
  complete.append((i,a))
 assert sum('watch'in v[s]for v in r['all_16_slots']for s in ('edit','repeat'))==r['actual_started_commands']
 for stem,seal in r['pair_seals'].items():
  i=int(stem.split('-')[1].split('.')[0]);assert set(by_pair[i])>={'A','B'}
  for k in 'AB':
   e=next(v for v in r['all_16_slots']if v['pair']==i and v['arm']==k)
   assert seal['roles'][k]==e['raw_files']['after.json']
 if r['terminal_exit']==0:
  assert len(complete)==16 and len(r['pair_seals'])==8 and r['actual_started_commands']==32
  x=schedule['screen']('milan',[by_pair[k]for k in range(1,9)])
  assert x==r['score']
  return x
 assert r['score']is None
 return {'terminal_exit':r['terminal_exit'],'verified_slots':len(complete),'complete_pairs':len(r['pair_seals']),'recorded_command_results':r['actual_started_commands'],'effect_calculated':False}
if __name__=='__main__':
 args=argparse.ArgumentParser();args.add_argument('file',type=Path,nargs='?',default=root/'results.json');r=args.parse_args()
 print(json.dumps(check(json.loads(r.file.read_bytes())),sort_keys=True,indent=2))
