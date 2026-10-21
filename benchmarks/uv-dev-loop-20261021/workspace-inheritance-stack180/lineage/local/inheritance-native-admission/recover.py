"""Retain a proved zero-work startup failure; never invoke a benchmark."""
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common

FREEZE = '767c4df6153e38245de96d6330c5679e181d515dd99b692b45289d6a19033cff'
CAPTURE = '9203be17ef06b5836ad916765d69d097df29d9fd83df61f33645a5d6a03c8177'
MEASUREMENT = HERE.parent / 'inheritance-measurement'

REMOTE_BODY = r'''
import datetime,importlib.util,os,socket,sys,time
request=json.load(sys.stdin)
root=Path(ROOT)
need(socket.gethostname()==HOST and os.getuid()==root.stat().st_uid==1000 and root.resolve()==root,'wrong owned host/root')
need(request['operation']=='retain-proved-zero-work-native-admission','wrong operation')
need(hashlib.sha256(request['closed_ir_manifest'].encode()).hexdigest()==CLOSED_IR,'unreviewed IR inventory')
closed=json.loads(request['closed_ir_manifest'])
need(sha(root/'controller/driver.py')==DRIVER and sha(root/'controller/measurement-seal.json')==SEAL,'changed original inputs')
need(sha(root/'controller/source-freeze.json')==ORIGINAL_SOURCE and sha(root/'delivery.json')==DELIVERY,'changed source/delivery')
spec=importlib.util.spec_from_file_location('native_admission_recovery_driver',root/'controller/driver.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
os.environ['GIT_OPTIONAL_LOCKS']='0'
need(not owned_processes(),'owned workload still active')
driver.verify_assets();driver.verify_seal(SEAL)
prior=original_hashes()
absence=observe_absence()
for name,expected in request['selected'].items():need(record(root/relative(name))==expected,'captured input changed: '+name)
need(set(request['selected'])==set(SELECTED),'selected scope differs')
boundary(read(root/MOVABLE[0]),read(root/MOVABLE[1]),absence,closed)
need(record(root/'active/bin/cargo')==request['canonical_cargo'],'canonical binary changed')
history=root/HISTORY
need(history.resolve()==history and not os.path.lexists(history),'history namespace exists or is noncanonical')
expected_uploads={'failed-launch-native.json','failed-launch-native.stdout','failed-launch-native.stderr',
                  'capture-receipt.json','boundary-review.json','source-review.json','recovery-source-review.json'}
need(set(request['uploads'])==expected_uploads,'unexpected retained metadata')
for name,row in request['uploads'].items():
 relative(name);need(hashlib.sha256(row['text'].encode()).hexdigest()==row['sha256'],'upload hash differs')
time.sleep(2)
quiet=driver.reference('native').quiet()
need(not owned_processes() and observe_absence()==absence,'boundary changed before retention')
history.parent.mkdir(exist_ok=True)
history.mkdir(exist_ok=False)
write(history/'started.json',{'operation':request['operation'],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'capture_sha256':request['capture_sha256'],'source_freeze_sha256':request['source_freeze_sha256'],
 'remote_source_sha256':request['remote_source_sha256'],'recovery_source_sha256':request['recovery_source_sha256'],
 'boundary_review_sha256':request['boundary_review_sha256'],'recovery_review_sha256':request['recovery_review_sha256'],
 'quiet':quiet,'original_locations':{name:request['selected'][name] for name in MOVABLE}})
for name,row in request['uploads'].items():
 with (history/name).open('xb') as stream:stream.write(row['text'].encode())
moves=[]
for index,name in enumerate(MOVABLE):
 source=root/name;destination=history/Path(name).name
 need(record(source)==request['selected'][name] and not os.path.lexists(destination),'move precondition changed')
 before=source.stat();os.rename(source,destination);after=destination.stat()
 need(record(destination)==request['selected'][name] and not os.path.lexists(source),'retained metadata differs')
 need((before.st_mode,before.st_mtime_ns,before.st_ino)==(after.st_mode,after.st_mtime_ns,after.st_ino),'rename changed metadata')
 event={'original':name,'retained':str(destination.relative_to(root)),'record':record(destination),
        'mode':after.st_mode,'mtime_ns':after.st_mtime_ns,'moved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 write(history/f'move-{index:02}.json',event);moves.append(event)
need(original_hashes()==prior,'accepted IR bytes changed')
for name,expected in request['selected'].items():
 if name not in MOVABLE:need(record(root/name)==expected,'original supporting metadata changed')
need(all(not os.path.lexists(root/name) for name in absent_paths() if name!=HISTORY),'native workload path appeared')
need(not owned_processes() and record(root/'active/bin/cargo')==request['canonical_cargo'],'owned work or binary changed')
driver.verify_assets();driver.verify_seal(SEAL)
files={str(path.relative_to(history)):record(path) for path in sorted(history.rglob('*')) if path.is_file()}
result={'status':'retained zero-work native admission','finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'history':HISTORY,'capture_sha256':request['capture_sha256'],'recovery_review_sha256':request['recovery_review_sha256'],
        'source_freeze_sha256':request['source_freeze_sha256'],'remote_source_sha256':request['remote_source_sha256'],
        'moves':moves,'retained_files':files,'accepted_ir_files_unchanged':500,'native_workload_paths_absent':10,
        'native_cargo_calls':0,'statistics_computed':False,'effects_inspected':False,'original_controls_unchanged':True}
write(history/'completed.json',result)
result['completed_receipt']=record(history/'completed.json')
print(json.dumps(result,sort_keys=True))
'''


