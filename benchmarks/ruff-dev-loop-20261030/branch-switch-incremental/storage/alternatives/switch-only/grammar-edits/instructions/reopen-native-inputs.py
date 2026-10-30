from pathlib import Path
import collections,hashlib,json,os,re,stat,sys
r=Path(sys.argv[1]); z=r/'diagnostic-v2'; flags=json.loads((z/'registration.json').read_bytes()); assert os.getuid()==1000 and os.statvfs(r/'ram').f_flag&os.ST_RDONLY
h=lambda b:hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
seen={}
def file(p):
 st=p.stat();assert stat.S_ISREG(st.st_mode);key=(st.st_dev,st.st_ino,st.st_size,st.st_ctime_ns)
 if key not in seen:
  with p.open('rb')as f:seen[key]=hashlib.file_digest(f,'sha256').hexdigest()
 return [st.st_size,seen[key]]
def sign(ob):return h(json.dumps(ob,sort_keys=True,separators=(',',':')).encode())
def cats(p):
 if p.name.endswith(('.rlib','.rmeta','.so','.a','.o','.dylib','.lib','.dll','.rmeta-link')):return 'provider'
 if p.name.endswith('.d'):return 'dep-info'
 return 'other'
cfg=read(r/'ops/study.json');roles={}
for role in 'RK':
 argsrows=[]
 for j in (1,2):
  for ph in ('edit-B','restore-B'):
   pp=r/'runs'/('pair-'+str(j)+'-'+role);a,=(pp/ph/'callgrind').glob('rustc.*.argv');v=a.read_bytes();assert v==(pp/('native-'+ph)/'native.argv').read_bytes();argsrows.append(v)
 assert len(set(argsrows))==1;roles[role]=argsrows[0]
def norm(b,role):return b.replace(b'/workspaces/bf36f3330d5965d1/v2-'+{'R':b'f21268108672fd87','K':b'7e17aac3200cd4df'}[role]+b'/',b'/workspaces/bf36f3330d5965d1/v2-{ARM}/')
assert norm(roles['R'],'R')==norm(roles['K'],'K')
def rel(p,role):return norm(os.fsencode(p.relative_to(r/'view')),role).decode()
slots={}; phaseholds={};names=set()
for slot in cfg['slots']:
 ref=slot.startswith('ref-');role=slot.split('-')[1]if ref else slot[-1];vector=roles[role].rstrip(b'\0').split(b'\0');root=r/'ram/stores'/slot
 def phys(p):
  logical=Path(os.fsdecode(p))
  assert logical.is_absolute() and logical.is_relative_to(r/'view');return root/logical.relative_to(r/'view')
 ex={};candidates={};nat={};native_inv={};names_in_search={};scope=collections.Counter()
 for i,t in enumerate(vector[:-1]):
  if t==b'--extern':
   nm,logical=vector[i+1].split(b'=',1);nm=nm.decode();raw=phys(logical);assert not nm in ex and raw.suffix=='.rmeta';ex[nm]=[rel(Path(os.fsdecode(logical)),role),*file(raw)];names.add(nm)
  if t==b'-L':
   k,logical=vector[i+1].split(b'=',1);k=k.decode();p=phys(logical);key=rel(Path(os.fsdecode(logical)),role);scope[k]+=1;assert p.is_dir()
   if k=='native':
    d={s.relative_to(p).as_posix():file(s) for s in p.rglob('*')if s.is_file()};assert d;nat[key]=d;continue
   assert k=='dependency';items={}
   for f in sorted(p.iterdir()):
    items[f.name]='dir' if f.is_dir()else cats(f)
    if f.is_file() and cats(f)=='provider':candidates[key+'/'+f.name]=file(f)
   names_in_search[key]=items
 assert len(ex)==16 and scope=={'dependency':45,'native':1}
 term=read(r/'runs'/slot/'terminal.json');phases=['empty'] if ref else ['edit-B','restore-B','native-edit-B','native-restore-B','unchanged-B','native-unchanged-B']
 if not ref:phases=[p for p in phases if p in term['hashes']]
 perph={}
 for ph in phases:
  o=r/'runs'/slot/ph;cc=[x for x in map(json.loads,(o/'cargo.stdout').read_bytes().splitlines())if x['reason']=='compiler-artifact']
  scored=read(o/'result.json');assert h((o/'result.json').read_bytes())==term['hashes'][ph]
  assert len(cc)==97 and (len(scored['dirty'])==97 if ref else 'ruff_python_parser'in scored['dirty']or 'unchanged' in ph)
  for nm,(lp,n,fh)in ex.items():
   claimed=[u for u in cc if any(rel(Path(f),role)==lp for f in u['filenames'] if Path(f).is_relative_to(r/'view'))];assert len(claimed)==1,(nm,lp,slot,ph)
   assert ref or (claimed[0]['fresh']and nm not in scored['dirty']),(nm,slot,ph)
  assert read(o/'run-reader.json')['exit']==0 and read(o/'link-reader.json')['exit']==0 and file(r/'full-outputs'/scored['ELF'])[1]==scored['ELF']
  s=state=scored['state'];assert (o/'run-reader.stdout').read_text().strip()==scored['verdict']=='Expr=56 signed-expression='+('accepted'if s=='C'else'rejected')
  current={t:h(json.dumps(sorted((n,sha)for name,n,sha in g['members']if name.endswith('.o')),separators=(',',':')).encode()) for t,g in scored['rlibs'].items()};refrow=phaseholds.setdefault(s,[scored['ELF'],current]);assert refrow==[scored['ELF'],current]
  perph[ph]={'state':s,'ELF':scored['ELF'],'objects':current,'typed':97,'dirty':len(scored['dirty']),'verified_extern_claims':len(ex),'result_sha256':term['hashes'][ph]}
 slots[slot]={'externs':ex,'native':nat,'dependency_candidates':candidates,'search_names':names_in_search,'native_roles':dict(scope),'phases':perph}
