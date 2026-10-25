"""Native raw gates; elapsed payloads are hashed, never decoded here."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import stat
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
import dirty_fixture
import env_trace
import output_admission
import packages
import maintenance
import timer_properties
import registry_cache
import admission
import window


def quiet_samples(rows, hostname):
    assert len(rows) == 4
    expected = {'cpu%d' % i for i in range(8)}
    for before, after in zip(rows, rows[1:]):
        assert before['host'] == after['host'] == hostname
        assert not before['competing_jobs'] and not after['competing_jobs']
        assert set(before['cpu']) == set(after['cpu']) == expected
        total = sum(after['cpu'][key][0]-before['cpu'][key][0] for key in expected)
        idle = sum(after['cpu'][key][1]-before['cpu'][key][1] for key in expected)
        assert total > 0 and 0 <= idle <= total and (total-idle)/total <= .10


def admission_window(directory, margin, hostname):
    rows = [json.loads(line) for line in (directory/'window-observations.jsonl').read_text().splitlines()]
    assert rows and rows[-1]['ready'] is True
    assert all(row['ready'] == window.ready(row, margin) for row in rows)
    waits = [row['wait_elapsed_seconds'] for row in rows]
    assert waits == sorted(waits) and all(0 <= value <= 1200 for value in waits)
    selected = len(rows)-1
    quiet_samples(json.loads((directory/('quiet-%03d.json' % selected)).read_bytes()), hostname)
    strict = json.loads((directory/('strict-admission-%03d.json' % selected)).read_bytes())
    assert not strict['other_workloads']
    assert window.ready(json.loads((directory/'window-entry.json').read_bytes()), margin)


def validate(root, inputs_sha, protocol, *, resolve=lambda p:Path(p)):
    root=Path(root)
    completion=json.loads((root/'completion.json').read_bytes())
    assert completion['state']=='complete' and completion['inputs_sha256']==inputs_sha
    assert C.sha(root/'inputs.json')==inputs_sha
    assert C.sha(root/'manifest.json')==completion['manifest_sha256']
    manifest=json.loads((root/'manifest.json').read_bytes())
    assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}==set(manifest)|{'manifest.json','completion.json'}
    assert not any(p.is_symlink() for p in root.rglob('*'))
    for name,row in manifest.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        local=root/name;s=local.stat()
        assert stat.S_ISREG(s.st_mode) and s.st_size==row['bytes'] and stat.S_IMODE(s.st_mode)==row['mode']
        assert C.sha(local)==row['sha256']
    terminal=json.loads((root/'terminal.json').read_bytes())
    assert C.sha(root/'terminal.json')==completion['terminal_sha256']
    assert terminal['state']=='complete' and terminal['failure'] is None and terminal['cleanup_failure'] is None
    assert all(terminal[k] for k in ('source_restored','cargo_restored','active_paths_absent','banks_parked'))
    assert terminal['parent_fresh']=={'baseline':True,'candidate':True} and terminal['effects_analyzed'] is False
    packet=json.loads((root/'inputs.json').read_bytes())
    def reference(row):
        p=resolve(row['path']);assert C.sha(p)==row['sha256'];return json.loads(p.read_bytes())
    assert reference(packet['protocol'])==protocol
    old=reference(packet['instruction_inputs'])
    admission.validate_bound_input(packet, old, protocol, reference)
    for name, row in packet['controls'].items():
        assert C.sha(Path(__file__).with_name(name)) == row['sha256']
    phase=packet['phase'];mode=terminal['mode']
    authority=json.loads((root/'authority.json').read_bytes())
    execution=json.loads((root/'execution.json').read_bytes())
    assert authority['status']=='approved' and authority['phase']==phase and authority['mode']==mode
    assert authority['inputs_sha256']==execution['inputs_sha256']==inputs_sha
    assert execution['source_sha256']==packet['controls']['collect_native.py']['sha256']
    assert execution['authority_sha256']==C.sha(root/'authority.json')
    if mode=='measure':
        cohort=reference(authority['cohort'])
        assert cohort['state']=='fixed-registry-native-cohort' and cohort['phase']==phase
        assert cohort['protocol_sha256']==packet['protocol']['sha256']
        assert cohort['collector_sha256']==execution['source_sha256']
        assert [r['hostname'] for r in cohort['members']]==protocol['hosts']
        assert cohort['members'][packet['host_index']]['inputs_sha256']==inputs_sha
    plan=protocol['phases'][phase]
    orders=['AB'] if mode=='rehearsal' else plan['orders'][str(packet['host_index'])]
    assert terminal['schedule']==orders
    expected=[(i,pos,protocol['labels'][letter],order) for i,order in enumerate(orders) for pos,letter in enumerate(order)]
    assert [(r['pair'],r['position'],r['variant'],r['order']) for r in terminal['samples']]==expected
    original_path=resolve(protocol['native_root']+'/source-original.rs')
    original=original_path.read_bytes();assert hashlib.sha256(original).hexdigest()==old['source']['sha256']
    margin=protocol['rehearsal_margin'] if mode=='rehearsal' else packet['margin']
    def fresh_gate(directory,label,source_sha):
        rows=env_trace.trace_records((directory/(label+'.trace')).read_text())
        successful=[r for r in rows if r['successful']]
        assert len(successful)==1 and successful[0]['executable']==old['root']+'/bin/cargo'
        assert successful[0]['argv']==protocol['command']
        assert successful[0]['environment']==[k+'='+v for k,v in old['cargo_environment'].items()]
        command=json.loads((directory/(label+'.command.json')).read_bytes())
        status=json.loads((directory/(label+'.exit.json')).read_bytes())
        assert command['trace'] and not command['timed'] and command['source_sha256']==source_sha
        assert status['returncode']==0 and status['failure'] is None
    for arm in C.ARMS:
        fresh_gate(root,arm+'.initial-fresh',old['source']['sha256'])
    for pair,order in enumerate(orders):
        d=root/('pair-%02d'%pair)
        prepared=json.loads((d/'prepared.json').read_bytes())
        assert prepared['pair']==pair and prepared['order']==order and prepared['both_before_fresh']
        batch=Path(protocol['native_root'])/'records'/(mode+'-'+phase+'-01')
        before=dirty_fixture.content(original,batch,'measurement',pair,'before')
        after=dirty_fixture.content(original,batch,'measurement',pair,'after_')
        assert prepared['source_before_sha256']==hashlib.sha256(before).hexdigest()
        assert prepared['source_after_sha256']==hashlib.sha256(after).hexdigest()
        assert prepared['source_bytes']==len(after)==len(before) and prepared['changed_bytes']==sum(a!=b for a,b in zip(before,after))==5
        entry=json.loads((d/'window-entry.json').read_bytes())
        admission_window(d, margin['entry_window_seconds'], packet['hostname'])
        assert maintenance.ready(entry,margin['entry_window_seconds'])
        for timer in entry['apt_timers'].values():
            remaining=timer_properties.remaining_seconds(timer,entry['clock_ns'])
            assert remaining is not None and remaining>=margin['entry_window_seconds']
        start=json.loads((d/'pair-start.json').read_bytes())
        finishes=['pair-finish.json']+[arm+'.'+side+'-window.json' for arm in C.ARMS for side in ('before','after')]
        for finish_name in finishes:
            end=json.loads((d/finish_name).read_bytes())
            assert packages.quiet(end['packages'])
            assert 0<=end['monotonic_us']*1000-start['monotonic_ns']<=margin['finish_budget_seconds']*10**9
            import datetime
            delta=(datetime.datetime.fromisoformat(end['utc'])-datetime.datetime.fromisoformat(start['utc'])).total_seconds()
            assert 0<=delta<=margin['finish_budget_seconds']
            for name in maintenance.HEAVY:
                a,b=entry['services'][name],end['services'][name]
                assert b['service']['ActiveState']=='inactive' and b['service']['SubState']=='dead' and b['service']['ExecMainStatus']=='0'
                assert a['timer']['LastTriggerUSecMonotonic']==b['timer']['LastTriggerUSecMonotonic']
                assert a['service']['ExecMainStartTimestampMonotonic']==b['service']['ExecMainStartTimestampMonotonic']
                deadline=maintenance.span_us(a['timer']['NextElapseUSecMonotonic'])
                assert end['monotonic_us']<deadline
                utc_deadline=datetime.datetime.fromisoformat(entry['utc'])+datetime.timedelta(microseconds=deadline-entry['monotonic_us'])
                assert datetime.datetime.fromisoformat(end['utc'])<utc_deadline
            for name in packages.NAMES:
                assert entry['packages']['services'][name]['ExecMainStartTimestampMonotonic']==end['packages']['services'][name]['ExecMainStartTimestampMonotonic']
            apt=json.loads((d/finish_name).with_suffix('.apt.json').read_bytes())
            assert apt['apt_timers']==entry['apt_timers']
            for timer in apt['apt_timers'].values():
                remaining=timer_properties.remaining_seconds(timer,apt['clock_ns'])
                assert remaining is not None and remaining>0
        for arm in C.ARMS:
            cache_arm = 'baseline' if phase == 'aa' else arm
            for name in ('before-cache-initial', 'prepared-cache', 'native-cache-before', 'native-cache-after', 'restored-cache'):
                witness = json.loads((d/(arm+'.'+name+'.json')).read_bytes())
                registry_cache.validate_snapshot(witness, old['cargo_environment']['CARGO_HOME'], cache_arm)
            for side in ('before','after'):
                activity=json.loads((d/(arm+'.'+side+'-activity.json')).read_bytes())
                assert activity['native']['host'] == packet['hostname']
                assert not activity['native']['competing_jobs'] and not activity['strict']['other_workloads']
            for label in (arm+'.before-fresh',arm+'.after-fresh',arm+'.restored-fresh'):
                source_sha=prepared['source_before_sha256'] if '.before-' in label else prepared['source_after_sha256'] if '.after-' in label else old['source']['sha256']
                fresh_gate(d,label,source_sha)
                assert json.loads((d/(label+'.fresh.json')).read_bytes())['compiler_calls']==0
            label=arm+'.native'
            command=json.loads((d/(label+'.command.json')).read_bytes())
            expected_cargo=protocol['AA_cargo_by_label' if phase=='aa' else 'AB_cargo_by_label'][arm]
            assert command['argv']==protocol['command'] and command['environment']==old['cargo_environment']
            assert command['cargo_sha256']==expected_cargo and command['source_sha256']==hashlib.sha256(after).hexdigest()
            assert command['timed']==(mode=='measure') and not command['trace'] and not command['tests_executed']
            status=json.loads((d/(label+'.exit.json')).read_bytes())
            assert status['returncode']==0 and status['failure'] is None and status['new_session']
            assert (d/(label+'.elapsed.json')).exists()==(mode=='measure')
            for suffix in ('stdout','stderr'):
                r=packet['native_diagnostics'][arm][suffix]
                ref=resolve(r['path']);assert C.sha(ref)==r['sha256']
                assert C.diagnostics((d/(label+'.'+suffix)).read_text())==C.diagnostics(ref.read_text())
            for prefix in (arm+'.native',arm+'.restored'):
                raw=json.loads((d/(prefix+'.raw-outputs.json')).read_bytes())
                checks=json.loads((d/(prefix+'.outputs.json')).read_bytes())
                specs=packet['native_output_specs'][arm]
                output_admission.validate_records(checks,specs)
                assert [r['identity'] for r in raw]==[r['identity'] for r in checks]
                for r,spec in zip(raw,specs):
                    blob=resolve(r['blob']['path']);assert C.sha(blob)==r['blob']['sha256']==r['identity']['sha256']
                    adapted=dict(spec,path=str(blob),mode=0o400)
                    if spec['kind']=='uv-rlib':
                        adapted['reference']=dict(spec['reference'],path=str(resolve(spec['reference']['path'])))
                    proof=output_admission.inspect_output(adapted)
                    assert proof['identity']['sha256']==r['identity']['sha256']
            done=json.loads((d/'complete.json').read_bytes())
            assert done['state']=='complete' and done['parent_fresh']=={'baseline':True,'candidate':True}
    ownership=[json.loads(p.read_bytes()) for p in sorted(root.glob('ownership-*.json'))]
    assert ownership and all(row.get('state','quiescent')=='quiescent' for row in ownership)
    assert ownership[0]['previous_subreaper']==0 and ownership[-1]['restored_subreaper']==0
    worker=ownership[0]['worker_pid']
    for row in ownership:
        assert not row.get('terminated_owned_identities'), 'a valid native cohort cannot require forced termination'
        if row['label']=='reaped-cleanup':
            assert row['healthy_exit_required'] is True
            assert all(child['exitcode']==0 and child['ppid']==worker for child in row['children'])
    groups={row['expected_group'] for row in ownership if 'expected_group' in row}
    for sample in terminal['samples']:
        status=json.loads((root/(sample['label']+'.exit.json')).read_bytes())
        assert status['pid'] in groups
    for row in ownership:
        if 'expected_group' not in row:continue
        for observation in row['observations']:
            assert all(child['ppid']==worker and child['pgid']==child['sid']==row['expected_group'] for child in observation)
    return {'state':'all-native-raw-gates-passed','phase':phase,'mode':mode,'inputs_sha256':inputs_sha,
            'completion_sha256':C.sha(root/'completion.json'),'manifest_sha256':C.sha(root/'manifest.json'),
            'samples':len(expected),'elapsed_payloads_decoded':False,'source_sha256':C.sha(__file__)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True)
    p.add_argument('--inputs-sha256',required=True);p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    C.save(a.output,validate(a.execution,a.inputs_sha256,json.loads(a.protocol.read_bytes())))
