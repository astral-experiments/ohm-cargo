"""Read only finalized native acquisitions and emit reproducible path-hashed evidence, with no environment values."""
from pathlib import Path
import hashlib,json,os
D=Path.home()/'.cache/ohm-script-hash-wall-rc19-v1';C=D/'current';host=os.uname().nodename;primary='loader-'in host;role='primary-linux' if primary else'independent-linux'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();dg=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest();read=lambda f:json.loads(f.read_bytes());pre=D/'release-native-final/pre.json';predata=read(pre);assert predata['terminal'];cross=D/'same-physical-crossover-v3/complete.json';q=read(cross)
def own(q):
 return {'euid':q['uid'],'egid':q['gid'],'affinity':q['affinity'],'actual_cargo_sha256':q['exe'],'same_ordinary_mount':'mnt:[' in q['mount_ns'],'uid_map':q['uidmap'],'paths':{str(p).replace(str(Path.home()),'$HOME'):{k:i[k]for k in ('uid','gid','mode','dev','ino')}for p,i in q['chain'].items()}}
def reads(q):
 return {'exec':q['tools'],'trace_digest_map':q['trace_files'],'registry_cache_hits':q['actual_registry_cache_reads'],'registry_inputs':q['actual_registry_prerequisites'],'file_observations':q['two_observations']}
cross_summary=[{'seed':z['seed'],'image':z['image'],'same_data':z['initial']==z['after'],'before':z['initial'],'after':z['after'],'ownership':own(z['exec']),'physical':reads(z['native']),'rows':z['rows'],'fresh':z['fresh']}for z in q['crossovers']]
initial={};phases={}
for arm in 'AB':
 f=D/'reports'/('final-pre-'+arm+'.json');r=read(f);assert predata['arms'][arm]['full_native']==sha(f);g=predata['arms'][arm];rpr=D/'reports'/('safe-identity-empty-'+arm)/'complete.json';ct=read(rpr)
 initial[arm]={'native_record_raw':sha(f),'cold_record_raw':sha(rpr),'cold_rows':ct['rows'],'cold_fresh':ct['fresh'],'unit_roster':r['ids'],'warm_rows':r['rows'],'warm_fresh':r['fresh'],'all_declared_files':g['files'],'artifact_identity':dg(g['files']),'products':{Path(n).suffix:s for n,s in r['products'].items()},'generated':r['zips'],'checks':dg(r['checks']),'generations':dg(r['generations']),'reader':r['reader'],'physical':reads(r['physical']),'actual':own(r['actual_exec'])}
race=D/('cpu-ptrace-adversaries-v4'if primary else'bounded-ptrace-adversaries-v4');rc=race/'complete.json';raceout=read(rc);assert raceout['terminal']
for arm,dirs in raceout['rows'].items():
 for direction,l in dirs.items():
  records=[]
  for r in l:
   lab=('ptrace-edge-'if primary else'bounded-ptrace-')+arm+'-'+direction+'-'+r['phase'];src=D/'reports'/lab;logs=read(src/'command.json');inv=read(src/'artifacts.json');assert logs['rc']==0 and inv['rows']==182
   records.append({'phase':r['phase'],'dirty':r['dirty'],'unit_identities':inv['ids'],'rows':inv['rows'],'fresh':inv['fresh'],'program':r['program'],'mode':r['mode'],'outer_zip':r['zip'],'quantity':r['archive_members'],'products':{Path(n).suffix:v for n,v in r['native_outputs'].items()},'events':r['events'],'stdout':logs['stdout'],'stderr':logs['stderr'],'native_generation':dg(r['generation']),'cargo':r['compiler_hash']})
  phases[arm+'-'+direction]=records
print(json.dumps({'role':role,'native_source':predata['source'],'unmodified_runner':predata['base'],'numeric_plan_ref':predata['source_plan'],'private_plan':predata['plan'],'actual_images':predata['images'],'preflight_raw':sha(pre),'exact_oracle':predata['oracle'],'per_arm':initial,'same_seed_crossovers':cross_summary,'same_seed_raw':sha(cross),'regular_file_changes':phases,'regular_file_changes_raw':sha(rc),'ptrace_tracer':raceout['hook'],'complete':True},sort_keys=True))