def across(field):
 matrix={};keyset=set.union(*(set(s[field])for s in slots.values()))
 for key in sorted(keyset):
  values={k:row[field].get(key)for k,row in slots.items()};matrix[key]={'unique':len({sign(v)for v in values.values()}),'physical_groups':{g:[s for s,v in values.items()if sign(v)==g]for g in sorted({sign(v)for v in values.values()})}}
 return matrix
mats={k:across(k)for k in ('externs','native','dependency_candidates','search_names')};mism={k:[x for x,v in m.items()if v['unique']>1] for k,m in mats.items()}
doc={'registration':h((z/'registration.json').read_bytes()),'prior_primary_rejection':h((z/'primary-rejection.json').read_bytes()),'v2_only_normalized_sha256':h(norm(roles['R'],'R')),'actual_argv_sha256':{k:h(v)for k,v in roles.items()},'differing':mism,'cases':slots,'provider_comparison':mats,'genuine_verdicts':phaseholds,'all_16_externs_identical':not mism['externs'],'all_discovered_native_identical':not mism['native'],'all_discovered_candidate_identities_identical':not mism['dependency_candidates'],'raw_objects_hashed':len(seen),'full_raw_read_bytes':sum(k[2]for k in seen),'time_effects_read':False,'instruction_effects_read':False}
f=z/'physical-inputs.json';assert not f.exists();f.write_text(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n')
print(json.dumps({'receipt':h(f.read_bytes()),'physical_count':len(seen),'new_bytes_hashed':doc['full_raw_read_bytes'],'named_extern_count':len(names),'selected_extern_raw_mismatches':mism['externs'],'native_search_mismatch_count':len(mism['native']),'dep_provider_mismatch_count':len(mism['dependency_candidates']),'dep_search_listing_mismatch_count':len(mism['search_names']),'scoped_candidate_examples':[Path(k).name for k in mism['dependency_candidates']][:24]},sort_keys=True))