def remote_source():
    tree = ast.parse((HERE / 'capture_remote.py').read_text())
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in ('owned_processes', 'observe_absence', 'original_hashes')]
    assert len(helpers) == 3
    # Identical read-only helpers, with the same globals as the original capture.
    return ((HERE / 'common.py').read_text() + '\nimport os\n'
            + '\n\n'.join(ast.unparse(node) for node in helpers) + '\n' + REMOTE_BODY)


def main():
    common.verify_sources(HERE, FREEZE)
    capture = HERE / 'capture-01'
    common.need(common.sha(capture / 'capture.json') == CAPTURE, 'capture receipt changed')
    for name, expected in common.read(capture / 'capture.json')['files'].items():
        common.need(common.record(capture / common.relative(name)) == expected, 'captured byte changed')
    boundary_review = common.read(HERE / 'boundary-review.json')
    common.need(boundary_review['status'] == 'passed zero-work native admission boundary'
                and boundary_review['capture_sha256'] == CAPTURE and boundary_review['native_measurements'] == 0,
                'actual zero-work boundary not accepted')
    review_path = HERE / 'root-recovery-source-review.json'
    review = common.read(review_path)
    remote = remote_source()
    remote_sha = hashlib.sha256(remote.encode()).hexdigest()
    common.need(review['status'] == 'passed' and review['recovery_source_sha256'] == common.sha(Path(__file__))
                and review['remote_source_sha256'] == remote_sha and review['capture_sha256'] == CAPTURE
                and review['boundary_review_sha256'] == common.sha(HERE / 'boundary-review.json'), 'recovery review differs')
    output = HERE / 'recovery-01'
    local_history = MEASUREMENT / 'native-admission-history/attempt-01'
    common.need(not os.path.lexists(output) and not os.path.lexists(local_history), 'recovery is single-use')
    uploads = {'failed-launch-native.' + suffix: MEASUREMENT / ('launch-native.' + suffix)
               for suffix in ('json', 'stdout', 'stderr')}
    for suffix in ('json', 'stdout', 'stderr'):
        common.need((MEASUREMENT / ('launch-native.' + suffix)).read_bytes()
                    == (HERE / 'history' / ('launch-native.' + suffix)).read_bytes(), 'failed local launch changed')
    uploads.update({'capture-receipt.json': capture / 'capture.json', 'boundary-review.json': HERE / 'boundary-review.json',
                    'source-review.json': HERE / 'root-source-review.json', 'recovery-source-review.json': review_path})
    transfer = common.read(capture / 'transfer-manifest.json')
    observation = common.read(capture / 'observation.json')
    request = {'operation': 'retain-proved-zero-work-native-admission', 'source_freeze_sha256': FREEZE,
               'capture_sha256': CAPTURE, 'boundary_review_sha256': common.sha(HERE / 'boundary-review.json'),
               'recovery_review_sha256': common.sha(review_path), 'recovery_source_sha256': common.sha(Path(__file__)),
               'remote_source_sha256': remote_sha, 'canonical_cargo': observation['canonical_cargo'],
               'closed_ir_manifest': (HERE / 'inputs/closed-ir-transfer-manifest.json').read_text(),
               'selected': {name: transfer['files']['remote/' + name] for name in common.SELECTED},
               'uploads': {name: {'text': path.read_text(), 'sha256': common.sha(path)} for name, path in uploads.items()}}
    output.mkdir();common.write(output / 'request.json', request)
    command = ['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh', common.HOST,
               '--', '/usr/bin/env', '-u', 'PYTHONHOME', '-u', 'PYTHONPATH', '-u', 'PYTHONSTARTUP', '-u', 'PYTHONINSPECT',
               '/usr/bin/python3', '-I', '-B', '-c', remote]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (output / 'request.json').open('rb') as incoming, (output / 'stdout').open('xb') as out, (output / 'stderr').open('xb') as err:
        result = subprocess.run(command, stdin=incoming, stdout=out, stderr=err)
    common.write(output / 'transport.json', {'started_at': started, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'returncode': result.returncode, 'stdout': common.record(output / 'stdout'), 'stderr': common.record(output / 'stderr'),
                 'request_sha256': common.sha(output / 'request.json')})
    common.need(result.returncode == 0, 'remote retention failed or acknowledgment lost; inspect before any further action')
    receipt = common.read(output / 'stdout')
    common.need(receipt['status'] == 'retained zero-work native admission' and receipt['capture_sha256'] == CAPTURE
                and receipt['recovery_review_sha256'] == common.sha(review_path)
                and receipt['remote_source_sha256'] == remote_sha and receipt['accepted_ir_files_unchanged'] == 500
                and receipt['native_workload_paths_absent'] == 10 and receipt['native_cargo_calls'] == 0
                and receipt['original_controls_unchanged'] is True, 'remote retention receipt differs')
    common.need({row['original'] for row in receipt['moves']} == set(common.MOVABLE), 'wrong remote move scope')
    for row in receipt['moves']:
        common.need(row['record'] == request['selected'][row['original']], 'wrong retained metadata bytes')
    for name, row in request['uploads'].items():
        common.need(receipt['retained_files'][name] == {'sha256': row['sha256'], 'size': len(row['text'].encode())},
                    'uploaded failure metadata was not retained exactly')
    common.write(output / 'remote-receipt.json', receipt)
    common.verify_sources(HERE, FREEZE)
    local_history.parent.mkdir(exist_ok=True);local_history.mkdir()
    moved = {}
    for suffix in ('json', 'stdout', 'stderr'):
        source = MEASUREMENT / ('launch-native.' + suffix)
        common.need(source.read_bytes() == (HERE / 'history' / source.name).read_bytes(), 'launch changed before local retention')
        destination = local_history / source.name
        os.rename(source, destination)
        moved[source.name] = common.record(destination)
    common.write(output / 'local-relocation.json', {'status': 'retained', 'remote_receipt_sha256': common.sha(output / 'remote-receipt.json'),
                 'original_directory': str(MEASUREMENT), 'retained_directory': str(local_history), 'files': moved,
                 'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print(json.dumps({'status': 'metadata retained; original native launcher ready for separate review',
                      'remote_receipt_sha256': common.sha(output / 'remote-receipt.json'),
                      'local_relocation_sha256': common.sha(output / 'local-relocation.json'), 'cargo_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
