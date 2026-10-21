"""Appended to the frozen common.py; read-only capture, never installed remotely."""
import datetime
import importlib.util
import io
import os
import socket
import sys
import tarfile

request = json.load(sys.stdin)
root = Path(ROOT)
need(socket.gethostname() == HOST and os.getuid() == root.stat().st_uid == 1000
     and root.resolve() == root and Path('/').stat().st_uid == 0, 'wrong owned host/root namespace')
need(request['operation'] == 'capture-native-zero-work-failure' and request['source_freeze_sha256'], 'wrong capture operation')
closed_bytes = request['closed_ir_manifest'].encode()
need(hashlib.sha256(closed_bytes).hexdigest() == CLOSED_IR, 'unreviewed prior IR inventory')
closed = json.loads(closed_bytes)
need(closed['seal_sha256'] == SEAL and closed['driver_sha256'] == DRIVER and len(closed['files']) == 500,
     'prior IR collection identity differs')
need(sha(root / 'delivery.json') == DELIVERY and sha(root / 'controller/driver.py') == DRIVER
     and sha(root / 'controller/source-freeze.json') == ORIGINAL_SOURCE
     and sha(root / 'controller/measurement-seal.json') == SEAL, 'original inputs differ')
need(read(root / 'ownership.json')['delivery_sha256'] == DELIVERY, 'ownership binding differs')
os.environ['GIT_OPTIONAL_LOCKS'] = '0'
spec = importlib.util.spec_from_file_location('native_admission_readonly_driver', root / 'controller/driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def owned_processes():
    result = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            state = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()[0]
            argv = [os.fsdecode(part) for part in (entry / 'cmdline').read_bytes().split(b'\0') if part]
        except (OSError, PermissionError):
            continue
        if state != 'Z' and any(value.startswith(ROOT + '/') for value in argv):
            result.append({'pid': int(entry.name), 'state': state, 'argv': argv})
    return result


def observe_absence():
    return {name: {'lexists': os.path.lexists(root / relative(name)),
                   'symlink': os.readlink(root / name) if (root / name).is_symlink() else None}
            for name in absent_paths()}


def original_hashes():
    result = {name: record(root / relative(name))['sha256'] for name in closed['files']}
    need(result == closed['files'], 'accepted IR/source bytes changed')
    return result


need(not owned_processes(), 'owned measurement/controller still runs')
driver.verify_assets()
driver.verify_seal(SEAL)
old_hashes = original_hashes()
absence = observe_absence()
payloads = {name: record(root / relative(name)) for name in SELECTED}
status = read(root / MOVABLE[0])
prerequisite = read(root / MOVABLE[1])
need(status['state'] in ('failed', 'complete'), 'native phase is not terminal')
canonical = record(root / 'active/bin/cargo')
try:
    boundary(status, prerequisite, absence, closed)
    boundary_state = {'status': 'passed exact zero-work boundary'}
except (ValueError, KeyError, TypeError) as error:
    boundary_state = {'status': 'unproven', 'error': repr(error)}
observation = {
    'operation': request['operation'], 'host': socket.gethostname(), 'root': ROOT, 'uid': os.getuid(),
    'uid_map': Path('/proc/self/uid_map').read_text(), 'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_freeze_sha256': request['source_freeze_sha256'], 'remote_source_sha256': request['remote_source_sha256'],
    'seal_sha256': SEAL, 'original_source_freeze_sha256': ORIGINAL_SOURCE, 'driver_sha256': DRIVER,
    'previous_closed_ir_manifest_sha256': CLOSED_IR, 'prior_500_file_hashes': old_hashes,
    'absence': absence, 'remaining_owned_processes': [], 'canonical_cargo': canonical,
    'native_status_sha256': payloads[MOVABLE[0]]['sha256'], 'native_prerequisite_sha256': payloads[MOVABLE[1]]['sha256'],
    'sealed_input_files_verified': len(read(root / 'controller/measurement-seal.json')['file_sha256']),
    'boundary': boundary_state, 'native_effects_inspected': False, 'qualification': 'not evaluated',
    'scope': 'Read-only capture. Only frozen asset/seal verification, opaque hashes and terminal metadata. No quiet-guard change or invocation, Cargo, sampling or statistical calculation.'}
observation_bytes = (json.dumps(observation, indent=2, sort_keys=True) + '\n').encode()
files = {'remote/' + name: value for name, value in payloads.items()}
files['observation.json'] = {'sha256': hashlib.sha256(observation_bytes).hexdigest(), 'size': len(observation_bytes)}
manifest = {'operation': request['operation'], 'host': HOST, 'root': ROOT, 'source_freeze_sha256': request['source_freeze_sha256'],
            'seal_sha256': SEAL, 'files': files, 'qualification': 'not evaluated'}


def add_bytes(archive, name, data):
    item = tarfile.TarInfo(name);item.size = len(data);item.mode = 0o600;item.mtime = 0
    archive.addfile(item, io.BytesIO(data))


with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
    for name in SELECTED:
        item = tarfile.TarInfo('remote/' + name)
        item.size, item.mode, item.mtime = payloads[name]['size'], 0o600, 0
        with (root / name).open('rb') as stream:
            archive.addfile(item, stream)
    add_bytes(archive, 'observation.json', observation_bytes)
    need(not owned_processes(), 'owned work resumed during capture')
    need(original_hashes() == old_hashes and observe_absence() == absence, 'original input or native boundary changed during capture')
    need({name: record(root / name) for name in SELECTED} == payloads
         and record(root / 'active/bin/cargo') == canonical, 'captured metadata/canonical binary changed')
    driver.verify_assets()
    driver.verify_seal(SEAL)
    add_bytes(archive, 'transfer-manifest.json', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
