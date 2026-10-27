"""Verify matched pre-timing whole Ruff, release-tool, external-effect and native failure witnesses."""
from pathlib import Path
import hashlib,json,tarfile
D=Path(__file__).resolve().parent
T=D/'qualification.tar.gz'
def run():
 result={'paired_calibration':{},'pydantic':{},'native_control_commands':0,'diagnostic_control_commands':0,'seeds':{}}
 with tarfile.open(T) as tf:
  load=lambda n:json.load(tf.extractfile(n))
  q=load('prepared.json');assert q['runner_sha256']=='378ff0961646713188f4c9d5fe6e1e2d99379e1d1224ff6f589686332b04207c' and q['unscored_zip_supplement']=='951eedbf82f02b20576bebfcfb8451347cb5ca310877611386abc8262213a847';result['subjects']=q['subjects']
  for arm in ('parent','candidate'):
   for view in ('original','edited'):
    z=load(f'prepare/{arm}/{view}/seed.json')['settled'];assert z['units']==z['fresh']==520 and z['totals']=={} and not z['scripts'];result['seeds'][arm+'/'+view]={'fresh':520,'unit_roster_sha256':z['unit_roster_sha256']}
   for direction in ('reverse','restore'):
    pref='prepare' if arm=='parent' else 'qualification-zstd-v1';a=f'{pref}/calibration/{arm}/{direction}';b=f'{pref}/raw-calibration/{arm}/{direction}'
    rz={}
    for label in ('preflight','change','change-next','change-next-2'):
     x=load(a+'/'+label+'/receipt.json');y=load(b+'/'+label+'/receipt.json');assert all(x[k]==y[k] for k in ('units','fresh','totals','unit_roster_sha256','rust_warnings'))
     assert sorted((v['crate'],v['kind']) for v in x['rustc'])==sorted((v['crate'],v['kind']) for v in y['rustc'])
     assert sorted((v['package'],v['sha256']) for v in x['scripts'])==sorted((v['package'],v['sha256']) for v in y['scripts'])
     assert (x['totals'].get('rustc-full',0),x['totals'].get('rustc-link-only',0),x['totals'].get('wild',0),len(x['scripts']))==((8,0,3,3) if label=='change' else ((3,0,0,0) if arm=='parent' and label!='preflight' else (0,0,0,0)))
     rz[label]={'fresh':x['fresh'],'actual_processes':x['totals'],'scripts':sorted(v['package'] for v in x['scripts'])}
    assert load(a+'/physical-snapshots.json')==load(b+'/physical-snapshots.json');result['paired_calibration'][arm+'/'+direction]=rz
   pp=f'qualification-zstd-v1/pydantic/{arm}';snap=load(pp+'/physical-snapshots.json');out={}
   for name in ('before','change','restore'):
    values=[v for p,v in snap[name].items() if p.endswith('zipped_typeshed.zip')];assert values
    exp='e67ba66ef4884603b181f9ae4605b4726a3174d0f9d0d9ad9af300314b9d5438' if name=='change' else 'ef75cf9d8fe41e26eecb4c5c937983e038f715f50bee81b7d27386876dc5b811'
    assert all(v['source_member_sha256']==exp for v in values)
    out[name]=values
   assert out['before']==out['restore'] and out['change']!=out['before']
   for direction in ('change','restore'):
    for suf in ('','-next','-next-2'):
     p=load(pp+'/'+direction+suf+'/receipt.json');full=p['totals'].get('rustc-full',0);assert full==(1 if not suf or arm=='parent' else 0) and p['units']==520 and p['fresh']==(506 if full else 520)
     assert sorted(v['package'] for v in p['scripts'])==(['ty_vendored'] if not suf else [])
     out[direction+suf+'-processes']={'full':full,'fresh':p['fresh'],'scripts':[v['package'] for v in p['scripts']]}
   result['pydantic'][arm]=out
   cases=load(f'safety/{arm}/controls/result.json');assert len(cases)==7
   for name,actions in cases.items():
    for phase,rec in actions.items():
     assert rec['correct'] and rec['stdout']==rec['expected'];z=load(f'safety/{arm}/controls/{name}/{phase}/result.json');assert z['build_returncode']==z['program_returncode']==0
     result['native_control_commands']+=1
   for cause in ('environment','outside-include'):
    actions=load(f'safety/{arm}/check-negative/{cause}/result.json');assert len(actions)==7;assert actions['edit']['diagnostics']==actions['first-unchanged']['diagnostics']==actions['empty-edited']['diagnostics'] and actions['edit']['diagnostics'][0]['code']['code']=='E0080'
    for phase,z in actions.items():
     assert z['exit']==(101 if phase in ('edit','first-unchanged','empty-edited') else 0);result['diagnostic_control_commands']+=1
 assert (result['native_control_commands'],result['diagnostic_control_commands'])==(84,28)
 return result
if __name__=='__main__':
 import sys
 z=run()
 if '--write' in sys.argv:(D/'results.json').write_text(json.dumps(z,indent=2,sort_keys=True)+'\n')
 else:assert z==json.loads((D/'results.json').read_bytes());print('All four starting states, both historical patches, raw/packaged process equivalence and 112 diagnostics/native controls verified')
