"""Verify the two original source identities, tool images and all behavioral outcomes."""
import hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
def obj(filename):return json.loads((p/filename).read_bytes())
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
paths=[]
for line in (p/'SHA256SUMS').read_text().splitlines():
 h,name=line.split('  ',1);f=p/name;assert f.is_relative_to(p) and f.is_file() and sha(f)==h;paths.append(f)
assert len(set(paths))==len(paths) and set(paths)=={f for f in p.rglob('*') if f.is_file()}-{p/'SHA256SUMS'}
source=obj('source.json');pr=source['current_publication']['pr'];origin=obj('writer-origin.json')
src=source['local_source'];assert origin['introduced_blob']['git_blob'] and not origin['parent_had_writer']
assert origin['introducing_commit']==src['source']==source['current_publication']['head'] and origin['direct_parent']==source['current_publication']['direct_parent']
assert src['caller_patch']==sha(p/f'site-{pr}.patch')
patch=(p/f'site-{pr}.patch').read_text()
assert any(x.startswith('+') and 'paths::write_atomic_no_follow' in x for x in patch.splitlines())
assert any(x.startswith('-') and 'paths::write_atomic(' in x for x in patch.splitlines())
rt=obj('runtime.json');assert rt['archive_sha256']=='d1bf93f2db9cf55b25a4c66410caf1a02e3beabecd3cbdca47d9423b9583f465' and len(rt['checked'])==66
tot=0
for arm,red in [('original',True),('fixed-native',False)]:
 img=obj(arm+'-build.json');a=obj('summary.json')[arm]
 assert img['source']==(src['source'] if red else src['fixed']) and img['tree']==(src['original_tree'] if red else src['tree'])
 assert img['source'] in img['version'] and a['cargo']==img['cargo'] and a['rustc']==rt['checked']['bin/rustc']
 assert len(a['driver'])==1 and all(rt['checked']['lib/'+k]==h for k,h in a['driver'].items())
 count=0;cases=list((p/'controls').glob(arm+'-*.json'))
 for f in cases:
  case=f.stem.removeprefix(arm+'-');j=json.loads(f.read_bytes())
  assert j['cargo']==a['cargo'] and j['compiler']==a['rustc']
  rows=j.get('rows',j.get('records'));count+=len(rows)
  assert all(r.get('exit',r.get('cargo_exit'))==0 for r in rows)
  assert all(t[1] for t in rows[-1].get('typed',rows[-1].get('cargo_units')))
  if pr in (53,66):
   assert [r['value'] for r in rows]==[17,29,29] and [r['phase'] for r in rows]==['cold','changed','repeat']
   if case=='disabled':assert j['disabled']
   else:
    assert j['sentinel_replaced']==red and j['cache_symlink']==red
    if case=='dangling':assert j['dangling'] and j['victim_existed_after']==red
    else:assert j['inode_preserved']!=red and (j['before_sha']!=j['after_sha'])==red
  elif pr==75:
   assert [r['program'] for r in rows]==[17,29,31,31] and [r['replaced_owned_sentinel'] for r in rows]==[False,red,False,False]
   assert [r['sentinel_inode_preserved'] for r in rows]==[True,not red,True,True] and [dict(r['cargo_units'])['itoa'] for r in rows]==[False,False,False,True]
  else:
   assert [r['verdict'] for r in rows]==['checked']*4 and [r['changed'] for r in rows]==[False,red and case=='enabled',False,False]
   assert all(r['inode_preserved']!=r['changed'] for r in rows)
 assert count==a['commands'] and len(cases)==a['cases']
 tot+=count
print(f'PR {pr}: original and repaired, {tot} authentic Cargo commands pass')
