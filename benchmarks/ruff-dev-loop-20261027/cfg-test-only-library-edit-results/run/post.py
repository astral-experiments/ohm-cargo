from pathlib import Path
from collections import Counter
import hashlib,json,shutil,subprocess,sys
I=Path(__file__).resolve().parent;X=I.parent;Q=X/'cfg-library-first-v1-campaign';O=Q/'selected';O.mkdir(exist_ok=True);sys.path.insert(0,str(I));from artifacts import archive,metadata
from wire import read
from compare import archive_diff
J=lambda p:json.loads(p.read_bytes())
def H(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(n,x):p=O/n;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(x,sort_keys=True,indent=1)+'\n')
def cop(p,n):q=O/n;q.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(p,q)
phases=[];sources={m:Q/'fixture'/m/'docstring.rs' for m in ('original','edited')};md5s={k:hashlib.md5(v.read_bytes()).digest() for k,v in sources.items()};jobs=[];casts=[]
subprocess.run([sys.executable,'-B',str(I/'live-attribution.py')],check=True,stdout=subprocess.DEVNULL)
for name,p in sources.items():cop(p,'inputs/'+name+'-docstring.rs')
for mode in ('build','check','test'):
 rows=sorted((Q/'receipts'/mode).glob('*/receipt.json'),key=lambda p:p.stat().st_mtime);olds=None;oldelfs=None;elsets={};pmod={}
 for z in rows:
  d=z.parent;v=J(z);setup=J(d/'setup.json');v['setup']=setup;v['space_state_footprint']='three independently empty target/shared/registry homes';v['diagnostic_count']=len(J(d/'diagnostics.json'));v['processes_sha256']=H(d/'processes.json');a=[json.loads(x) for x in (d/'stdout').read_bytes().splitlines()];art=[r for r in a if r.get('reason')=='compiler-artifact'];ins=J(d/'artifact-state.json');pc=J(d/'processes.json')
  if mode in ('build','test'):
   src=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');phys=(Q if mode!='test' else Path('/dev/shm/ohm-cfg-library-first-v1'))/'state'/mode
   pths={p for j in art if j['package_id'].startswith('path+') for p in j['filenames'] if Path(p).suffix in ('','.so')}
   if not elsets: 
    for raw in pths:
     pp=Path(raw);root=src/('native-target' if pp.is_relative_to(src/'native-target') else 'shared');fp=phys/('target' if root.name=='native-target' else 'shared')/pp.relative_to(root)
     with fp.open('rb') as fd:ty=fd.read(4)
     if ty==bytes.fromhex('7f454c46'):elsets[raw]=1
   assert len(elsets)==(15 if mode=='build' else 110)
   el={p:ins[p]['sha256'] for p in elsets};v['elf_roster']={'count':len(el),'sha256':hashlib.sha256(json.dumps(el,sort_keys=True).encode()).hexdigest(),'changed':{p:[oldelfs[p],h] for p,h in el.items() if oldelfs and oldelfs[p]!=h}};oldelfs=el
  if v['label'] in ('edit','restore'):
   v['changed_file_digests']=J(d/'artifact-changes.json');sx=[{k:t[k] for k in ('pid','img','kind','crate','test','exec_sha256','image_sha256','argv','link_output')} for t in pc['typed'] if t['kind'] in ('rustc-full','rustc-link-only','wild','cc','collect2','other-linker','rustc-guarded-unknown')];save('process/'+mode+'-'+v['label']+'.json',sx);v['rustc_roles']=[[t['kind'],t['crate'],t['test']] for t in sx if t['kind'].startswith('rustc')]
  if v['label'] in ('cold','edit','restore'):
   full=J(d/'producer.json');pmod[v['label']]=full;save('producer/'+mode+'-'+v['label']+'.json',full)
   phase=v['label'];srcview=v['view'];md=d/'producer.rmeta'
   if md.is_file():
    wire=read(md,sources[srcview],'docstring.rs');v['actual_source_entry']=wire
    q=O/'raw-rmeta';q.mkdir(exist_ok=True);dest=q/(H(md)+'.rmeta')
    if not dest.is_file():shutil.copyfile(md,dest)
   for dep in d.glob('*.d.original'):
    lines=dep.read_text(errors='replace');focus=[ln for ln in lines.splitlines() if 'crates/ty_ide/src/docstring.rs' in ln or 'ohm-foreign-span-bytes' in ln];v.setdefault('producer_dep_inputs',{})[dep.name]={'raw_sha256':H(dep),'source_tracked':bool(focus),'contained_observer_marker':'ohm-foreign-span-bytes' in lines,'path':'crates/ty_ide/src/docstring.rs','input_count':len(lines.splitlines()[0].split())-1 if lines else 0}
   if (d/'ty_ide-test-roster.txt').is_file():cop(d/'ty_ide-test-roster.txt','test-lists/'+phase+'.txt')
  phases.append(v)
 for a,b in (('cold','edit'),('edit','restore')):
  if a in pmod and b in pmod:
   def native(label):
    r=next(j for j in pmod[label] if not j['profile']['test']);return next((x for x in r['component_hashes'].values() if 'members' in x),None)
   x,y=native(a),native(b)
   if x and y:casts.append({'mode':mode,'from':a,'to':b,**archive_diff(x,y)})
