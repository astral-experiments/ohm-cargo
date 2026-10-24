import hashlib,json,os,platform,shutil,stat,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from remote_common import ROOT,run,save,sha,utc
os.umask(0o077);os.sched_setaffinity(0,set(range(24,32)))
controls=ROOT/'incoming/controls';bench=ROOT/'work/benchmark'
warm=json.loads((ROOT/'records/warm-complete.json').read_bytes())
assert warm['state']=='complete' and warm['check_commands_run']==0 and warm['baseline_native_state_restored']
for name in ('maintenance_02.py','restack_control_02.py','test_maintenance_02.py','test_binding.py'):
 target=bench/name;assert not target.exists();shutil.copy2(controls/name,target);assert sha(target)==sha(controls/name)
sys.path.insert(0,str(bench));import loader_fixture_delta as fixture;import maintenance_02 as maintenance;import restack_control_02 as control
root,manifest=fixture.load('uv-loader-restack');fixture.check_inputs(manifest)
assert sha(manifest['canonical_executable'])==manifest['variant_sha256']['baseline']
run('final-preflight/control-tests',['/usr/bin/python3','-I','-B','-m','unittest','discover','-s',str(bench),'-p','test_*.py'])
margin=warm['pair_reservation_seconds'];assert margin==210
ready=maintenance.wait_for_pair(ROOT/'records/maintenance-window-rehearsal-01.jsonl',margin)
save(ROOT/'records/maintenance-window-rehearsal-01.json',{'ready':ready,'pair_margin_seconds':margin,'no_cargo_check_run':True,'execution_authorized':False})
readiness=run('final-preflight/host-readiness',['/usr/bin/python3','-I','-B',str(controls/'readiness_remote.py')])
host=json.loads(readiness);assert host['host']=='charlie-ohm-loader-perf-1024' and host['cpu_count']==32
for name in ('apt-daily','apt-daily-upgrade'):
 text=host['services'][name]['service']['stdout'];assert 'ActiveState=inactive\n' in text and 'SubState=dead\n' in text
locks=Path('/proc/locks').read_text();locked=[]
for name in ('/var/lib/dpkg/lock-frontend','/var/lib/dpkg/lock','/var/lib/apt/lists/lock','/var/cache/apt/archives/lock'):
 p=Path(name)
 if not p.exists():continue
 s=p.stat()
 for line in locks.splitlines():
  for field in line.split():
   parts=field.split(':')
   if len(parts)==3:
    try:match=(int(parts[0],16),int(parts[1],16),int(parts[2]))==(os.major(s.st_dev),os.minor(s.st_dev),s.st_ino)
    except ValueError:continue
    if match:locked.append({'path':name,'record':line})
assert not locked
save(ROOT/'records/final-host-readiness.json',{'host':host,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'apt_lock_matches':locked,'proc_locks':locks,'observed_at':utc()})

protocol=json.loads((controls/'protocol-draft-01.json').read_bytes())
protocol.update(state='frozen-awaiting-root-authorization',created_at=utc(),pair_reservation_seconds=margin,pending_assets=[])
protocol['preflight']='Dedicated charlie-ohm-loader-perf-1024; complete native-only seeds and natural provenance; 210-second heavy-service admission before each complete pair, with service-cycle checks outside each native stopwatch. Original load averages remain recorded; no new generic numerical CPU-occupancy gate is claimed.'
protocol['correctness_tests']={'original_fixture_cases':31,'raw_receipt_cases':3,'original_maintenance_cases':8,'active_maintenance_cases':11,'binding_cases':6,'total_passed':59,'scope':'collector controls; no new Cargo testsuite claim'}
protocol['common_checkout_head']=protocol.pop('embedded_cargo_head')
protocol['cargo_version_scope']='Both actual -Vv outputs are byte-identical and omit commit fields. The common checkout HEAD is source provenance, not an assertion that a commit appears in the emitted version.'
protocol['maintenance_decoder']='Repeated TimersMonotonic values are preserved in order; duplicate scalar, unknown and missing properties reject.'
protocol_path=ROOT/'protocol-final-01.json';save(protocol_path,protocol)
entry=ROOT/'records/confirmation-01.entry.json';terminal=ROOT/'records/confirmation-01.terminal.json'
output=ROOT/'work/benchmark-results/loader-restack-confirmation-01';output.parent.mkdir(exist_ok=True);assert not output.exists() and not entry.exists() and not terminal.exists()
configuration=json.loads((root/'paired.json').read_bytes())
original_prepare=list(configuration['prepare_command'])
configuration['prepare_command']=['/usr/bin/python3','-I','-B',str(bench/'restack_control_02.py'),'prepare','--entry',str(entry),*original_prepare[3:]]
assert configuration['command']==protocol['command'] and configuration['env']==manifest['environment']
configuration['record_files']=sorted(set(configuration['record_files'])|{str(protocol_path),str(bench/'maintenance_02.py'),str(bench/'restack_control_02.py')})
configuration_path=root/'paired-confirmation-01.json';save(configuration_path,configuration)
shutil.copy2(root/'journal.jsonl',ROOT/'records/premeasurement-journal.jsonl')

