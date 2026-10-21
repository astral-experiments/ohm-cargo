#!/usr/bin/env python3
"""Pure closure guard tests: no host access, Cargo, profiling, or real statistics."""
import ast
import copy
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import closure_contract as contract


class ClosureTests(unittest.TestCase):
    def test_exact_original_tail(self):
        tail = contract.original_tail((HERE / 'original/driver.py').read_text())
        self.assertEqual(ast.dump(tail, include_attributes=False), ast.dump(ast.parse(
            (HERE / 'original/analysis-tail.py').read_text()), include_attributes=False))

    def test_changed_quiet_guard_rejected(self):
        source = (HERE / 'original/driver.py').read_text().replace(
            "state='both workflows passed integrity', quiet=ref.quiet()",
            "state='both workflows passed integrity', quiet={}")
        with self.assertRaises(AssertionError):
            contract.original_tail(source)

    def test_changed_statistics_rejected(self):
        source = (HERE / 'original/driver.py').read_text().replace("'--resamples', '20000'", "'--resamples', '2'")
        with self.assertRaises(AssertionError):
            contract.original_tail(source)

    def test_sample_loop_cannot_join_tail(self):
        source = (HERE / 'original/driver.py').read_text().replace(
            "        assert status['integrity_complete'] == ['check', 'test']",
            "        subprocess.run(['cargo', 'check'])\n        assert status['integrity_complete'] == ['check', 'test']")
        with self.assertRaises(AssertionError):
            contract.original_tail(source)

    def kwargs(self, workflow):
        return {'stdout': types.SimpleNamespace(name=str(contract.ROOT / ('results/ir-' + workflow + '/analysis-stdout.json'))), 'check': True}

    def test_original_analysis_command_allowed(self):
        for workflow in ('check', 'test'):
            contract.validate_analyze_call(contract.analyze_command('/usr/bin/python3', workflow), self.kwargs(workflow), '/usr/bin/python3', workflow)

    def test_workload_command_rejected(self):
        with self.assertRaises(AssertionError):
            contract.validate_analyze_call(['cargo', 'check'], self.kwargs('check'), '/usr/bin/python3', 'check')

    def test_resampling_or_pair_setting_change_rejected(self):
        for needle, replacement in [('20000', '2'), ('1701', '33'), ('12', '24'), ('.99', '.95')]:
            command = contract.analyze_command('/usr/bin/python3', 'check')
            command[command.index(needle)] = replacement
            with self.assertRaises(AssertionError):
                contract.validate_analyze_call(command, self.kwargs('check'), '/usr/bin/python3', 'check')

    def test_switched_analysis_output_rejected(self):
        with self.assertRaises(AssertionError):
            contract.validate_analyze_call(contract.analyze_command('/usr/bin/python3', 'check'), self.kwargs('test'), '/usr/bin/python3', 'check')

    def test_extra_process_options_rejected(self):
        kwargs = self.kwargs('check');kwargs['shell'] = True
        with self.assertRaises(AssertionError):
            contract.validate_analyze_call(contract.analyze_command('/usr/bin/python3', 'check'), kwargs, '/usr/bin/python3', 'check')

    def test_unsafe_relative_paths_rejected(self):
        for name in ['', '.', '..', '../raw', '/tmp/raw', 'a/../b', 'a//b', './a', 'a\\b']:
            with self.subTest(name=name), self.assertRaises(AssertionError):
                contract.relative(name)

    def test_original_bytes_and_sole_status_exception(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='pure-test-') as tmp:
            root = Path(tmp);(root / 'results').mkdir();(root / 'raw').write_bytes(b'observation')
            (root / contract.STATUS_PATH).write_bytes(b'failed')
            capture = {'files': {name: contract.sha(root / name) for name in ('raw', contract.STATUS_PATH)}}
            self.assertEqual(contract.original_hashes(root, capture), capture['files'])
            (root / contract.STATUS_PATH).write_bytes(b'complete')
            with self.assertRaises(AssertionError):contract.original_hashes(root, capture)
            self.assertEqual(contract.original_hashes(root, capture, True)['raw'], capture['files']['raw'])
            (root / 'raw').write_bytes(b'changed')
            with self.assertRaises(AssertionError):contract.original_hashes(root, capture, True)

    def test_symlinked_original_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='pure-test-') as tmp:
            root = Path(tmp);(root / 'raw').write_bytes(b'original');(root / 'alias').symlink_to('raw')
            with self.assertRaises(AssertionError):contract.regular(root, 'alias')

    def exercise_tail(self, fail_quiet=None):
        events = [];status = {'integrity_complete': ['check', 'test'], 'completed': []}
        quiet_calls = 0
        class Output:
            def __init__(self, workflow):self.workflow = workflow
            def __str__(self):return str(contract.ROOT / ('results/ir-' + self.workflow))
            def __truediv__(self, name):
                assert name == 'analysis-stdout.json'
                return self
            def open(self, mode):
                assert mode == 'x'
                result = io.StringIO();result.name = str(contract.ROOT / ('results/ir-' + self.workflow + '/analysis-stdout.json'))
                return result
        def quiet():
            nonlocal quiet_calls
            quiet_calls += 1;events.append('quiet')
            if quiet_calls == fail_quiet:raise AssertionError('synthetic occupancy')
            return {'other_workloads': []}
        def run(command, **kwargs):
            workflow = 'check' if command[5].endswith('ir-check') else 'test'
            contract.validate_analyze_call(command, kwargs, '/usr/bin/python3', workflow)
            events.append('analyze-' + workflow)
        def gate(phase, output):
            events.append('gate-' + output.workflow)
            return {'passes_gate': False, 'significant_native_regression': False}
        namespace = {'status': status, 'ref': types.SimpleNamespace(quiet=quiet, uv_identity=lambda: 'unchanged'),
            'core': types.SimpleNamespace(atomic_json=lambda *args: events.append('status-write'), utc_now=lambda: 'synthetic'),
            'phase_status': lambda phase: 'ordinary-status', 'phase': 'ir', 'STAGES': {'ir': {'plan': [('check', 1), ('test', 2)], 'pairs': 12}},
            'paths': lambda phase, workflow: {'output': Output(workflow)}, 'sys': types.SimpleNamespace(executable='/usr/bin/python3'),
            'runner': contract.ROOT / 'benchmark/frozen/paired.py', 'subprocess': types.SimpleNamespace(run=run),
            'gate': gate, 'verify_seal': lambda value: events.append('verify-seal'), 'expected_seal': contract.SEAL}
        error = None
        try:exec(compile(contract.original_tail((HERE / 'original/driver.py').read_text()), '<pure-tail>', 'exec'), namespace)
        except AssertionError as failure:error = failure
        return events, status, error

    def test_exact_tail_only_two_fixed_analyses(self):
        events, status, error = self.exercise_tail()
        self.assertIsNone(error);self.assertEqual(status['state'], 'complete')
        self.assertEqual([x for x in events if x.startswith('analyze')], ['analyze-check', 'analyze-test'])
        self.assertEqual(events.count('quiet'), 2);self.assertEqual(events.count('verify-seal'), 1)
        self.assertLess(events.index('verify-seal'), len(events) - 2)

    def test_first_original_quiet_failure_blocks_all_effects(self):
        events, status, error = self.exercise_tail(1)
        self.assertIsNotNone(error);self.assertFalse(any(x.startswith('analyze') for x in events))
        self.assertNotEqual(status.get('state'), 'complete')

    def test_post_analysis_quiet_failure_blocks_completion(self):
        events, status, error = self.exercise_tail(2)
        self.assertIsNotNone(error);self.assertEqual(len([x for x in events if x.startswith('analyze')]), 2)
        self.assertNotEqual(status.get('state'), 'complete')

    def test_independent_raw_and_statistics_logic_unchanged(self):
        old, new = HERE / 'original/reviewer', HERE / 'reviewer'
        self.assertEqual((old / 'statistics_review.py').read_bytes(), (new / 'statistics_review.py').read_bytes())
        self.assertEqual((old / 'review_setup.py').read_bytes(), (new / 'review_setup.py').read_bytes())
        def functions(path):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name != 'main'}
        self.assertEqual(functions(old / 'review.py'), functions(new / 'review.py'))
        def methods(path):
            cls = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef) and node.name == 'Evidence')
            return {node.name: ast.dump(node, include_attributes=False) for node in cls.body
                    if isinstance(node, ast.FunctionDef) and node.name != '__init__'}
        self.assertEqual(methods(old / 'evidence.py'), methods(new / 'evidence.py'))


if __name__ == '__main__':unittest.main(verbosity=2)
