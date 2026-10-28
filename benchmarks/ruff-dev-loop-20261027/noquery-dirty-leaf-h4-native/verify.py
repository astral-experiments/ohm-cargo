from pathlib import Path
import gzip,hashlib,json
p=Path(__file__).resolve().parent;raw=gzip.decompress((p/'observations.json.gz').read_bytes());b=(p/'binding.json').read_bytes();z=json.loads(raw);sha=lambda x:hashlib.sha256(x).hexdigest();binding=json.loads(b)
assert sha(b)==z['binding']=='f3e6f93431a3af20a422171dfd6e3f49649d0f6eedb7148cb003c0a11d126e81'
assert [binding['cargo'][a]['sha256'] for a in 'BPN']==['0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2','03c851e44a863bb0d2cb8c9a98df1eef33310c8f3fbc77cdbb48aee516e68400','d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde']
assert binding['common_driver']['sha256']=='ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99'
import re
def native(r):
    members=[]
    for x in r['members'] or []:
        if x['kind']=='codegen':
            m=re.fullmatch(r'(ruff_text_size-[0-9a-f]{16}\.[0-9a-z]+)\.[0-9a-z]+(\.rcgu\.o)',x['label']);assert m,x['label']
            members.append((m[1]+m[2],x['size'],x['sha']))
        elif x['kind']=='lib.rmeta-link':
            assert x['label']=='lib.rmeta-link';members.append((x['label'],x['size'],x['exact_member_names_folded']))
        else:
            assert x['kind']==x['label']=='lib.rmeta';members.append((x['label'],x['size'],x['sha']))
    assert not members or [x['kind'] for x in r['members']]==['lib.rmeta','lib.rmeta-link','codegen','codegen']
    return dict(meta=r['outputs']['.rmeta'],members=members,api=r['ordinary_api'],source=r['source'],checksums=r['checksummed_sources'],marker=r['foreign_marker'],depinfo=r['depinfo_sha256'])

cases={};phases={'original','edit','restore','unchanged_edit','unchanged_restore'}
for kind in ['check','build']:
 for arm in 'BPN':
  key=kind+'-'+arm;tot={'commands':0,'fresh':0,'real_rustc':0,'observer_capability':0}
  for name in [key,key+'2']:
   data=z['controls'][name];assert set(data)==phases
   for phase,v in data.items():
    fresh=phase.startswith('unchanged');edited=phase in ('edit','unchanged_edit');tr=v['trace']
    assert v['units']==1 and v['foreign_marker'] is False and v['checksummed_sources']==4 and v['fresh']==fresh
    assert len(tr['jobs'])==int(not fresh) and all(j['crate']=='ruff_text_size' for j in tr['jobs']) and tr['observer_probes']==(int(not fresh) if arm=='P' else 0)
    assert v['source']==('097615fdf261460b1c30900d535bb5bde4ab709a402d4850b49820a6923b0771' if edited else 'f61f9d66ec9dcc29bac8067dd4d5910db6b7e52009ef7cc976ac0478c6800c52')
    assert v['outputs'].get('.rmeta') and (v['ordinary_api']['rc']==1 if edited else v['ordinary_api']['rc']==0)
    tot['commands']+=1;tot['fresh']+=fresh;tot['real_rustc']+=len(tr['jobs']);tot['observer_capability']+=tr['observer_probes']
  assert list(tot.values())==[10,4,6,6 if arm=='P' else 0];cases[key]=tot
 for ph in phases:
  rows=[z['controls'][kind+'-'+a][ph] for a in ('B','P','N','B2','P2','N2')]
  assert len({r['outputs']['.rmeta'] for r in rows})==1 and len({json.dumps(r['ordinary_api'],sort_keys=True) for r in rows})==1
  assert all(native(v)==native(rows[0]) for v in rows)
  expected_api={'rc':1,'code':'E0599'} if ph in ('edit','unchanged_edit') else {'rc':0,'ordinary_output':'2-6'} if kind=='build' else {'rc':0,'metadata':True}
  assert all(v['ordinary_api']==expected_api for v in rows)
  if kind=='build':
   members=[r['members'] for r in rows]
   assert all(m for m in members)
print(json.dumps({'native_cargo_commands':60,'arm_cases':cases,'raw':sha(raw),'source_manifest':z['binding'],'scored':0},sort_keys=True,indent=2))
