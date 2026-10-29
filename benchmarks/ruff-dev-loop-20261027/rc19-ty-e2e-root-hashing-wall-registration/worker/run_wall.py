"""Run only the enrolled uninstrumented root-Cargo endpoint and its separate correctness controls."""
from pathlib import Path
import json,os,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent));from common import *
from enter import launch
from wire import same,bind_source_files
from analyze_wall import analyze

OLD=K.parent/'ohm-rc20-ty-e2e-inlay-manifest-20261029-mount-v2'
ROLES=('parent','child')

def enrolled_sources():
 reg=K/'registration';actual=rawsha(reg/'SHA256SUMS');assert get(K/'binding/physical.json')['plan']==actual
 names=set()
 for line in (reg/'SHA256SUMS').read_text().splitlines():
  digest,name=line.split('  ',1);rel=Path(name);assert name not in names and not rel.is_absolute() and '..' not in rel.parts;names.add(name);assert rawsha(reg/rel)==digest
  if rel.parts[0]=='worker':assert rawsha(K/'ops'/rel.name)==digest
  if rel.parts[0]=='design':assert rawsha(DESIGN/rel.name)==digest
 assert names=={str(p.relative_to(reg)) for p in reg.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
 assert {p.name for p in (K/'ops').glob('*.py')}=={Path(n).name for n in names if n.startswith('worker/')}
 for name,digest in get(DESIGN/'product-and-proofs.json')['frozen_helper_files'].items():
  family,relative=name.split('/',1);root={'campaign':M,'native-tools':prior.V.SEED}[family];assert rawsha(root/relative)==digest,name
 assert sha_oracle()==get(DESIGN/'whole-reference.json')['cold_native_packet']
 return actual

def sha_oracle():return rawsha(OLD/'native-stopped-result-v2/SHA256SUMS')

def begin():
 plan=enrolled_sources();assert os.getuid()==1000 and set(os.sched_getaffinity(0))==set(SCHEMA['cpus']);floor=floors(2_100_000_000)
 assert not (K/'binding/offclock-start.json').exists();q=get(K/'binding/native-go.json');assert q['plan']==plan and q['native_only'] and not q['score']
 assert (LANES/'train').is_symlink() and (LANES/'train').resolve()==(OLD/'lanes/train').resolve();assert rawsha(K/'binding/donor.json')==rawsha(OLD/'binding/donor.json')
 bind_source_files();gold=get(DESIGN/'whole-reference.json');records={}
 for a,x in gold['cold_oracle_rows'].items():
  d=OLD/'reports'/('cold-'+a)/'edited-cold';store=OLD/'cold-archives';p=store/('cold-'+a+'.tar.zst');assert rawsha(p)==x['archive'] and p.stat().st_size==x['archive_bytes'];assert rawsha(store/('cold-'+a+'.json'))==x['terminal'];assert rawsha(d/'result.json')==x['result'] and rawsha(d/'native.json')==x['native'] and rawsha(d/'dependencies.json')==x['closure'] and rawsha(d/'typed-roster.json')==x['typed']
  raw=OLD/'recipe-forensics/raw'/('cold-'+a+'.rlink');assert rawsha(raw)==x['raw_recipe'];r=get(d/'result.json');assert r['units']==300 and r['fresh']==0 and r['e2e']==gold['sources']['edited']['elf'] and r['exit']==0
  records[a]={'archive':x['archive'],'raw_recipe':x['raw_recipe'],'all_native_files_verified_again':x['closure'],'runtime_200':r['verdicts']['list']}
 for m in ('original','edited'):
  h=gold['sources'][m]['elf']['sha256'];ref=(M/'native-objects'/h) if m=='original'else(OLD/'bodies'/h);assert rawsha(ref)==h
  for a in ROLES:
   p=OLD/'reports'/('leaf-'+a+'-'+m)/'root-empty/native-descriptor.json';assert rawsha(p)==gold['sources'][m]['native_descriptor']
 small=get(K/'binding/small-source.json');assert rawsha(small['manifest_file'])==small['manifest_sha256']=='41db99ab3ddc0f97a59cf2253bd5385bf0f479a915b134155f81efddcc1ca0f3'
 put(K/'binding/offclock-start.json',{'registration':plan,'source':rawsha(DESIGN/'source.json'),'true_external_colds':records,'small':small['manifest_sha256'],'capacity':floor})

def phase(lane,a,label,mode,how,want):
 launch(lane,a,label,mode,how,want);d=REPORTS/lane/label;result=get(d/'result.json');assert get(d/'outer.json')['exit']==0
 for which in ('before','after'):
  obs=get(d/('raw-recipe-'+which+'.json'))
  if obs['existence']=='regular':assert rawsha(K/'raw-recipes'/obs['sha256'])==obs['sha256']
  else:assert obs['existence']=='absent'
 if mode!='invalid'and want in ('dirty','leaf'):
  proof=get(d/'wire-proof.json');assert proof['body']==get(d/'raw-recipe-after.json')['sha256'];assert proof['all_histories_wire']==get(DESIGN/'whole-reference.json')['sources'][mode]['all_histories_wire']
  if how=='native':assert rawsha(d/'native-descriptor.json')==get(DESIGN/'whole-reference.json')['sources'][mode]['native_descriptor']
 return d

def qualification(a):
 assert (K/'binding/offclock-start.json').is_file();steps=[('incoming','original','settled'),('edit','edited','dirty'),('repeat','edited','settled'),('invalid','invalid','dirty'),('recovery','edited','dirty'),('restore','original','dirty'),('restored-repeat','original','settled')];lane='warm-'+a
 for label,mode,n in steps:phase(lane,a,label,mode,'native',n)
 for m in ('original','edited'):phase('leaf-'+a+'-'+m,a,'root-empty',m,'native','leaf')
 phase(lane,a,'io-edit','edited','io','dirty');phase(lane,a,'io-restore','original','native','dirty');phase(lane,a,'ready','original','native','settled')

def verify_q():
 enrolled_sources();plots={};gold=get(DESIGN/'whole-reference.json')
 for a in ROLES:
  r=REPORTS/('warm-'+a);io=get(r/'io-edit/cargo-real-input-io.json');assert len(io['inputs'])==len(io['opened'])==140 and io['executable_stat_calls']>0
  used=sum(io['read_bytes'].values());assert used==(sum(io['inputs'].values())if a=='parent'else 0)
  assert get(r/'incoming/launches.json')==get(r/'ready/launches.json')=={'full':[],'cached':[],'wild_total':0,'root_native':{'stock-wild':0,'gcc':0,'collect2':0}};assert get(r/'invalid/result.json')['exit']==101
  plots[a]={'input_bytes':sum(io['inputs'].values()),'observed_post_link_read_bytes':used,'io':rawsha(r/'io-edit/cargo-real-input-io.json'),'status':rawsha(r/'ready/result.json')}
 for tag in ('edit','recovery','restore','io-edit','io-restore'):
  same(REPORTS/'warm-parent'/tag,REPORTS/'warm-child'/tag)
 for m in ('original','edited'):
  same(REPORTS/('leaf-parent-'+m)/'root-empty',REPORTS/('leaf-child-'+m)/'root-empty')
  all_paths=[REPORTS/('warm-'+a)/('edit' if m=='edited' else 'restore')for a in ROLES]+[REPORTS/('leaf-'+a+'-'+m)/'root-empty'for a in ROLES];assert all(get(p/'result.json')['e2e']==gold['sources'][m]['elf'] for p in all_paths)
  assert all(get(p/'wire-proof.json')['all_histories_wire']==gold['sources'][m]['all_histories_wire'] for p in all_paths)
 put(K/'binding/native-admission.json',{'plan':rawsha(K/'registration/SHA256SUMS'),'offclock_start':rawsha(K/'binding/offclock-start.json'),'inputs':plots,'whole':rawsha(DESIGN/'whole-reference.json'),'original_study_withheld':sha_oracle(),'replacements':0,'elf':{m:v['elf'] for m,v in gold['sources'].items()}})

def quiet():
 def counts():
  items={}
  for l in Path('/proc/stat').read_text().splitlines():
   key,*fields=l.split()
   if key in {'cpu'+str(n) for n in SCHEMA['cpus']}:
    v=[int(n) for n in fields[:8]];items[key]=(sum(v),v[3])
  assert len(items)==4;return items
 limit=time.monotonic()+180
 while True:
  a=counts();time.sleep(1);b=counts();f={k:(b[k][1]-v[1])/(b[k][0]-v[0]) for k,v in a.items()}
  if min(f.values())>=.85:return f
  assert time.monotonic()<limit,'four quiet cores unavailable before clock'

def run():
 admitted=rawsha(K/'binding/native-admission.json');grant=get(K/'binding/score-grant.json');plan=enrolled_sources();assert grant['go'] and grant['preflight']==admitted and grant['plan']==plan and grant['pairs']==32 and grant['no_replacement'];orders=get(DESIGN/'orders.json');assert len(orders['orders'])==32 and all(sorted(orders['orders'][i:i+4])==['FR','FR','RF','RF']for i in range(0,32,4))
 assert not (K/'binding/clock-start.json').exists();put(K/'binding/clock-start.json',{'grant':rawsha(K/'binding/score-grant.json'),'registration':plan,'order':rawsha(DESIGN/'orders.json'),'began':time.time_ns()});completed=[]
 for i,seq in enumerate(orders['orders'],1):
  label='pair-'+str(i).zfill(2);visits={}
  for token in seq:
   a={'R':'parent','F':'child'}[token];lane='warm-'+a
   if i>1:phase(lane,a,label+'-reset','original','ordinary','dirty')
   phase(lane,a,label+'-settled','original','ordinary','settled')
   put(K/'logs'/(label+'-'+a+'-idle.json'),quiet());visits[a]=phase(lane,a,label+'-edit','edited','ordinary','dirty')
  matched=same(visits['parent'],visits['child'])
  if i>1:same(REPORTS/'warm-parent'/(label+'-reset'),REPORTS/'warm-child'/(label+'-reset'))
  receipt={'pair':i,'order':seq,'accepted_sources':matched,'slots':{a:{'product':rawsha(d/'result.json'),'clock':rawsha(d/'clock.json'),'wire':rawsha(d/'wire-proof.json')}for a,d in visits.items()}};put(K/'logs'/(label+'-closed.json'),receipt);completed.append(receipt)
 for a in ROLES:
  lane='warm-'+a;phase(lane,a,'post-restore','original','native','dirty');phase(lane,a,'post-settled','original','native','settled');phase(lane,a,'post-edit','edited','native','dirty')
 for l in ('post-restore','post-edit'):same(REPORTS/'warm-parent'/l,REPORTS/'warm-child'/l)
 put(K/'binding/clock-terminal.json',{'pairs':32,'post_native':True,'visits':completed,'all_slots':64,'elapsed_opened_for_analysis':False})

def stats():
 c=get(K/'binding/clock-terminal.json');o=get(DESIGN/'orders.json');assert c['pairs']==len(c['visits'])==32 and c['post_native'] and c['all_slots']==64
 rows=[]
 for i,z in enumerate(c['visits'],1):
  assert z['pair']==i and z['order']==o['orders'][i-1];row={}
  for a,v in z['slots'].items():
   p=REPORTS/('warm-'+a)/('pair-'+str(i).zfill(2)+'-edit');assert rawsha(p/'clock.json')==v['clock'] and rawsha(p/'result.json')==v['product'] and rawsha(p/'wire-proof.json')==v['wire'];clock=get(p/'clock.json');assert clock['status']==0 and clock['elapsed_ns']==clock['end_ns']-clock['start_ns'];row[a]=clock['elapsed_ns']
  rows.append(row)
 report=analyze(rows,o['orders'],o['bootstrap_seed']);report.update({'rows_ns':rows,'orders':o['orders'],'terminal':rawsha(K/'binding/clock-terminal.json')});put(K/'binding/analysis.json',report)

if __name__=='__main__':
 assert len(sys.argv)==2 and os.getuid()==1000;action=sys.argv[1];enrolled_sources()
 if action in ROLES:qualification(action)
 else:{'begin':begin,'admit':verify_q,'run':run,'analyze':stats}[action]()
