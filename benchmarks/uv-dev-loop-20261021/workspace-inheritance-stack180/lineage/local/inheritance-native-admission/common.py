"""Pure identity and boundary helpers for a native phase with no observations."""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'
HOST = 'charlie-oss-2'
DRIVER = '1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
ORIGINAL_SOURCE = 'f52a57b667b0708413cb353b2af4164f11fec6a9b8e0025bab4ab8330135ff98'
SEAL = 'b6e765057417644e62cf7cadc4994a05172077f8c9a26bfe6343e6ad377e48ff'
DELIVERY = '9cb40f6d074706a713b60c2c1b17e4ac44bf8294f1fc3ba3973f46912a2e15ec'
CLOSED_IR = '1eb96065ef89ab579f0aef22930bc945adcae762f28b39470c5c4b8ca9bea0dc'
IR_STATUS = '733cc2e9c98bf07956726b3f9d46cb781ee71b19de1c3380611d6d46feac46ec'
IR_REVIEW = '0ea0f500d28c30d69fc679be7b191f108964b3464fd6dc2f20a486c8661a1834'
TRANSPORT_REVIEW = 'ddc3571d1c77a8f50533caf9d27fec449148df5e1613f4828110ff531dcf1326'
FAILED_LAUNCH = '4655a40aee0f8fce994c9bb4ca59258ea9259dc6283a76d0dbda33a782e2d0b3'
FAILED_STDERR = 'afc6929be95d04008e2a0751e0f05a627a21370f8c2b15d93a2ccb43035396de'
EMPTY = hashlib.sha256(b'').hexdigest()
VARIANTS = {'baseline': '3164f9287711f122fa9636a7816ed8749598706ac5076d66051a036dcef51037',
            'candidate': '3b1a2e4e3654b7b23816fbb54c51072cb356486c36052a5bcd6c4d3d2e6a07e9'}
BUSY = [{'pid': 1076012, 'name': 'fwupdmgr', 'cpu_percent': 150.0, 'controller': False,
         'argv': ['/usr/bin/fwupdmgr', 'refresh']}]
HISTORY = 'metadata/native-admission-history/attempt-01'
MOVABLE = ('results/native-status.json', 'metadata/native-prerequisite.json')
SELECTED = ('delivery.json', 'ownership.json', 'controller/driver.py', 'controller/occupancy.py',
            'controller/reference-native-controller.py', 'controller/source-freeze.json',
            'controller/measurement-seal.json', 'controller/assets.json', 'controller/protocol.json',
            'benchmark/native-check.json', 'benchmark/native-test.json', 'results/ir-status.json',
            'metadata/setup.json', *MOVABLE)


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def relative(name):
    path = PurePosixPath(name)
    need(name and name != '.' and not path.is_absolute() and '..' not in path.parts
         and '\\' not in name and str(path) == name, 'unsafe relative path')
    return path


def record(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.resolve() == path, 'noncanonical regular file: ' + str(path))
    return {'sha256': sha(path), 'size': path.stat().st_size}


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True);stream.write('\n')


def absent_paths():
    result = []
    for workflow in ('check', 'test'):
        label = 'native-' + workflow
        result.extend(('targets/' + label, 'shared-cache/' + label, 'metadata/' + label + '-preflight',
                       'results/' + label, 'logs/' + label + '-runner.log'))
    result.append(HISTORY)
    return sorted(result)


def prerequisite_paths():
    return {ROOT + '/results/ir-status.json'} | {
        ROOT + '/results/ir-' + workflow + '/' + name for workflow in ('check', 'test')
        for name in ('manifest.json', 'samples.json', 'samples.jsonl', 'samples.csv', 'integrity.json', 'analysis.json', 'gate.json')}


def boundary(status, prerequisite, absence, closed):
    need(status['state'] == 'failed' and status['phase'] == 'native' and status['seal_sha256'] == SEAL
         and status['variants'] == VARIANTS and status['integrity_complete'] == [] and status['completed'] == []
         and 'workflow' not in status and 'seed' not in status and status['error'] == repr(AssertionError(BUSY)),
         'not the exact pre-preflight native guard failure')
    need(status['started_at'] <= status['failed_at'], 'invalid failure chronology')
    need(set(absence) == set(absent_paths()) and all(value == {'lexists': False, 'symlink': None} for value in absence.values()),
         'a native fixture/output or recovery namespace already exists')
    need(prerequisite['state'] == 'passed' and prerequisite['seal_sha256'] == SEAL
         and set(prerequisite['files']) == prerequisite_paths()
         and prerequisite['verified_at'] <= status['started_at'], 'native prerequisite differs')
    for name, digest in prerequisite['files'].items():
        need(closed['files'][name.removeprefix(ROOT + '/')] == digest, 'prerequisite is not the accepted IR evidence')
    need(prerequisite['files'][ROOT + '/results/ir-status.json'] == IR_STATUS, 'IR status differs')


def verify_sources(directory, expected):
    directory = Path(directory)
    need(sha(directory / 'source-freeze.json') == expected, 'capture source freeze differs')
    frozen = read(directory / 'source-freeze.json')
    for name, value in frozen['files'].items():
        need(record(directory / relative(name)) == value, 'frozen capture input differs: ' + name)
    for name, digest in {'original/driver.py': DRIVER, 'original/source-freeze.json': ORIGINAL_SOURCE,
                         'history/launch-native.json': FAILED_LAUNCH, 'history/launch-native.stderr': FAILED_STDERR,
                         'history/launch-native.stdout': EMPTY, 'inputs/closed-ir-transfer-manifest.json': CLOSED_IR,
                         'inputs/ir-independent-review.json': IR_REVIEW, 'inputs/ir-transport-review.json': TRANSPORT_REVIEW}.items():
        need(sha(directory / name) == digest, 'original lineage input differs')
    launch = read(directory / 'history/launch-native.json')
    need(launch['returncode'] == 1 and launch['host'] == HOST and launch['root'] == ROOT
         and launch['sealed_inputs_sha256'] == SEAL and launch['delivery_sha256'] == DELIVERY
         and launch['stdout_sha256'] == EMPTY and launch['stderr_sha256'] == FAILED_STDERR,
         'native failed launch differs')
    return frozen
