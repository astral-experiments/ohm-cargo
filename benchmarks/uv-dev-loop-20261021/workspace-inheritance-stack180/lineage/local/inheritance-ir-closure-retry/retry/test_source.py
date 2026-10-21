"""Source and synthetic checks only: no remote actions, workloads or effects."""
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract
import launch
import evidence


def proof():
    return {'state': 'passed', 'scope': 'read-only pre-staging absence proof',
            'host': contract.HOST, 'uid': 1000, 'root': contract.ROOT,
            'measurement_seal_sha256': contract.MEASUREMENT_SEAL,
            'driver_sha256': contract.DRIVER, 'ir_failed_status_sha256': contract.IR_FAILED_STATUS,
            'paths_lexist': {name: False for name in contract.ABSENT}, 'native_status_lexists': False,
            'observed_at': '2099-01-01T00:00:00+00:00'}


class FakePath:
    def __init__(self, value):
        self.value = str(value)

    def __truediv__(self, child):
        return FakePath(self.value.rstrip('/') + '/' + str(child))

    def __eq__(self, other):
        return isinstance(other, FakePath) and self.value == other.value

    def __str__(self):
        return self.value

    def resolve(self):
        return self

    def stat(self):
        return SimpleNamespace(st_uid=0 if self.value == '/' else 1000)

    def open(self, mode):
        assert mode == 'rb'
        stream = io.BytesIO()
        stream.name = self.value
        return stream


