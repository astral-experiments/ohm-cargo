from pathlib import Path
import collections,gzip,hashlib,json,os,re,stat,subprocess,sys
r=Path(sys.argv[1]);o=r/'ops';rd=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def signature(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
def ident(p):
 z=p.stat();return [z.st_dev,z.st_ino,z.st_ctime_ns,z.st_size]
reg=rd(o/'study.json');term=rd(r/'complete.json');assert term['plan']==digest(o/'EARLY.sha256');subprocess.run(['sha256sum','--quiet','-c','EARLY.sha256'],cwd=o,check=True)
assert (r/'boot.exit').read_text()=='0\n';ri=rd(r/'prep.json');bulk=Path(ri['bulk'])
def get_members(data):
 assert data[:8]==b'!<arch>\n';i=8;names=b'';arr=[];extras=[]
 while i<len(data):
  h=data[i:i+60];assert h[-2:]==b'\x60\n';n=int(h[48:58]);raw=h[:16].strip();payload=data[i+60:i+60+n];assert len(payload)==n;i+=60+n+(n&1)
  if raw==b'//': names=payload
  if raw in (b'//',b'/',b'/SYM64/'):extras+=[[raw.decode(),n,sha(payload)]];continue
  if raw[:1]==b'/' and raw[1:].isdigit(): a=int(raw[1:]);name=names[a:names.index(b'/\n',a)]
  elif raw.startswith(b'#1/'):a=int(raw[3:]);name=payload[:a].rstrip(b'\0');payload=payload[a:]
  else:name=raw.rstrip(b'/')
  arr+=[[name.decode(),len(payload),sha(payload)]]
 assert i==len(data)
 return arr,extras
watch_path=r/'verification-v1/tgids-terminal.json';watch=rd(watch_path)['rows'];lookup={}; result={'schema':1,'registration':term['plan'],'protocol':digest(o/'study.json'),'roles':{},'refs':{},'observations':{},'ledger':{},'source':rd(o/'source.json'),'bootstrap':{},'failed_acquisitions':[]}
for role in 'RK':
 de=rd(o/('sdk-'+role+'.json'));prod=Path(de['source']); assert digest(prod/'product.json')==de['product']; assert rd(prod/'product.json')['native_files']==de['native'] and de['native'][de['driver']]==reg['driver'][role]
 fields={'sha':reg['driver'][role],'source':rd(prod/'product.json')['rust'],'product':de['product'],'launcher':de['native']['bin/rustc'],'driver_identity':ident(Path(de['files'][de['driver']])),'launcher_identity':ident(Path(de['files']['bin/rustc'])),'std_count':53,'std_ledger':signature({k:v for k,v in de['native'].items() if k.startswith('lib/rustlib/')}),'cargo':reg['cargo'],'wild':reg['wild']}
 result['roles'][role]=fields
assert result['roles']['R']['std_ledger']==result['roles']['K']['std_ledger']
for s in reg['slots']:
 dd=r/'runs'/s;tt=rd(dd/'terminal.json');ro=tt['role'];cfg=rd(o/('sdk-'+ro+'.json'));ad=rd(dd/'admission.json')
 assert digest(dd/'terminal.json')==term['slots'][s];assert ad['source_product']==cfg['product'] and ad['registry_ro'] and ad['empty'] and len(ad['physical'])==55 and ad['capacity']['memory']>70*2**30
 assert ad['physical'][cfg['driver']]==tt['driver_pre']==tt['driver_post']==result['roles'][ro]['driver_identity'] and ad['physical']['bin/rustc']==result['roles'][ro]['launcher_identity']
 for k,v in ad['physical'].items():
  p=Path(cfg['files'][k]) if k in cfg['files'] else r.parent/'ohm-ruff-pr274-replay-v1'/'parent'/k
  assert digest(p)==cfg['native'][k] and ident(p)==v
 for n,v in [('cargo',ad['cargo']),('wild',ad['wild'])]:
  if n in result['bootstrap']:assert result['bootstrap'][n]==v
  else:result['bootstrap'][n]=v
 rows={}
 result['observations'][s]=rows
 for phase,hh in tt['hashes'].items():
  d=dd/phase;assert digest(d/'result.json')==hh
  w=rd(d/'result.json');g=w['git'];state=w['state'];assert (g['commit'],g['branch'])==((result['source']['A'],'historical-parent')if state=='A' else (result['source']['B'],'historical-feature')); assert w['typed']==97 and w['role']==ro
  got='Expr='+('64' if state=='A' else '56')+' signed-expression='+('accepted' if state=='C' else 'rejected')
  assert got==w['verdict'];hh0=w['ELF'];assert digest(r/'full-outputs'/hh0)==hh0 and (r/'full-outputs'/hh0).read_bytes().startswith(b'\x7fELF')
  assert (d/'run-reader.stdout').read_bytes()==(got+'\n').encode()
  for prefix in ('cargo','run-reader','link-reader'):
   x=rd(d/(prefix+'.json'));assert x['exit']==0 and digest(d/(prefix+'.stdout'))==x['stdout'] and digest(d/(prefix+'.stderr'))==x['stderr']
  real=[json.loads(t) for t in (d/'cargo.stdout').read_bytes().splitlines()];assert real[-1]=={'reason':'build-finished','success':True}
  uu=[t for t in real if t['reason']=='compiler-artifact'];assert sorted(t['target']['name']for t in uu if not t['fresh'])==w['dirty']
  by={}
  for lib,v in w['rlibs'].items():
   acc=[(n,h)for n,size,h in v['members']if n.endswith('.o')];assert len(acc)>0
   ref=s.startswith('ref-') or (state=='A' and phase=='empty-A' and s.startswith('pair-1'))
   if s.startswith('ref-'):
    unit,=[t for t in uu if t['target']['name']==lib and 'lib' in t['target']['kind']];archives={}
    for rawfile in unit['filenames']:
     f=Path(rawfile);logical=f.relative_to(r/'view'); physical=bulk/s/logical
     if physical.suffix not in ('.rlib','.rmeta'):continue
     archives[physical.suffix]=[physical.stat().st_size,digest(physical)]
     if physical.suffix=='.rlib':
      assert archives['.rlib']==[v['bytes'],v['sha']];pars,ex=get_members(physical.read_bytes());assert pars==v['members'] and ex==v['index']
    assert '.rlib' in archives;result['refs'].setdefault(ro+'/'+state,{}).setdefault('original_files',{})[lib]=archives
   if ref:lookup.setdefault((ro,state,lib),v)
   by[lib]={'size':v['bytes'],'sha':v['sha'],'member_manifest':signature(v['members']),'payload_multiset':v['payload_multiset'],'objects':len(acc),'object_body_set':signature(sorted([size,h]for n,size,h in v['members']if n.endswith('.o'))),'metadata':[[n,size,h]for n,size,h in v['members']if n in ('lib.rmeta','lib.rmeta-link')]}
  if s.startswith('ref-') or (state=='A' and phase=='empty-A' and s.startswith('pair-1')):result['refs'].setdefault(ro+'/'+state,{})['elf']=hh0
  st=w['storage'];packed=collections.Counter()
  for f,(family,name,sz,blocks,ino) in st['packed'].items():
   pre=next((z for z in ('ruff_python_ast','ruff_python_parser') if family.startswith(z)),'other');packed[pre+'/'+name]+=1
  kaf=None
  if w['kernel']:
   kk=w['kernel'];raws=kk['trace'];events=collections.Counter();actual=[];execs=collections.Counter();evidence=[]
   for nf,(nn,hs,gs) in raws.items():
    pp=d/nf; assert digest(pp)==gs;hf=hashlib.sha256();n=0
    with gzip.open(pp,'rb') as file:
     for raw in file:
      hf.update(raw);n+=len(raw);line=raw.decode(errors='replace').strip()
      if line.startswith('execve(') and re.search(r'\)\s+= 0$',line):
       exe=re.match(r'execve\("([^"]+)"',line)[1];execs[Path(exe).name]+=1
       if exe.endswith('/bin/rustc') and '"--crate-name"' in line and '"--emit=' in line:
        crate=re.search(r'"--crate-name", "([^"]+)"',line)[1];assert '-Zohm-branch-cache=yes' in line and '-Zohm-check-relink-inputs' in line;actual.append(crate)
      if 'ohm-packed-' in line and not '= -1 ' in line:
       fam=next((f for f in ('ruff_python_parser','ruff_python_ast') if re.search('/'+f+r'-[^/]+/s-',line)),'unknown');tb=next((t for t in ('dep-graph','query-cache')if 'ohm-packed-'+t in line),'unknown')
       act='create' if 'O_CREAT' in line else 'open_read' if 'O_RDONLY' in line else line.split('(',1)[0];events[(fam,tb,act)]+=1
    assert hf.hexdigest()==hs and n==nn
    evidence.append([nf,nn,hs,gs])
   assert sorted(actual)==w['dirty'] and kk['Wild']==0 and not ({'wrap','tables','zstd','gzip'}&set(execs)) and not execs.get('ld.bfd',0)
   positive=[(pid,ev)for pid,kind,ev in kk['table_access'] if any(e[3]==0 for e in ev)]
   owners=[]
   if positive:
    verified=watch.get(s+'/'+phase,{})
    for tid,ev in positive:
     obs=verified.get(str(tid)); assert obs is not None and obs[1]==tid and obs[3]=='rustc' and obs[4:]==ad['physical']['bin/rustc'][:2],(s,phase,tid,obs,ad['physical']['bin/rustc'])
     cargo_compilers={k[2]:k[0]for k in kk['rustc']}; assert obs[0] in cargo_compilers,(s,phase,tid,obs,cargo_compilers)
     owners.append({'tid':tid,'rustc_pid':obs[0],'crate':cargo_compilers[obs[0]],'actual_rustc_inode':obs[4:],'events':sum(x[3]==0 for x in ev)})
   kaf={'live_compiler_thread_owners':owners,'full':sorted(actual),'wild':0,'events':{'/'.join(k):v for k,v in sorted(events.items())},'actual_execs':dict(execs),'trace_merkle':signature(sorted(evidence)),'trace_files':len(evidence),'trace_bytes':sum(f[1] for f in evidence)}
  rows[phase]={'source':state,'tree':g['tree'],'grammar':g['file'],'typed':w['typed'],'dirty':w['dirty'],'cargo_elapsed_ns':None if kaf else w['usage']['wall_ns'],'stderr':w['usage']['stderr'],'stdout':w['usage']['stdout'],'raw_result':hh,'elf':hh0,'verdict':got,'rlibs':by,'storage':{'bytes':st['combined'],'alternate_exclusive':st['alternate'],'alternate_by_type':st['categories'],'session_count':len(st['families']),'packed_counts':dict(packed)},'kernel':kaf}
 for phase,z in rows.items():
  state=z['source']
  if (ro+'/'+state) in result['refs']:assert result['refs'][ro+'/'+state]['elf']==z['elf']
for s,rr in result['observations'].items():
 ro=rd(r/'runs'/s/'terminal.json')['role']
 for ph,z in rr.items():
  assert z['elf']==result['refs'][ro+'/'+z['source']]['elf']
  for name,a in z['rlibs'].items():
   b=lookup[(ro,z['source'],name)];objs=sorted([size,h]for n,size,h in b['members']if n.endswith('.o'))
   a.update(archive_matches_empty=a['sha']==b['sha'],native_objects_match_empty=a['object_body_set']==signature(objs),metadata_matches_empty=a['metadata']==[[n,sz,h]for n,sz,h in b['members']if n in ('lib.rmeta','lib.rmeta-link')])
assert len({v['elf']for v in result['refs'].values()})>=3
result['principals']=reg['orders'];result['prior_host']='Linux/x86_64';result['observer_sha256']=digest(r/'verification-v1/offclock-threads.py');result['independent_tid_snapshot']=digest(watch_path)
print(json.dumps(result,sort_keys=True,separators=(',',':')))
