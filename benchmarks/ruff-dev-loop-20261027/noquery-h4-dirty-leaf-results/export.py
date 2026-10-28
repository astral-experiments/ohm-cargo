"""Export every real wall time, typed native correctness observation and command status after the locked schedule."""
from pathlib import Path
import csv,fcntl,gzip,hashlib,io,json,os,socket,sys,tarfile
f=Path('/mnt/devbox-scratch/dev-user/ohm-ron-noquery-dirty-leaf-h4-20261028-fixeddeps-v1');os.environ['OHM_SCOPED_FIXTURE_ROOT']=str(f);sys.path.insert(0,str(f/'protocol'));import qualify as q
assert socket.gethostname()=='charlie-ohm-generic-perf-1024' and (f/'wall.rc').read_text().strip()=='0' and not (f/'first-wall-failure.txt').exists()
h=lambda x:hashlib.sha256(x).hexdigest();read=lambda p:json.loads(p.read_bytes());j=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()
b=f/'inputs/frozen-binding.json';q.configure(read(b));ledger=f/'wall-ledger';original=read(ledger/'complete.json');assert original['counts']=={'check':4752,'build':432} and original['times']==q.sha(ledger/'times.csv') and original['plan']==q.sha(f/'inputs/plan.json')
def write_tar(t,n,x):
 it=tarfile.TarInfo(n);it.size=len(x);it.mode=0o644;t.addfile(it,io.BytesIO(x))
def safe(v):
 for bad in (b'Authorization:',b'://',b'PRIVATE KEY',b'access_token=',b'/home/',b'/mnt/'):assert bad not in v,bad
 return v
with Path(read(b)['host_lock']).open('rb') as locked:
 fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)
 native=read(f/'inputs/native-qualification.json');data=io.BytesIO();seen_callers={};units=set();before={};count=0
 for kind in ['check','build']:
  for arm in 'BPN':
   for ph in ['wall-pre-fresh','wall-post-fresh']:
    d=f/'records'/(kind+'-'+arm)/ph;tr=q.fixture.trace(d);assert not tr['jobs'] and not tr['observer_probes'];raws={n.name:q.sha(n) for n in d.glob('exec.*')};before[kind+'-'+arm+'/'+ph]={'actual_processes':tr,'raw_trace_files_sha256':raws}
 with (ledger/'times.csv').open(newline='') as stream:
  for v in csv.DictReader(stream):
   kind=v['kind'];arm=v['arm'];direction=v['direction'];block,cycle,slot=(int(v[n]) for n in ('block','cycle','slot'));prefix=f'{block:02}-{kind}-{cycle:02}-{slot}-{arm}';d=ledger/'raw'/prefix;record=read(d/'observation.json');cmd=read(d/'commands.json')
   assert record['elapsed_ns']==int(v['elapsed_ns']) and record['trace'] is None and not record['fresh'] and record['units']==1 and not record['foreign_marker']
   assert len(cmd)==(3 if kind=='build' and direction=='restore' else 2)
   assert cmd[0]['inside_cargo_timer'] and sum(x['inside_cargo_timer'] for x in cmd)==1
   for i,status in enumerate(cmd):
    for channel in ('stdout','stderr'):assert q.sha(d/(str(i)+'.'+channel))==status[channel]
   assert [x['status'] for x in cmd]==([0,1] if direction=='edit' else [0]*len(cmd))
   raw=[json.loads(l) for l in (d/'0.stdout').read_bytes().splitlines()];z,=[x for x in raw if x.get('reason')=='compiler-artifact'];assert z['target']['name']=='ruff_text_size' and not z['fresh'] and raw[-1]=={'reason':'build-finished','success':True}
   assert not any(x.get('reason')=='compiler-message' for x in raw)
   artifact={'name':z['target']['name'],'kind':z['target']['kind'],'profile':z['profile'],'features':z['features'],'artifacts':[Path(a).name for a in z['filenames']],'exact_package_sha256':h(z['package_id'].encode()),'exact_source_sha256':h(z['target']['src_path'].encode()),'exact_manifest_spelling_sha256':h(z['manifest_path'].encode())}
   units.add(h(j(artifact)))
   if direction=='edit':
    report=(d/'1.stderr').read_bytes();assert b'E0599' in report and b'to_std_range' in report
   else:
    sha0=record['native_caller_file_sha256']
    if sha0 not in seen_callers:seen_callers[sha0]=q.sha(ledger/'callers'/sha0);assert seen_callers[sha0]==sha0
    if kind=='build':assert (d/'2.stdout').read_bytes().strip()==b'2-6'
   row={'slot':{k:int(n) if k in ('block','cycle','slot') else n for k,n in v.items() if k!='elapsed_ns'},'observation':record,'cargo_and_external_oracle_commands':cmd,'cargo_artifact':artifact,'source_observation':{'sha256':q.sha(d/'observation.json'),'typed_command_statuses':q.sha(d/'commands.json')}};data.write(safe(j(row))+b'\n');count+=1
 assert count==5184
 auth=read(f/'inputs/registered-activation.json');assert auth['binding']==q.sha(b) and auth['qualification']==original['native_gate'] and auth['plan']==original['plan']
 meta={'terminal':original,'exit_code':0,'earlier_unscored_workspace_exit':auth['earlier_unscored_workspace_exit'],'authority':{k:auth[k] for k in ['upstream_registration','source_provenance','native_admission']},'activation_sha256':q.sha(f/'inputs/registered-activation.json'),'retained_caller_sha256':sorted(seen_callers),'derived_typed_cargo_artifacts':sorted(units),'stdout_sha256':q.sha(f/'wall.stdout'),'stderr_sha256':q.sha(f/'wall.stderr'),'commands':count,'actual_before_and_after_fresh_qualified_commands':12,'compressed_oracles':'Every original per-command stdout/stderr SHA256, private complete logs retained on H4.'}
 with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
  for n,v in [('wall.csv',(ledger/'times.csv').read_bytes()),('rows.jsonl.gz',gzip.compress(data.getvalue(),compresslevel=6,mtime=0)),('terminal.json',safe(j(meta))+b'\n'),('pre-post.json',safe(j(before))+b'\n')]:write_tar(t,n,v)
