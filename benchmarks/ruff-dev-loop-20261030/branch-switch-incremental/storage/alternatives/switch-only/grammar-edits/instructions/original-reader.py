from pathlib import Path
import gzip,hashlib,json,os,re,subprocess,sys
r=Path(sys.argv[1]).resolve();v=r/'verification-v1';op=r/'ops';read=lambda p:json.loads(p.read_bytes());cfg=read(op/'study.json')
def sha(p):
 with p.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
def zero(n):assert(v/(n+'.exit')).read_text()=='0\n'
def reader_rows(f,pid,log):
 costs=0;edge=False;events=[];ticks=[];pids=[]
 with gzip.open(f,'rb')as src:
  for row in src:
   if row.startswith(b'events: '):events.append(row.split()[1:])
   elif row.startswith(b'totals: '):ticks.append(int(row.split()[1]))
   elif row.startswith(b'pid: '):pids.append(row.split()[1])
   elif row.startswith(b'calls='):assert not edge;edge=True
   elif row[:1] in b'0123456789+-*'and row.strip():
    if edge:edge=False
    else:costs+=int(row.split()[-1])
 assert not edge and pids==[str(pid).encode()] and events==[[b'Ir']] and ticks==[costs] and costs>0
 raw=gzip.decompress(log.read_bytes());ns=re.findall(rb'^=='+str(pid).encode()+rb'== Collected\s+:\s+([\d,]+)\s*$',raw,re.M);assert len(ns)==1 and int(ns[0].replace(b',',b''))==costs
 return costs
def obj(e):
 return {c:sorted((n,h)for name,n,h in g['members'] if name.endswith('.o'))for c,g in e['rlibs'].items()}
