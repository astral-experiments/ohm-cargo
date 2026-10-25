"""Private copies only; no Cargo command, compiler, profiler or elapsed sample."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import inventory
import admission
import registry_cache


def parked_context(bank):
    workspace = bank/'target/debug/build/workspaces'
    registry = bank/'shared/debug/build/registries'
    info = bank/'target/.rustc_info.json'
    return {'workspace_roots': sorted(p.name for p in workspace.iterdir()),
            'workspace_contexts': sorted(str(p.relative_to(workspace)) for p in workspace.glob('*/*') if p.is_dir()),
            'registry_contexts': sorted(p.name for p in registry.iterdir()) if registry.is_dir() else None,
            'rustc_info': {'sha256': C.sha(info), 'bytes': info.stat().st_size,
                          'mtime_ns': info.stat().st_mtime_ns, 'inode': info.stat().st_ino}}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--request', type=Path, required=True)
    p.add_argument('--request-sha256', required=True); a=p.parse_args()
    os.umask(0o077)
    request=C.read_ref({'path':str(a.request),'sha256':a.request_sha256})
    phase=request['phase']
    assert phase in ('aa','ab') and request['state']=='native-'+phase.upper()+'-preparation-request'
    old=C.read_ref(request['instruction_inputs']); protocol=C.read_ref(request['protocol'])
    release=C.read_ref(request['instruction_release'])
    assert release['hostname']==request['hostname']
    assert request['root_authority']['status'] == 'approved-native-preparation'
    assert request['root_authority']['protocol_sha256'] == request['protocol']['sha256']
    admission.validate_prerequisites(dict(request, host_index=protocol['hosts'].index(request['hostname'])), old, protocol, C.read_ref)
    os.sched_setaffinity(0, range(9,16))
    assert release['state'] == 'released-registry-host-to-native'
    assert release['owned_workloads_remaining'] == release['owned_connections_remaining'] == 0
    assert release['source_and_cargo_restored'] and release['banks_parked']
    assert os.uname().nodename==request['hostname']==old['host']['hostname']
    assert C.sha('/etc/machine-id')==old['host']['machine_id_sha256']
    assert os.uname().release==old['host']['kernel'] and os.getuid()==old['host']['uid']==1000
    assert str(C.NATIVE)==protocol['native_root']
    for row in request['controls'].values(): assert C.sha(row['path'])==row['sha256']
    assert all(not os.path.lexists(C.ROOT/name) for name in C.PARTS)
    assert C.identity(C.SOURCE)==old['source'] and C.identity(C.ROOT/'bin/cargo')==old['original_cargo']
    for arm in C.ARMS: C.verify_file(old['variants'][arm]['artifact'])
    if phase=='ab':
        decision=C.read_ref(request['aa_decision'])
        assert decision['phase']=='aa' and decision['both_passed'] is True
    log=C.NATIVE/'records'/('setup-'+phase+'-01');log.mkdir(parents=True)
    C.save(log/'started.json',{'state':'copying-private-native-states','utc':C.utc(),'request_sha256':a.request_sha256,'samples':0})
    assert not (C.NATIVE/'phases'/phase).exists()
    (C.NATIVE/'phases'/phase/'banks').mkdir(parents=True)
    if phase=='aa':
        assert not (C.NATIVE/'runtime-copies').exists()
        (C.NATIVE/'runtime-copies').mkdir()
        assert not (C.NATIVE/'source-original.rs').exists()
        shutil.copyfile(C.SOURCE,C.NATIVE/'source-original.rs');os.chmod(C.NATIVE/'source-original.rs',0o400)
        runtime={}
        for arm in ('original',*C.ARMS):
            if arm=='original': path=C.ROOT/'bin/cargo'
            else:
                path=C.NATIVE/'runtime-copies'/arm
                shutil.copyfile(old['variants'][arm]['artifact']['path'],path);os.chmod(path,0o700)
                assert path.stat().st_nlink==1
            runtime[arm]=dict(C.identity(path),dev=path.stat().st_dev,inode=path.stat().st_ino)
    else:
        previous=C.read_ref(request['aa_inputs'])
        runtime=previous['runtime_identities']
        assert C.sha(C.NATIVE/'source-original.rs')==old['source']['sha256']
        for arm,row in runtime.items():
            path=C.ROOT/'bin/cargo' if arm=='original' else C.NATIVE/'runtime-copies'/arm
            assert C.sha(path)==row['sha256'] and [path.stat().st_dev,path.stat().st_ino]==[row['dev'],row['inode']]
    manifests={}; originals={}; banks={}; contexts={}; total=0
    for arm in C.ARMS:
        donor=admission.instruction_bank(old,C.ROOT,arm)
        rows=inventory.inventory(donor);total+=inventory.total_bytes(rows)
        C.save(log/(arm+'.instruction-bank.json'),rows)
        originals[arm]=C.ref(log/(arm+'.instruction-bank.json'))
    output_bytes=max(sum(r['bytes'] for r in rows) for rows in old['output_specs']['check'].values())
    base_bytes = inventory.total_bytes(C.read_ref(originals['baseline']))
    candidate_bytes = inventory.total_bytes(C.read_ref(originals['candidate']))
    required=(3*base_bytes+candidate_bytes if phase=='aa' else base_bytes+candidate_bytes)+(68 if phase=='aa' else 32)*output_bytes+protocol['disk']['reserve_bytes']+protocol['disk']['growth_bytes']
    C.save(log/'capacity.json',{'free_bytes':shutil.disk_usage(C.NATIVE).free,'required_bytes':required,
                              'one_phase_bank_bytes':total,'full_output_set_bytes':output_bytes,
                              'phase':phase,'reserve_bytes':protocol['disk']['reserve_bytes'],'original_disposal_authorized':False})
    assert shutil.disk_usage(C.NATIVE).free>=required
    source_inodes=set().union(*(inventory.inode_set(admission.instruction_bank(old,C.ROOT,arm)) for arm in C.ARMS))
    copied_inodes=set()
    for arm in C.ARMS:
        donor_arm = admission.donor_arm(phase, arm)
        destination=C.NATIVE/'phases'/phase/'banks'/arm
        command=['/usr/bin/cp','-a','--reflink=auto',str(admission.instruction_bank(old,C.ROOT,donor_arm)),str(destination)]
        started=time.monotonic_ns()
        result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,timeout=1800)
        C.save(log/(arm+'.copy.json'),{'argv':command,'returncode':result.returncode,
               'stdout':result.stdout.decode(),'stderr':result.stderr.decode(),'excluded_copy_ns':time.monotonic_ns()-started})
        assert result.returncode==0 and not result.stdout and not result.stderr
        actual=inventory.inventory(destination);assert actual==C.read_ref(originals[donor_arm])
        identities=inventory.inode_set(destination)
        assert not identities&source_inodes and not identities&copied_inodes
        copied_inodes|=identities
        C.save(log/(arm+'.native-bank.json'),actual);manifests[arm]=C.ref(log/(arm+'.native-bank.json'))
        banks[arm]=str(destination)
        contexts[arm]=parked_context(destination)
        old_context=C.read_ref(old['variants'][donor_arm]['context'])
        projected=json.loads(json.dumps(contexts[arm]));projected['rustc_info']['inode']=old_context['rustc_info']['inode']
        assert projected==old_context
    tools={};aliases={};commands={}
    for name in ('python3','cp','sync','ps','git','systemctl','busctl','tmux','cc','c++','ld'):
        original=Path('/usr/bin')/name;path=original
        while path.is_symlink():
            target=os.readlink(path);aliases[str(path)]=target
            path=Path(os.path.normpath(path.parent/target)) if not Path(target).is_absolute() else Path(target)
        row=C.identity(path);tools[str(path)]=row;commands[str(original)]={'path':str(path),'sha256':row['sha256']}
    for name in ('/lib/x86_64-linux-gnu/libc.so.6','/usr/lib/x86_64-linux-gnu/libstdc++.so.6'):
        path=Path(name)
        while path.is_symlink():
            target=os.readlink(path);aliases[str(path)]=target
            path=Path(os.path.normpath(path.parent/target)) if not Path(target).is_absolute() else Path(target)
        tools[str(path)]=C.identity(path)
    driver=[C.ROOT/name for name,row in old['files'].items() if row['sha256']==protocol['pins']['sdk12_driver_sha256']]
    assert len(driver)==1;driver=driver[0];info=driver.stat()
    native_diagnostics={};native_contexts={};native_outputs={};native_commands={};cache_witnesses={}
    for arm in C.ARMS:
        donor_arm = admission.donor_arm(phase, arm)
        directory=C.ROOT/'records'/('check-preflight-'+donor_arm+'-01')
        preflight=C.read_ref(old['variants'][donor_arm]['preflight']['check'])
        command=C.read_ref(request['native_commands'][donor_arm])
        assert request['native_commands'][donor_arm]['path']==str(directory/'native.json')
        native_commands[arm] = request['native_commands'][donor_arm]
        native_outputs[arm] = old['output_specs']['check'][donor_arm]
        witness = registry_cache.observe(Path(banks[arm])/'package-home', donor_arm)
        C.save(log/(arm+'.cache.json'), witness); cache_witnesses[arm] = C.ref(log/(arm+'.cache.json'))
        assert command['returncode']==0 and command['error'] is None and command['environment']==old['cargo_environment']
        assert command['source_sha256']==preflight['rows']['native']['prepared']['after_sha256']
        assert command['argv'][-len(protocol['command']):]==protocol['command']
        native_contexts[arm]=preflight['rows']['native']['normalized_compiler']
        native_diagnostics[arm]={}
        for suffix in ('stdout','stderr'):
            path=directory/('native.'+suffix)
            assert C.sha(path)==command[suffix+'_sha256']
            native_diagnostics[arm][suffix]=C.ref(path)
    assert native_contexts['baseline']==native_contexts['candidate'] and len(native_contexts['baseline'])==1
    source_donors = {arm: admission.donor_arm(phase, arm) for arm in C.ARMS}
    C.save(log/'copy-independence.json', {'state':'native-phase-copies-verified','phase':phase,
        'source_donors':source_donors,'no_cross_bank_aliases':True,'no_donor_aliases':True,
        'bytes_modes_mtimes_hardlinks_exact':True,'start_manifests':manifests})
    packet={'schema':1,'state':'bound-registry-native-inputs','phase':phase,'hostname':request['hostname'],
            'host_index':protocol['hosts'].index(request['hostname']),'instruction_inputs':request['instruction_inputs'],
            'instruction_release':request['instruction_release'],'protocol':request['protocol'],
            'controls':request['controls'],'tools':tools,'tool_aliases':aliases,'tool_commands':commands,
            'runtime_identities':runtime,'banks':banks,'contexts':contexts,'start_manifests':manifests,
            'instruction_bank_manifests':originals,'output_bytes':output_bytes,
            'native_diagnostics':native_diagnostics,'native_contexts':native_contexts,
            'native_command_refs':native_commands,'native_output_specs':native_outputs,
            'source_donors':source_donors,'start_cache_witnesses':cache_witnesses,
            'copy_independence':C.ref(log/'copy-independence.json'),
            'raw_retention_capacity':C.ref(log/'capacity.json'),
            'primary_qualification':request['primary_qualification'],'cold_review':request['cold_review'],
            'correctness_acceptance':request['correctness_acceptance'],
            'margin':None if phase=='aa' else previous['margin'],
            'driver':{'path':str(driver),'sha256':C.sha(driver),'inode_identity':[info.st_dev,info.st_ino,info.st_ctime_ns]}}
    if phase=='ab':
        packet['aa_decision']=request['aa_decision']
        packet['margin_acceptance']=previous['margin_acceptance']
    admission.validate_bound_input(packet, old, protocol, C.read_ref)
    C.save(log/'inputs.json',packet)
    C.INPUT=packet;C.OLD=old;C.PROTOCOL=protocol;C.ENV=old['cargo_environment']
    C.fixed_guard()
    C.sync_owned(C.NATIVE,log/'sync.json')
    C.save(log/'complete.json',{'state':'prepared-without-workload','inputs':C.ref(log/'inputs.json'),
           'all_original_banks_preserved':True,'bank_aliases_isolated':True,'runtime_renames_only':True,
           'samples':0,'commands_run':['cp','sync'],'finished_at':C.utc()})
    print(json.dumps({'state':'prepared-without-workload','inputs_sha256':C.sha(log/'inputs.json')}))


if __name__=='__main__':main()
