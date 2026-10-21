"""Pure source/metadata/synthetic joins; no host access or effect evaluation."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import transport_contract as transport


def functions(path):
    return {node.name: node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)}


def remote_code(path):
    return next(node.value.value for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, ast.Assign) and any(isinstance(item, ast.Name) and item.id == 'remote' for item in node.targets))


class Tests(unittest.TestCase):
    def test_original_47_sources_still_match_original_freeze(self):
        package = transport.PACKAGE
        frozen = transport.read(package / 'source-freeze.json')
        self.assertEqual(len(frozen['files']), 47)
        self.assertEqual(transport.sha(package / 'source-freeze.json'),
                         'befbcd80ecdbfa09a14a39faf11891a01b65cb544522417fbbc29b3aa4352d10')
        for name, digest in frozen['files'].items():
            self.assertEqual(transport.sha(package / name), digest)

    def test_remote_collector_is_byte_identical(self):
        self.assertEqual(remote_code(HERE / 'collect.py'), remote_code(transport.PACKAGE / 'collect_final.py'))

    def test_failure_archive_and_utc_helpers_are_ast_identical(self):
        old = functions(transport.PACKAGE / 'reviewer/closure_binding.py')
        new = functions(HERE / 'closure_binding.py')
        self.assertEqual(set(old), set(new))
        for name in set(old) - {'verify_closed_ir'}:
            self.assertEqual(ast.dump(old[name]), ast.dump(new[name]))

    def test_only_four_launch_transport_statements_differ_in_binding_body(self):
        old = functions(transport.PACKAGE / 'reviewer/closure_binding.py')['verify_closed_ir']
        new = functions(HERE / 'closure_binding.py')['verify_closed_ir']
        def retained(function):
            # Drop the docstring and only statements involving the replacement
            # transport/stdout/inspection join. All raw/source/tail checks remain.
            kept, changed = [], []
            for statement in function.body[1:]:
                text = ast.unparse(statement)
                if "launch['returncode']" in text or 'final_stdout' in text or 'inspection' in text \
                   or "utc(launch['finished_at'])" in text:
                    changed.append(statement)
                else:
                    kept.append(ast.dump(statement))
            return kept, changed
        old_kept, old_changed = retained(old)
        new_kept, new_changed = retained(new)
        self.assertEqual(len(old_changed), 4)
        self.assertEqual(len(new_changed), 4)
        self.assertEqual(old_kept, new_kept)

    def test_exact_local_failed_transport_and_later_inspection_bind(self):
        value = transport.verify_local_failure()
        launch = transport.read(transport.PACKAGE / 'launch-finalize.json')
        self.assertEqual(launch['returncode'], 255)
        self.assertGreater(value['paths']['closures/ir-postguard/finalization.json']['metadata']['finished_at'], launch['finished_at'])
        self.assertGreater(value['observed_at'], value['paths']['closures/ir-postguard/finalization.json']['metadata']['finished_at'])

    def synthetic_remote(self, root):
        inspection = transport.verify_local_failure()
        for name, row in inspection['paths'].items():
            if not row['is_file']:
                continue
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic bytes for ' + name + '\n')
            row['sha256'] = transport.sha(path)
        files = {name: row['sha256'] for name, row in inspection['paths'].items() if row['is_file']}
        metadata = inspection['paths']['closures/ir-postguard/finalization.json']['metadata']
        receipt = {'state': 'complete', 'started_at': metadata['started_at'], 'finished_at': metadata['finished_at']}
        return inspection, files, receipt

    def test_remote_completion_requires_every_inspected_file_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection, files, receipt = self.synthetic_remote(root)
            with mock.patch.object(transport, 'verify_local_failure', return_value=inspection):
                self.assertEqual(transport.verify_remote_completion(transport.PACKAGE, root, files, receipt,
                                                                   {'state': 'complete'}), inspection)
                (root / 'results/ir-test/gate.json').write_text('different\n')
                with self.assertRaisesRegex(ValueError, 'remote result differs'):
                    transport.verify_remote_completion(transport.PACKAGE, root, files, receipt, {'state': 'complete'})

    def test_remote_completion_rejects_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection, files, receipt = self.synthetic_remote(root)
            receipt['state'] = 'failed'
            with mock.patch.object(transport, 'verify_local_failure', return_value=inspection):
                with self.assertRaisesRegex(ValueError, 'finalization metadata differs'):
                    transport.verify_remote_completion(transport.PACKAGE, root, files, receipt, {'state': 'complete'})

    def test_adapter_contains_no_subprocess_or_execution_primitive(self):
        source = ast.parse((HERE / 'transport_contract.py').read_text())
        forbidden = {'run', 'Popen', 'system', 'execve', 'spawn', 'sleep'}
        attributes = {node.func.attr for node in ast.walk(source) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute)}
        self.assertFalse(attributes & forbidden)


if __name__ == '__main__':
    unittest.main(verbosity=2)
