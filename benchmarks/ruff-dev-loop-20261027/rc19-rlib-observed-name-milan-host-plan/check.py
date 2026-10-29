"""Reject a different machine class, reference, source, admission order or storage substrate."""
from pathlib import Path
import json
r=Path(__file__).resolve().parent
read=lambda n:json.loads((r/n).read_bytes())
s,a,b=[read(x+'.json')for x in ('registration','original','new')]
assert s['observed_name_plan_git']=='86fd410922315ae22b9d3de58f50b30ba1e8939a' and s['observed_name_plan_sha256']=='0184771b39300ce849a1eb46d5590031cbf9d80855a383b4dcdc1fbdeca184d0'
assert s['current_input_plan_git']=='a644772c28607282fc06bb7c72f08225ea04f0a6' and s['milan_old_verified_sha256']=='45b122161aaa2ca02857ab4c208e823d16275a740cb13291b2cec2df11c6d323'
assert a['cpu']==b['cpu']=={'os_release':'7.0.0-38-generic','model':'AMD EPYC-Milan Processor','family':25,'stepping':1,'model_id':1,'count':32,'sockets':1,'threads_per_core':1,'numa_nodes':1}
assert a['boot_id']!=b['boot_id'] and a['native_executables']==b['native_executables'] and a['affinity']==b['affinity']==list(range(32))
assert b['uid']==b['gid']==1000 and all(b['new_destinations_absent'].values()) and not a['active_compilers'] and not b['active_compilers']
assert b['owners']['root'][:2]==b['owners']['home-root'][:2]==[0,0] and b['owners']['owner'][:2]==b['owners']['scratch-owner'][:2]==[1000,1000]
assert b['mounts']['home']['source']!=b['mounts']['scratch']['source'] and all(b['mounts'][m]['filesystem']=='ext4'for m in ('home','scratch'))
assert s['image_bytes']==16*2**30 and s['external_floor_each']==25*2**30 and s['in_image_floor']==2*2**30
assert b['mounts']['scratch']['free']-s['image_bytes']>=s['external_floor_each'] and b['mounts']['home']['free']-s['case_storage']['separate_home_budget_bytes']>=s['external_floor_each']
assert all(a['mounts'][m]['free']<s['external_floor_each']for m in ('scratch','home','shm')) and s['old_image']['above_floor']==329265152<s['old_image']['measured_two_P_transitions_before_final_commit']
assert s['source_tree']['seed']['regular_unique_bytes']==1368528501 and s['source_tree']['pristine']['regular_unique_bytes']==90239437
assert s['admission_order']==[['parent','B'],['parent','A'],['historical','B'],['historical','A']] and s['scored_pairs_if_both_hosts_qualify_and_granted']==8
assert s['cpu_sets']=={'cargo':list(range(8)),'passive_watcher':[8]} and s['cargo_runs_before_grant']==0 and not s['authorization_for_clocks']
print('Matched Milan class, two physical hosts, native tools, custody, enforced capacity and four prespecified admissions verified.')
