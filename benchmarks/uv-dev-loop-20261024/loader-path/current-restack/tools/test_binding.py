import argparse
import copy
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import restack_control_02 as control

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        protocol = {'pairs': 12, 'warmup_pairs': 0, 'randomization_seed': 2026102126,
                    'balanced_order_plan': [list(x) for x in control.paired.make_plan(12, 2026102126)],
                    'acceptance': {'test_only': True}, 'pair_reservation_seconds': 120,
                    'command': ['{cargo}', 'check']}
        configuration = {'command': protocol['command'], 'env': {'LD_LIBRARY_PATH': None},
                         'canonical_executable': str(self.root / 'never-executed-cargo')}
        fixed = self.root / 'fixed'; fixed.write_bytes(b'fixed')
        self.inputs = {'protocol': self.write('protocol.json', protocol), 'original_acceptance': protocol['acceptance'],
                       'configuration': self.write('configuration.json', configuration),
                       'entry_path': str(self.root / 'entry.json'), 'terminal_path': str(self.root / 'terminal.json'),
                       'fixture_name': 'test-only', 'files': [{'path': str(fixed), 'sha256': control.paired.sha256(fixed),
                       'bytes': 5, 'mode': stat.S_IMODE(fixed.stat().st_mode)}]}
        self.input_ref = self.write('inputs.json', self.inputs)
        self.authority = {'status': 'approved', 'inputs_sha256': self.input_ref['sha256'],
                          'output': str(self.root / 'never-created-output'), 'pairs': 12, 'seed': 2026102126,
                          'warmup_pairs': 0, 'test_only': True}
        self.authority_ref = self.write('authority.json', self.authority)
        self.entry = {'inputs': self.input_ref, 'authority': self.authority_ref, 'output': self.authority['output']}

    def write(self, name, data):
        p = self.root / name; p.write_text(json.dumps(data))
        return {'path': str(p), 'sha256': control.paired.sha256(p)}

    def load(self):
        self.write('entry.json', self.entry)
        return control.load_entry(self.root / 'entry.json')

    def test_complete_binding_loads_without_execution(self):
        self.assertEqual(self.load()[1], self.inputs)
        control.verify_files(self.inputs)
        self.assertFalse(Path(self.authority['output']).exists())

    def test_wrong_input_digest_rejected(self):
        self.entry['inputs'] = dict(self.input_ref, sha256='0' * 64)
        with self.assertRaises(AssertionError): self.load()

    def test_pending_authority_rejected(self):
        self.authority['status'] = 'pending'
        self.entry['authority'] = self.write('authority.json', self.authority)
        with self.assertRaises(AssertionError): self.load()

    def test_wrong_seed_rejected(self):
        self.authority['seed'] += 1
        self.entry['authority'] = self.write('authority.json', self.authority)
        with self.assertRaises(AssertionError): self.load()

    def test_changed_immutable_input_rejected(self):
        (self.root / 'fixed').write_bytes(b'changed')
        with self.assertRaises(AssertionError): control.verify_files(self.inputs)

    def test_restoration_failure_rejects_complete_mock_collection(self):
        args = argparse.Namespace(inputs=self.input_ref['path'], inputs_sha256=self.input_ref['sha256'],
                                  authority=self.authority_ref['path'], authority_sha256=self.authority_ref['sha256'])
        manifest = {'variants': {'baseline': str(self.root / 'fixed')},
                    'canonical_executable': str(self.root / 'never-executed-cargo')}
        with patch.object(control.paired, 'run'), patch.object(control.fixture, 'verify'), \
             patch.object(control.fixture, 'load', return_value=(self.root, manifest)), \
             patch.object(control.fixture, 'install_variant'), \
             patch.object(control.fixture, 'make_environment', return_value={}), \
             patch.object(control.fixture, 'prepare', side_effect=ValueError('test-only restoration failure')):
            with self.assertRaises(AssertionError): control.run(args)
        terminal = json.loads((self.root / 'terminal.json').read_bytes())
        self.assertEqual(terminal['state'], 'failed')
        self.assertEqual(terminal['failure']['type'], 'ValueError')
        self.assertFalse(terminal['effects_analyzed'])
        self.assertFalse(Path(self.authority['output']).exists())

if __name__ == '__main__': unittest.main()