def ref(p):return {'path':str(p),'sha256':sha(p)}
paths={Path(p) for p in configuration['record_files']}|{configuration_path,protocol_path,Path('/proc/sys/kernel/random/boot_id'),Path('/etc/hostname')}
for p in bench.glob('*.py'):paths.add(p)
for name in ('warm-complete','warm-02-correction','native-seeds-reviewed','excluded-restore-headroom','pair-headroom','sdk6-runtime-manifest','native-control-tools','matched-build-complete','matched-build-recipe','build-tools-before','build-tools-after','inherited-cargo-configuration','final-host-readiness','maintenance-window-rehearsal-01','premeasurement-journal'):
 paths.add(ROOT/'records'/(name+('.jsonl' if name=='premeasurement-journal' else '.json')))
for arm in ('baseline','candidate'):
 for name in ('manifest.json','inventory.jsonl','runlist.json'):paths.add(root/'snapshots'/arm/name)
 for suffix in ('stdout','stderr'):paths.add(root/'logs'/('seed-'+arm+'.'+suffix))
 paths.add(ROOT/'artifacts'/arm/'cargo');paths.add(ROOT/'artifacts'/arm/'identity.json')
symlinks=[]
for row in json.loads((ROOT/'records/sdk6-runtime-manifest.json').read_bytes())['files']:
 if row['type']=='file':paths.add(Path(row['path']))
 else:symlinks.append({k:row[k] for k in ('path','target','resolved')})
for row in json.loads((ROOT/'records/native-control-tools.json').read_bytes()):
 p=Path(row['path']);assert sha(p)==row['sha256'];paths.add(p)
rows=[]
for p in sorted(paths):
 assert p.is_file(),p;s=p.stat();rows.append({'path':str(p),'sha256':sha(p),'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode)})
inputs={'schema_version':1,'state':'frozen-awaiting-root-authorization','fixture_name':manifest['name'],'host':{'hostname':host['host'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cpu_model':host['cpu_model']},'entry_path':str(entry),'terminal_path':str(terminal),'protocol':ref(protocol_path),'configuration':ref(configuration_path),'original_acceptance':protocol['acceptance'],'files':rows,'symlinks':symlinks,'first_check_calls_before_freeze':0,'seed_manifests':{a:ref(root/'snapshots'/a/'manifest.json') for a in ('baseline','candidate')}}
inputs_path=ROOT/'inputs-final-01.json';save(inputs_path,inputs);control.verify_files(inputs);fixture.check_inputs(manifest)
authority={'schema_version':1,'status':'pending','inputs_sha256':sha(inputs_path),'protocol_sha256':sha(protocol_path),'output':str(output),'pairs':12,'warmup_pairs':0,'seed':2026102126,'stop_rules':protocol['stop_rules'],'approval_requirement':'Root must approve this exact pending template before dispatch'}
authority_path=ROOT/'authority-01.template.json';save(authority_path,authority)
# Exercise actual frozen input/config joins without creating the real entry/output or approving an authority.
assert control.read_ref(ref(inputs_path))==inputs and control.read_ref(inputs['configuration'])==configuration
assert configuration['prepare_command'][6]==str(entry)
assert protocol['balanced_order_plan']==[list(x) for x in control.paired.make_plan(12,2026102126)]
assert not output.exists() and not entry.exists() and not terminal.exists()
result={'state':'ready-for-root-review','inputs':ref(inputs_path),'protocol':ref(protocol_path),'authority_template':ref(authority_path),'configuration':ref(configuration_path),'output':str(output),'entry_absent':True,'output_absent':True,'seed_parent_restored':'baseline','first_check_calls':0,'control_tests':59,'pair_margin_seconds':margin,'observed_at':utc()}
save(ROOT/'records/final-input-binding-01.json',result);print(json.dumps(result))