class Tests(unittest.TestCase):
    def test_all_original_frozen_sources_are_byte_identical(self):
        self.assertEqual(contract.sha(contract.PACKAGE / 'source-freeze.json'), contract.ORIGINAL_FREEZE)
        frozen = contract.read(contract.PACKAGE / 'source-freeze.json')
        self.assertEqual(len(frozen['files']), 47)
        for name, expected in frozen['files'].items():
            self.assertEqual(contract.sha(contract.PACKAGE / name), expected)
            self.assertEqual(contract.sha(contract.ORIGINAL / name), expected)

    def test_first_failed_closure_launch_is_retained_in_place(self):
        for name, expected in contract.FAILED_LAUNCH.items():
            self.assertEqual(contract.sha(contract.ORIGINAL / name), expected)
            self.assertEqual(contract.sha(HERE / 'history' / name), expected)

    def test_original_pre_staging_guard_is_before_payload_and_directory(self):
        tree = ast.parse((contract.PACKAGE / 'run_finalize.py').read_text())
        remote = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'remote' for target in node.targets))
        lines = remote.splitlines()
        self.assertEqual(lines[14], "driver.reference('ir').quiet()")
        self.assertLess(remote.index("driver.reference('ir').quiet()"), remote.index('sys.stdin.buffer.read()'))
        self.assertLess(remote.index("driver.reference('ir').quiet()"), remote.index('here.mkdir(exist_ok=False)'))

    def test_absence_proof_rejects_each_existing_output(self):
        for name in contract.ABSENT:
            value = proof()
            value['paths_lexist'][name] = True
            with self.assertRaises(ValueError):
                contract.verify_absence_proof(value)

    def test_absence_proof_rejects_missing_or_extra_paths(self):
        for key in ('missing', 'extra'):
            value = proof()
            if key == 'missing':
                value['paths_lexist'].pop(contract.ABSENT[0])
            else:
                value['paths_lexist']['unrelated'] = False
            with self.assertRaises(ValueError):
                contract.verify_absence_proof(value)

    def test_absence_proof_binds_host_status_and_seal(self):
        for key in ('host', 'uid', 'root', 'measurement_seal_sha256', 'driver_sha256', 'ir_failed_status_sha256'):
            value = proof()
            value[key] = 'different'
            with self.assertRaises(ValueError):
                contract.verify_absence_proof(value)

    def execute_probe(self, existing=(), wrong_seal=False):
        mapping = {contract.ROOT + '/controller/driver.py': contract.DRIVER,
                   contract.ROOT + '/controller/measurement-seal.json': contract.MEASUREMENT_SEAL,
                   contract.ROOT + '/results/ir-status.json': contract.IR_FAILED_STATUS}
        if wrong_seal:
            mapping[contract.ROOT + '/controller/measurement-seal.json'] = 'different'
        def digest(stream, algorithm):
            self.assertEqual(algorithm, 'sha256')
            return SimpleNamespace(hexdigest=lambda: mapping[stream.name])
        output = io.StringIO()
        with mock.patch('pathlib.Path', FakePath), mock.patch('socket.gethostname', return_value=contract.HOST), \
             mock.patch('os.getuid', return_value=1000), mock.patch('hashlib.file_digest', side_effect=digest), \
             mock.patch('os.path.lexists', side_effect=lambda path: str(path) in existing), \
             contextlib.redirect_stdout(output):
            exec(compile(launch.ABSENCE_PROBE, '<synthetic-read-only-probe>', 'exec'), {})
        return json.loads(output.getvalue())

    def test_remote_probe_success_uses_exact_absence_contract(self):
        contract.verify_absence_proof(self.execute_probe())

    def test_remote_probe_rejects_directory_or_dangling_symlink_lexistence(self):
        for name in contract.ABSENT:
            with self.assertRaises(AssertionError):
                self.execute_probe({contract.ROOT + '/' + name})

    def test_remote_probe_rejects_native_status(self):
        with self.assertRaises(AssertionError):
            self.execute_probe({contract.ROOT + '/results/native-status.json'})

    def test_remote_probe_rejects_changed_seal(self):
        with self.assertRaises(AssertionError):
            self.execute_probe(wrong_seal=True)

    def test_remote_probe_has_no_mutating_or_process_calls(self):
        forbidden = {'mkdir', 'makedirs', 'remove', 'unlink', 'rename', 'replace', 'write_text', 'write_bytes',
                     'run', 'Popen', 'system', 'execve', 'spawn', 'sleep'}
        calls = [node for node in ast.walk(ast.parse(launch.ABSENCE_PROBE)) if isinstance(node, ast.Call)]
        self.assertFalse({node.func.attr for node in calls if isinstance(node.func, ast.Attribute)} & forbidden)
        for node in calls:
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'open':
                self.assertEqual(ast.literal_eval(node.args[0]), 'rb')

    def test_failed_absence_probe_never_invokes_original_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            retry = package / 'retry'
            retry.mkdir()
            with mock.patch.object(contract, 'PACKAGE', package), mock.patch.object(contract, 'HERE', retry), \
                 mock.patch.object(launch, 'HERE', retry), mock.patch.object(contract, 'verify_controls'), \
                 mock.patch.object(contract, 'load_original_binding') as binding, \
                 mock.patch.object(launch.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run, \
                 mock.patch.object(sys, 'argv', ['launch.py', '--retry-source-freeze-sha256', 'synthetic']):
                with self.assertRaisesRegex(ValueError, 'absence proof failed'):
                    launch.main()
                self.assertEqual(run.call_count, 1)
                result = contract.read(retry / 'attempt.json')
                self.assertEqual(result['state'], 'failed')
                self.assertEqual(result['absence_probe_returncode'], 1)
                self.assertEqual(set(result['retained_files']), {'retry/attempt-started.json', 'retry/absence.stdout', 'retry/absence.stderr'})
                self.assertFalse((package / 'launch-finalize.json').exists())

    def test_existing_attempt_prevents_any_remote_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            retry = package / 'retry'
            retry.mkdir()
            (retry / 'attempt.json').write_text('{"original":true}\n')
            with mock.patch.object(contract, 'PACKAGE', package), mock.patch.object(contract, 'HERE', retry), \
                 mock.patch.object(launch, 'HERE', retry), mock.patch.object(contract, 'verify_controls'), \
                 mock.patch.object(contract, 'load_original_binding'), mock.patch.object(launch.subprocess, 'run') as run, \
                 mock.patch.object(sys, 'argv', ['launch.py', '--retry-source-freeze-sha256', 'synthetic']):
                with self.assertRaisesRegex(ValueError, 'single-use'):
                    launch.main()
                run.assert_not_called()
                self.assertEqual((retry / 'attempt.json').read_text(), '{"original":true}\n')

    @contextlib.contextmanager
    def synthetic_collection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, controls = root / 'package', root / 'controls'
            retry = package / 'retry'
            retry.mkdir(parents=True)
            destination = controls / 'collections/ir-closed-postguard'
            destination.mkdir(parents=True)
            for name, content in {'receipt.json': '{"status":"passed"}\n',
                                  'transfer-manifest.json': '{}\n', 'transport.json': '{}\n',
                                  'payload.tar': 'synthetic opaque original transport\n'}.items():
                (destination / name).write_text(content)
            for name in ('launch-finalize.json', 'retry/attempt.json', 'retry/absence.stdout',
                         'retry/collect-ir.stdout', 'retry/collect-ir.stderr'):
                (package / name).write_text('{}\n')
            (package / 'synthetic.txt').write_text('retained source\n')
            (retry / 'collect-ir.json').write_text(json.dumps({
                'returncode': 0, 'phase': 'ir', 'retry_source_freeze_sha256': 'synthetic',
                'original_collection_receipt_sha256': contract.sha(destination / 'receipt.json'),
                'stdout_sha256': contract.sha(retry / 'collect-ir.stdout'),
                'stderr_sha256': contract.sha(retry / 'collect-ir.stderr')}))
            selected = ['synthetic.txt', 'retry/collect-ir.json', 'retry/collect-ir.stdout', 'retry/collect-ir.stderr']
            with mock.patch.object(contract, 'PACKAGE', package), mock.patch.object(contract, 'HERE', retry), \
                 mock.patch.object(contract, 'CONTROLS', controls), mock.patch.object(contract, 'verify_attempt'), \
                 mock.patch.object(contract, 'verify_controls'), mock.patch.object(evidence, 'selected', return_value=selected):
                yield destination

    def test_supplement_archive_preserves_original_transport_and_receipts(self):
        with self.synthetic_collection() as destination:
            before = {name: (destination / name).read_bytes() for name in
                      ('receipt.json', 'transfer-manifest.json', 'transport.json', 'payload.tar')}
            report = evidence.attach('ir', 'synthetic')
            self.assertEqual(report['state'], 'passed')
            self.assertFalse(report['sampling_or_analysis'])
            self.assertEqual(before, {name: (destination / name).read_bytes() for name in before})

    def test_supplement_archive_rejects_symlink_even_with_updated_archive_digest(self):
        with self.synthetic_collection() as destination:
            evidence.attach('ir', 'synthetic')
            with tarfile.open(destination / 'operational-retry.tar', 'a:') as archive:
                member = tarfile.TarInfo('files/evil')
                member.type = tarfile.SYMTYPE
                member.linkname = '../outside'
                archive.addfile(member)
            descriptor = contract.read(destination / 'operational-retry-archive.json')
            descriptor['archive'] = contract.record(destination / 'operational-retry.tar')
            (destination / 'operational-retry-archive.json').write_text(json.dumps(descriptor))
            with self.assertRaisesRegex(ValueError, 'unsafe/extra'):
                evidence.verify('ir', 'synthetic')

    def test_supplement_archive_rejects_changed_copied_file(self):
        with self.synthetic_collection() as destination:
            evidence.attach('ir', 'synthetic')
            (destination / 'local-operational-retry/synthetic.txt').write_text('changed\n')
            with self.assertRaisesRegex(ValueError, 'bytes differ'):
                evidence.verify('ir', 'synthetic')


if __name__ == '__main__':
    unittest.main(verbosity=2)
