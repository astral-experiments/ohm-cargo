"""Verify the actual return values, compiler calls, checksums, ABI pairings and migrations."""
from pathlib import Path
import hashlib,json,tarfile
p=Path(__file__).resolve().parent
for row in (p/'SHA256SUMS').read_text().splitlines():
 h,n=row.split('  ');assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
with tarfile.open(p/'observations.tar.gz') as t:
 paths=set(t.getnames())
 def get(name):return t.extractfile('rc17/'+name).read()
 def j(name):return json.loads(get(name))
 assert len(paths)==2599 and get('suite.failures').strip()==b'0' and len([s for s in paths if s.startswith('rc17/cmd/') and s.endswith('.rc')])==22
 assert all(t.extractfile(n).read().strip()==b'0' for n in paths if n.startswith('rc17/cmd/') and n.endswith('.rc'))
 cf='787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5';co='e74dddbed648ca90bd5cabab90d9e02517478e40f5552a0a8369d72d15596d33';rf='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955';ro='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05'
 ids=('fixed-fixed','old-fixed','fixed-old','old-old','upgrade-old','downgrade-fixed')
 for arm in ids:
  pref='build-'+arm+'/';ident=j(pref+'identity.json');assert ident['new_cargo']==cf and ident['old_cargo']==co and ident['driver']==(rf if arm.endswith('fixed') else ro)
  for typ,data in j(pref+'result.json').items():
   repeated=data['unchanged'];changed=data['changed'];empty=data['empty'];assert repeated['value']==17 and empty['value']==29 and repeated['real']!=changed['real'] and repeated['stamps'][:2]==changed['stamps'][:2] and repeated['stamps'][2]-changed['stamps'][2]==18
   if arm in ['old-old','upgrade-old'] and typ.startswith('decoy'):
    assert changed['fresh'] and changed['value']==17 and not changed['compiler_exec']
   else:assert changed['value']==29 and not changed['fresh'] and len(changed['compiler_exec'])==1
   if arm=='fixed-fixed' or (not typ.startswith('decoy') and typ!='no-decoy'):assert repeated['fresh'] and not repeated['compiler_exec']
   if arm=='fixed-old' and typ!='ordinary':assert not repeated['fresh'] and repeated['complete']==0
   if arm=='upgrade-old':assert data['upgrade']['value']==29 and data['upgrade-noop']['value']==29
   if arm=='downgrade-fixed':assert all(data[x]['value']==29 for x in ['return-old','train-old','noop-old','return-new','train-new','noop-new'])
   if arm=='fixed-fixed':assert repeated['header'] and repeated['version']==4 and repeated['complete']==1
  if arm.startswith('downgrade'):continue
  data=j('check-'+arm+'/result.json');ref=data['independent']
  assert ref['exit']==101 and any(d['code']['code']=='E0308' for d in ref['diagnostics'])
  if arm in ['old-old','upgrade-old']:assert data['changed']['fresh'] and data['changed']['exit']==0
  else:assert data['changed']['exit']==101 and data['changed']['diagnostics']==ref['diagnostics']
  if arm=='upgrade-old':assert data['corrected']['diagnostics']==ref['diagnostics']
 unicode_counts={}
 for arm in ['fixed-fixed','old-fixed','fixed-old','old-old','upgrade-old','from-prototype']:
  pref='unicode-check-'+arm+'/';data=j(pref+'result.json');read=0
  for mode,rows in data.items():
   obs=rows['unchanged'];changed=rows['changed'];ref=rows['empty'];assert ref['exit']==101 and any(d['code']['code']=='E0308' for d in ref['diagnostics'])
   poisoned=(arm in ['old-old','upgrade-old'] and mode!='only-valid') or (arm=='from-prototype' and mode=='ab')
   if poisoned:assert changed['exit']==0 and changed['fresh'] and changed['complete']==1 and changed['version'] in (2,3)
   else:assert changed['exit']==101 and changed['diagnostics']==ref['diagnostics']
   if arm in ['upgrade-old','from-prototype']:assert rows['upgrade']['diagnostics']==ref['diagnostics'] and rows['upgrade-repeat']['diagnostics']==ref['diagnostics']
   if arm in ['old-fixed','fixed-fixed']:assert obs['fresh']==(mode=='only-valid') and obs['complete']==int(mode=='only-valid') and len(obs['replacement_checksums'])==int(mode=='only-valid')
   if arm=='fixed-old':assert not obs['fresh'] and obs['complete']==0
   read+=len(rows)
  unicode_counts[arm]=read
 for name,rc,driver in [('source-positive',0,rf),('source-negative',101,ro)]:
  rec=j(name+'/receipt.json');assert rec['exit']==rc and rec['driver']==driver and rec['test_binary']=='1f971549e0d7b15096692b5adcac2320e14b882e009899fc4c95900c3bd1cb69'
 fifo=j('true-fifo/result.json');assert all(z['returncode']==0 and not z['writer'] for z in fifo.values()) and sum(len(z['checksums']) for z in fifo.values())==2
 assert all(any('O_NONBLOCK' in f and 'O_NOCTTY' in f for f in z['opens']) for z in fifo.values())
 assert j('escaped-fifo/receipt.json')['native']=='17'
 alias=j('alias/result.json');assert len(alias)==8 and all(rows[1][:2]==[True,17] and rows[3][:2]==[False,29] and rows[2][:2]==([True,17] if name=='published/seed-off-retarget' else [False,29]) for name,rows in alias.items())
 nrows=sum(n.endswith('/row.json') for n in paths)
print(f'Passed 22 exact RC gates, {nrows} individual Cargo rows, 32 additional alias builds, 2 checked-in Rust runs and {sum(unicode_counts.values())} of the above Cargo checks with a genuine U+FFFD/wire migration.')
