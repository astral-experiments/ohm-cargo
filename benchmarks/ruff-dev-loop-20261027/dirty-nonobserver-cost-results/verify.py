from pathlib import Path
import collections,gzip,hashlib,json,re,sys
p=Path(__file__).resolve().parent;sys.path.insert(0,str(p))
from analyze import analyze
z=json.loads(gzip.decompress((p/'commands.json.gz').read_bytes()));plan=json.loads((p/'schedule.json').read_bytes());assert z['controls']['subjects']==plan['executable_arms'] and z['controls']['driver']==plan['release_driver_sha'] and z['temporary_byte_size']<2**30
def identity(v):
    items=[]
    for x in v['members'] or []:
        if x['kind']=='codegen':
            m=re.fullmatch(r'(ruff_text_size-[0-9a-f]{16}\.[0-9a-z]+)\.[0-9a-z]+(\.rcgu\.o)',x['label']);assert m;items.append((m[1]+m[2],x['size'],x['sha']))
        elif x['kind']=='lib.rmeta-link':items.append((x['label'],x['size'],x['exact_member_names_folded']))
        else:assert x['kind']==x['label']=='lib.rmeta';items.append((x['label'],x['size'],x['sha']))
    return [v['source'],v['ordinary_api'],v['outputs']['.rmeta'],v['depinfo_sha256'],items]
proof={};c=z['controls']['qualified']
for kind in ('check','build'):
    for arm in ('B','B2','C','C2'):
        for phase,row in c[kind+'-'+arm].items():
            dirt=not phase.startswith('unchanged');assert row['trace']['observer_probes']==int(dirt and arm[0]=='C') and len(row['trace']['jobs'])==int(dirt) and row['fresh']==(not dirt)
            if dirt:assert row['trace']['jobs'][0]['depinfo_flag']==(arm[0]=='C')
            assert row['checksummed_sources']==4 and not row['foreign_marker']
            if 'edit' in phase:assert row['ordinary_api']=={'rc':1,'code':'E0599'}
            else:assert row['ordinary_api']==({'rc':0,'metadata':True} if kind=='check' else {'rc':0,'ordinary_output':'2-6'})
        for phase in ('edit','restore'):
            row=c[kind+'-'+arm][phase];v=identity(row);assert proof.setdefault((kind,phase),v)==v
            assert row['outputs']==c[kind+'-'+arm]['unchanged_'+phase]['outputs']
assert collections.Counter([r['kind'] for r in z['scored']])=={'check':48,'build':48}
for r in z['scored']:
    v=r['receipt'];assert v['trace'] is None and v['fresh'] is False and v['checksummed_sources']==4 and not v['foreign_marker'] and identity(v)==proof[r['kind'],r['direction']]
a=analyze(plan,z);assert a==json.loads((p/'analysis.json').read_bytes())
print(json.dumps({'unscored_controls':40,'timed_checks':48,'timed_builds':48,'complete_native_projections':96,'small_cost':{k:v['small_margin_pass'] for k,v in a.items()},'slower':{k:v['slower'] for k,v in a.items()}},sort_keys=True))
