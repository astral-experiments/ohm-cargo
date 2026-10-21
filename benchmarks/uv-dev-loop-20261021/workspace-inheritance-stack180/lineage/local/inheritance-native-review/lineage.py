"""Verify the retained zero-work native admission before any native effects."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ADMISSION = WORK / 'inheritance-native-admission'
CONTROLS = WORK / 'inheritance-measurement'
TRANSPORT = WORK / 'inheritance-ir-closure-retry/transport'
sys.path.insert(0, str(ADMISSION))
import common

CAPTURE_SOURCE = '767c4df6153e38245de96d6330c5679e181d515dd99b692b45289d6a19033cff'
CAPTURE = '9203be17ef06b5836ad916765d69d097df29d9fd83df61f33645a5d6a03c8177'
BOUNDARY = '098062f02d103e6889b3959772a60a3d025204e391d491611a282ee8371519ff'
RECOVERY = 'edc17ec3bbf0140fafb1ab86a68674e71f642839ef67740c16826fd59b4e22f1'
RECOVERY_REVIEW = 'dda8f307b2070398fda00c72bff40e3113eaf53627d69ee3db88c687727d0fb6'
REMOTE_RECEIPT = 'bb7ff585d53bbf9691997ac8ace84b6c7780dbe4c2839346e12757a019558f27'
LOCAL_RECEIPT = '0479bbf04cec39426b1834de69dc1c648382d9cb80be00b7645ccf830a36b585'
STAGE = '67982c7f92b012dfcfa83f4ccb3dfbfb7e15be18aa5932e7cd4f7c3141946655'
TRANSPORT_SOURCE = '92db62095f5b381fff4062f9fb7a48d12039085d58e74f401417fc8770f037f6'


def verify_source(expected):
    common.need(common.sha(HERE / 'source-freeze.json') == expected, 'native lineage review freeze differs')
    frozen = common.read(HERE / 'source-freeze.json')
    for name, digest in frozen['files'].items():
        common.need(common.sha(HERE / common.relative(name)) == digest, 'native reviewer source changed')
    for name, digest in frozen['local_inputs'].items():
        common.need(common.sha(WORK / common.relative(name)) == digest, 'native lineage input changed: ' + name)
    common.verify_sources(ADMISSION, CAPTURE_SOURCE)
    common.need(common.sha(TRANSPORT / 'source-freeze.json') == TRANSPORT_SOURCE, 'original statistical review source freeze differs')
    transport_freeze = common.read(TRANSPORT / 'source-freeze.json')
    for name, digest in transport_freeze['files'].items():
        common.need(common.sha(TRANSPORT.parent / common.relative(name)) == digest, 'original review/transport input changed')
    return frozen


def verify_moves(moves, selected):
    common.need([row['original'] for row in moves] == list(common.MOVABLE), 'metadata move order/scope differs')
    for row in moves:
        common.need(row['retained'] == common.HISTORY + '/' + Path(row['original']).name
                    and row['record'] == selected[row['original']], 'moved metadata differs')


def verify(expected_freeze, expected_native_manifest):
    verify_source(expected_freeze)
    capture = ADMISSION / 'capture-01'
    common.need(common.sha(capture / 'capture.json') == CAPTURE, 'admission capture differs')
    for name, value in common.read(capture / 'capture.json')['files'].items():
        common.need(common.record(capture / common.relative(name)) == value, 'admission captured bytes changed')
    common.need(common.sha(ADMISSION / 'boundary-review.json') == BOUNDARY
                and common.sha(ADMISSION / 'recover.py') == RECOVERY
                and common.sha(ADMISSION / 'root-recovery-source-review.json') == RECOVERY_REVIEW,
                'boundary/recovery review differs')
    boundary = common.read(ADMISSION / 'boundary-review.json')
    common.need(boundary['status'] == 'passed zero-work native admission boundary'
                and boundary['capture_sha256'] == CAPTURE and boundary['native_measurements'] == boundary['native_cargo_calls'] == 0,
                'zero-work boundary not accepted')
    observation = common.read(capture / 'observation.json')
    closed = common.read(ADMISSION / 'inputs/closed-ir-transfer-manifest.json')
    common.boundary(common.read(capture / 'remote' / common.MOVABLE[0]),
                    common.read(capture / 'remote' / common.MOVABLE[1]), observation['absence'], closed)
    recovery_dir = ADMISSION / 'recovery-01'
    common.need(common.sha(recovery_dir / 'remote-receipt.json') == REMOTE_RECEIPT
                and common.sha(recovery_dir / 'local-relocation.json') == LOCAL_RECEIPT, 'retention receipts differ')
    request, transport = common.read(recovery_dir / 'request.json'), common.read(recovery_dir / 'transport.json')
    receipt, local = common.read(recovery_dir / 'remote-receipt.json'), common.read(recovery_dir / 'local-relocation.json')
    review = common.read(ADMISSION / 'root-recovery-source-review.json')
    common.need(transport['returncode'] == 0 and transport['request_sha256'] == common.sha(recovery_dir / 'request.json')
                and transport['stdout'] == common.record(recovery_dir / 'stdout')
                and transport['stderr'] == common.record(recovery_dir / 'stderr')
                and common.read(recovery_dir / 'stdout') == receipt, 'recovery transport/receipt differs')
    common.need(request['capture_sha256'] == receipt['capture_sha256'] == CAPTURE
                and request['source_freeze_sha256'] == receipt['source_freeze_sha256'] == CAPTURE_SOURCE
                and request['recovery_review_sha256'] == receipt['recovery_review_sha256'] == RECOVERY_REVIEW
                and request['recovery_source_sha256'] == review['recovery_source_sha256'] == RECOVERY,
                'recovery control joins differ')
    spec = importlib.util.spec_from_file_location('audited_zero_work_recovery_source', ADMISSION / 'recover.py')
    recovery = importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
    remote_source = recovery.remote_source()  # Pure extraction of the authenticated source; no main/host call.
    common.need(hashlib.sha256(remote_source.encode()).hexdigest() == request['remote_source_sha256']
                == review['remote_source_sha256'] == receipt['remote_source_sha256'], 'executed recovery source differs')
    selected = {name: common.read(capture / 'transfer-manifest.json')['files']['remote/' + name] for name in common.SELECTED}
    common.need(request['selected'] == selected and request['canonical_cargo'] == observation['canonical_cargo'], 'recovery admitted different captured inputs')
    verify_moves(receipt['moves'], selected)
    common.need(receipt['status'] == 'retained zero-work native admission' and receipt['accepted_ir_files_unchanged'] == 500
                and receipt['native_workload_paths_absent'] == 10 and receipt['native_cargo_calls'] == 0
                and receipt['original_controls_unchanged'] and not receipt['statistics_computed'] and not receipt['effects_inspected'],
                'recovery did not preserve the zero-work boundary')
    collection = CONTROLS / 'collections/native'
    common.need(common.sha(collection / 'transfer-manifest.json') == expected_native_manifest, 'terminal native collection differs')
    manifest = common.read(collection / 'transfer-manifest.json')
    common.need(manifest['phase'] == 'native' and manifest['root'] == common.ROOT
                and manifest['seal_sha256'] == common.SEAL and manifest['driver_sha256'] == common.DRIVER, 'native collection identity differs')
    files, remote = manifest['files'], collection / 'remote'
    # Opaque hashing only. Both workflow raw integrity/statistical audits run later in the unchanged reviewer.
    for name, digest in files.items():
        common.need(common.record(remote / common.relative(name))['sha256'] == digest, 'native capture byte changed')
    common.need(all(files.get(name) == digest for name, digest in closed['files'].items()), 'accepted IR data changed before native')
    for name, value in receipt['retained_files'].items():
        path = remote / common.HISTORY / common.relative(name)
        common.need(common.record(path) == value and files[common.HISTORY + '/' + name] == value['sha256'], 'remote retained failure/history differs')
    completed = remote / common.HISTORY / 'completed.json'
    common.need(common.record(completed) == receipt['completed_receipt']
                and common.read(completed) == {key: value for key, value in receipt.items() if key != 'completed_receipt'},
                'remote final retention receipt differs')
    expected_history = set(receipt['retained_files']) | {'completed.json'}
    common.need({name.removeprefix(common.HISTORY + '/') for name in files if name.startswith(common.HISTORY + '/')}
                == expected_history, 'extra/missing remote admission history')
    for name, row in request['uploads'].items():
        path = remote / common.HISTORY / common.relative(name)
        common.need(path.read_bytes() == row['text'].encode() and common.sha(path) == row['sha256'], 'uploaded review/failed launch bytes differ')
    local_history = CONTROLS / 'native-admission-history/attempt-01'
    common.need(local['status'] == 'retained' and local['remote_receipt_sha256'] == REMOTE_RECEIPT
                and local['original_directory'] == str(CONTROLS) and local['retained_directory'] == str(local_history)
                and set(local['files']) == {'launch-native.' + suffix for suffix in ('json', 'stdout', 'stderr')}, 'local relocation scope differs')
    for name, value in local['files'].items():
        common.need(common.record(local_history / name) == value and common.record(ADMISSION / 'history' / name) == value,
                    'original local launch was not retained exactly')
    replay_path = CONTROLS / 'root-native-replay-launch-review.json'
    replay = common.read(replay_path)
    common.need(replay['status'] == 'passed' and replay['capture_sha256'] == CAPTURE
                and replay['boundary_review_sha256'] == BOUNDARY and replay['recovery_source_review_sha256'] == RECOVERY_REVIEW
                and replay['remote_retention_receipt_sha256'] == REMOTE_RECEIPT
                and replay['local_relocation_receipt_sha256'] == LOCAL_RECEIPT
                and replay['native_observations_before_replay'] == 0, 'replay admission not accepted')
    common.need(common.sha(CONTROLS / 'driver.py') == replay['driver_sha256'] == common.DRIVER
                and common.sha(CONTROLS / 'stage.py') == replay['stage_sha256'] == STAGE
                and common.sha(CONTROLS / 'source-freeze.json') == common.ORIGINAL_SOURCE
                and replay['seal_sha256'] == common.SEAL, 'original phase controls changed')
    launch = common.read(CONTROLS / 'launch-native.json')
    common.need(launch['returncode'] == 0 and launch['operation'] == 'launch-native'
                and launch['host'] == common.HOST and launch['root'] == common.ROOT
                and launch['sealed_inputs_sha256'] == common.SEAL
                and local['completed_at'] <= replay['reviewed_at'] <= launch['started_at'], 'replay launch/chronology differs')
    for suffix in ('stdout', 'stderr'):
        common.need(common.sha(CONTROLS / ('launch-native.' + suffix)) == launch[suffix + '_sha256'], 'final launch stream differs')
    status = common.read(remote / 'results/native-status.json')
    common.need(status['state'] == 'complete' and status['phase'] == 'native'
                and launch['started_at'] <= status['started_at'] <= status['completed_at'] <= launch['finished_at'],
                'native phase not terminal after the admitted replay')
    verify_source(expected_freeze)
    return {'status': 'passed', 'zero_native_observations_replaced': True, 'original_phase_controls_unchanged': True,
            'effects_inspected': False, 'statistics_computed': False, 'source_freeze_sha256': expected_freeze,
            'capture_sha256': CAPTURE, 'boundary_review_sha256': BOUNDARY, 'recovery_source_review_sha256': RECOVERY_REVIEW,
            'remote_retention_receipt_sha256': REMOTE_RECEIPT, 'local_relocation_sha256': LOCAL_RECEIPT,
            'root_replay_review_sha256': common.sha(replay_path), 'final_native_launch_sha256': common.sha(CONTROLS / 'launch-native.json'),
            'native_transfer_manifest_sha256': expected_native_manifest, 'ir_files_preserved': 500,
            'retained_remote_files': len(expected_history), 'retained_local_launch_files': 3,
            'scope': 'Exact zero-work admission/recovery joins verified before the unchanged two-workflow raw/statistical reviewer.'}