zero('build-tracer');zero('acquisition');d=read(v/'calibration.json');assert d['deltas']==[0,300000,0,300000,300000,0]
subprocess.run(['sha256sum','--quiet','-c','EARLY.sha256'],cwd=op,check=True)
arms='RK';obs={};refs={};ident={};warm=0;seen=0;argv_all=set();sourcefiles={}
for slot in cfg['slots']:
 p=r/'runs'/slot;ref=slot.startswith('ref-');role=slot.split('-')[1]if ref else slot[-1]
 ad=read(p/'admission.json');sd=read(op/('sdk-'+role+'.json'));ter=read(p/'terminal.json');assert ad['registry_ro']and ad['empty']and ter['driver_pre']==ter['driver_post']==ad['physical'][sd['driver']]
 ide={'driver':sd['native'][sd['driver']],'compiler':sd['native']['bin/rustc'],'driver_inode':ad['physical'][sd['driver']],'compiler_inode':ad['physical']['bin/rustc'],'cargo':ad['cargo'],'wild':ad['wild'],'standard_library':{n:hh for n,hh in sd['native'].items()if n.startswith('lib/rustlib/')},'cargo_sha':cfg['cargo'],'wild_sha':cfg['wild']}
 assert ident.setdefault(role,ide)==ide and ide['driver']==cfg['driver'][role]
 stable=ident[role]['standard_library'];assert len(stable)==53
 for ph,h in ter['hashes'].items():
  b=p/ph;o=read(b/'result.json');assert sha(b/'result.json')==h and read(b/'run-reader.json')['exit']==0 and read(b/'link-reader.json')['exit']==0
  c=read(b/'cargo.json');assert c['exit']==0 and c['stdout']==sha(b/'cargo.stdout')and c['stderr']==sha(b/'cargo.stderr') and 'wall' not in c
  cs=list(map(json.loads,(b/'cargo.stdout').read_bytes().splitlines()));assert cs[-1]=={'reason':'build-finished','success':True};uu=[q for q in cs if q['reason']=='compiler-artifact'];assert len(uu)==o['typed']==97
  dirty=sorted(q['target']['name']for q in uu if not q['fresh']);assert dirty==o['dirty'];state=o['state'];g=o['git'];assert g['tree']==sourcefiles.setdefault(state,g['tree'])
  elf=r/'full-outputs'/o['ELF'];assert sha(elf)==o['ELF']and elf.read_bytes()[:4]==b'\x7fELF';assert (b/'run-reader.stdout').read_text().strip()==o['verdict']=='Expr='+('64'if state=='A'else'56')+' signed-expression='+('accepted'if state=='C'else'rejected');seen+=1
  er=refs.setdefault(role+'/'+state,{'ELF':o['ELF'],'verdict':o['verdict'],'objects':obj(o)});assert (er['ELF'],er['verdict'],er['objects'])==(o['ELF'],o['verdict'],obj(o));assert all(er['objects'].values())
  if ref:
   assert len(dirty)==97 and ph=='empty'
   # Reopen the two original rlibs from the still-mounted empty-reference store.
   for name,a in o['rlibs'].items():
    target,=[q for q in uu if q['target']['name']==name and 'lib'in q['target']['kind']]
    for fname in target['filenames']:
     pa=Path(fname)
     if pa.suffix=='.rlib':assert sha(r/'ram/stores'/slot/pa.relative_to(r/'view'))==a['sha']
   continue
  if ph in ('edit-B','restore-B'):
   cx=o['Ir'];pid=cx['PID'];z=b/'callgrind';assert dirty==['ruff_python_parser']and cx['Wild']==0
   stderr=(b/'cargo.stderr').read_bytes();assert re.findall(rb'^compiler (\d+) (.+) (\d+) (\d+)$',stderr,re.M)==[(str(pid).encode(),b'ruff_python_parser',b'1',b'0')] and re.search(rb'^cargo 0\nlinks 0$',stderr,re.M)
   add=read(z/'counts.json');assert list(add['crates'])==['ruff_python_parser']and not add['wild_links'];expected=add['crates']['ruff_python_parser']
   ledger={n:[(z/n).stat().st_size,sha(z/n)]for n in cx['raw']};assert ledger==cx['raw']
   av=(z/('rustc.'+str(pid)+'.argv')).read_bytes();argv_all.add(hashlib.sha256(av).hexdigest());assert hashlib.sha256(av).hexdigest()==expected['argv_sha256']==cx['argv'];assert b'-Zohm-branch-cache=yes\x00'in av and b'ohm-check-relink-inputs'in av and not b'-Zlink-only'in av
   flag=(z/('rustc.'+str(pid)+'.jobserver')).read_bytes();fds=dict(l.split(' ',1) for l in (z/('rustc.'+str(pid)+'.fds')).read_text().splitlines());pipes=[fds[str(n)]for n in cx['jobserver']];assert len(set(pipes))==1 and pipes[0]==cx['pipe'] and re.search(rb'--jobserver-(fds|auth)='+(','.join(map(str,cx['jobserver']))).encode(),flag)
   ir=reader_rows(z/expected['profile'],pid,z/('valgrind.'+str(pid)+'.'+str(pid)+'.gz'));assert ir==cx['Ir']==expected['Ir']
   assert list(z.glob('wild.*.argv'))==[] and bool(r/'runs'/slot/('native-'+ph)) and sha(p/('native-'+ph)/'native.argv')==cx['argv']
   obs.setdefault(slot,{})[ph]={'Ir':ir,'ELF':o['ELF'],'verdict':o['verdict'],'argv':cx['argv'],'PID':pid,'jobserver':cx['jobserver'],'raw_sha':ledger,'native_argv_sha':sha(p/('native-'+ph)/'native.argv'),'original_result':h,'cargo_stdout':c['stdout'],'cargo_stderr':c['stderr'],'native_objects':len(obj(o)['ruff_python_parser']),'native_object_multiset':hashlib.sha256(json.dumps(obj(o),sort_keys=True).encode()).hexdigest()};warm+=1
  elif ph.startswith('unchanged'):assert dirty==[]
  elif ph.startswith('native-'):
   assert dirty==['ruff_python_parser'] and not o['kernel']['Wild'];assert sha(b/'native.argv')==o['kernel']['argv_sha256']
   assert all(sha(b/k)==h for k,h in o['kernel']['raw_trace'].items())
  elif ph=='empty-A':assert len(dirty)==97
  else:assert dirty==['ruff_python_ast','ruff_python_parser']
assert warm==8 and len(argv_all)==1 and seen==52 and ident['R']['standard_library']==ident['K']['standard_library']
for st in 'ABC':assert refs['R/'+st]['ELF']==refs['K/'+st]['ELF']
shortrefs={k:{'ELF':u['ELF'],'verdict':u['verdict'],'native_objects':{n:len(ls)for n,ls in u['objects'].items()}}for k,u in refs.items()}
out={'schema':1,'source':{role:cfg['raw'if role=='R' else 'compact']for role in arms},'trees':sourcefiles,'roles':ident,'rows':obs,'refs':shortrefs,'counts':{'profiles':warm,'native_receipts':seen,'stock_wild_during_measured_builds':0,'blocks':2},'provenance':{'registration':sha(op/'plan-counter.json'),'scripts':sha(op/'EARLY.sha256'),'calibration':d,'raw_arms':sha(r/'complete.json')}}
(v/'projection.json').write_text(json.dumps(out,sort_keys=True)+'\n');(v/'terminal.json').write_text(json.dumps({'projection':sha(v/'projection.json'),'validation':'8 complete per-process parser Ir profiles and literal uninstrumented flanks, 52 authentic reference products/typed/verdict receipts','scripts':out['provenance']['scripts'],'raw':out['provenance']['raw_arms']},sort_keys=True)+'\n')