save('phases.json',phases);save('cargo-native-section-comparisons.json',casts);cop(Q/'live-pair-attribution.json','wire-and-outputs.json');cop(Q/'complete.json','complete-run.json');cop(Q/'initial-disks.json','initial-disks.json')
mix=Q/'mixed-current-snapshots';avail=mix/'content';mixed={};snapshot_file_outputs={}
for p in sorted(mix.glob('*.json')):
 if p.name=='complete.json':continue
 r=J(p);snapshot_file_outputs[p.stem]=r
 for z in r['rows']:
  for dst,v in z['paths'].items():
   h=v['phase_sha256'];sv=avail/(h+Path(dst).suffix) if h else None
   if sv and sv.is_file() and H(sv)==h:
    v['matching_material_available_across_qualified_states']=True
    if sv.suffix=='.rlib' and h not in mixed:mixed[h]=archive(sv,'docstring.rs',md5s)
   else:v['matching_material_available_across_qualified_states']=False
 save('mixed/'+p.name,r)
for h,r in mixed.items():save('mixed/archive/'+h+'.json',r)
pairs=[]
for mode in ('build','test'):
 for pre,aft in [('cold','edit'),('edit','restore')]:
  def a(name):
   r=snapshot_file_outputs[mode+'-'+name];rr=next((v for v in r['rows'] if not v['is_test']),None)
   if rr is None:return None
   return {Path(p).suffix:v['phase_sha256'] for p,v in rr['paths'].items()}
  aa,bb=a(pre),a(aft)
  if not aa or not bb:continue
  a1,a2=(r.get('.rlib') for r in (aa,bb));row={'mode':mode,'from':pre,'to':aft,'published':[aa,bb],'have_both_matching_raw_archives':a1 in mixed and a2 in mixed,'whole_so_equal':aa.get('.so')==bb.get('.so'),'whole_rmeta_equal':aa.get('.rmeta')==bb.get('.rmeta')}
  if row['have_both_matching_raw_archives']:row['native_members']=archive_diff(mixed[a1],mixed[a2])
  pairs.append(row)
save('mixed/verified-pairs.json',pairs)
completed=Q/'clean-and-ordinary'
if completed.exists():
 for n in ('identity.json','external-readers.json','macro-headers.json','complete.json','current-root-listings.json','reader_good.rs','reader_error.rs','raw_observer.rs','raw_source_client.rs','raw_observer-build.stderr'):
  if (completed/n).is_file():cop(completed/n,'independent/'+n)
 for d in ('compiler-original','compiler-edited','warm-isolated-prefix'):
  for n in ('evidence.json','stderr','stdout'):
   if (completed/d/n).is_file():cop(completed/d/n,'independent/'+d+'/'+n)
 for d in completed.glob('raw-source-client-*'):
  for p in sorted(d.glob('*.d'))+list(d.glob('stderr')):cop(p,'independent/'+d.name+'/'+p.name)
 cold=[]
 for name in ('original','edited'):
  co=completed/('compiler-'+name)
  if not (co/'evidence.json').is_file():continue
  cr=J(co/'evidence.json')
  for md in (co/'out').glob('*.rmeta'):
   cp=O/'raw-rmeta'/(H(md)+'.rmeta')
   if not cp.is_file():shutil.copyfile(md,cp)
   cr['decoded_source']=read(md,sources[name],'docstring.rs')
  cold.append(cr)
 if len(cold)==2 and 'archive' in cold[0] and 'archive' in cold[1]:save('independent/clean-archive-comparison.json',archive_diff(cold[0]['archive'],cold[1]['archive']))
print('saved',len(phases),'phases; archive info',len(casts),'mixed candidates',[(s['mode'],s['from'],s['have_both_matching_raw_archives']) for s in pairs])
