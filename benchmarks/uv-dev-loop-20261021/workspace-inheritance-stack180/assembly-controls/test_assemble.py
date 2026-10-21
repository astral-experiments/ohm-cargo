"""Synthetic-only evidence packaging checks; no actual phases or statistics."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('inheritance_assembly_under_test', HERE / 'assemble.py')
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)


class AssemblyTests(unittest.TestCase):
    def make_capture(self, directory, duplicate=False, link=False):
        directory = Path(directory)
        (directory / 'remote/logs').mkdir(parents=True)
        (directory / 'remote/logs/example.txt').write_bytes(b'unchanged synthetic observation\n')
        manifest = {'seal_sha256': assembly.SEAL, 'driver_sha256': assembly.DRIVER,
                    'root': assembly.REMOTE, 'files': {'logs/example.txt': assembly.sha(directory / 'remote/logs/example.txt')}}
        (directory / 'transfer-manifest.json').write_bytes(assembly.encoded(manifest))
        with tarfile.open(directory / 'payload.tar', 'w') as archive:
            names = ['transfer-manifest.json', 'remote/logs/example.txt']
            if duplicate:
                names.append('remote/logs/example.txt')
            for name in names:
                data = (directory / name).read_bytes()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            if link:
                info = tarfile.TarInfo('remote/link')
                info.type = tarfile.SYMTYPE
                info.linkname = '/elsewhere'
                archive.addfile(info)
        (directory / 'transport.json').write_text('{"returncode": 0}\n')
        return assembly.sha(directory / 'transfer-manifest.json')

    def test_original_archive_and_envelope_are_retained(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            digest = self.make_capture(root)
            original = (root / 'payload.tar').read_bytes()
            _, inventory = assembly.inventory_capture(root, digest)
            self.assertEqual(inventory['original_payload']['sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(set(inventory['envelope_files']), {'payload.tar', 'transfer-manifest.json', 'transport.json'})
            self.assertEqual((root / 'payload.tar').read_bytes(), original)

    def test_extra_extracted_raw_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); digest = self.make_capture(root)
            (root / 'remote/extra').write_text('unexpected')
            with self.assertRaisesRegex(ValueError, 'extra or missing'):
                assembly.inventory_capture(root, digest)

    def test_changed_raw_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); digest = self.make_capture(root)
            (root / 'remote/logs/example.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'captured bytes differ'):
                assembly.inventory_capture(root, digest)

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); digest = self.make_capture(root, duplicate=True)
            with self.assertRaisesRegex(ValueError, 'duplicate original archive'):
                assembly.inventory_capture(root, digest)

    def test_archive_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); digest = self.make_capture(root, link=True)
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                assembly.inventory_capture(root, digest)

    def test_extracted_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); digest = self.make_capture(root)
            path = root / 'remote/logs/example.txt'
            path.unlink(); path.symlink_to(root / 'transport.json')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                assembly.inventory_capture(root, digest)

    def lineage(self):
        admission = assembly.encoded({'status': 'passed', 'zero_native_observations_replaced': True,
            'original_phase_controls_unchanged': True, 'native_transfer_manifest_sha256': 'capture',
            'source_freeze_sha256': assembly.NATIVE_REVIEW_SOURCE})
        review = {'status': 'valid-negative', 'qualifies': False}
        binding = {'status': 'passed', 'original_returncode': 0, 'source_freeze_sha256': assembly.NATIVE_REVIEW_SOURCE,
            'lineage_before_effects_sha256': hashlib.sha256(admission).hexdigest(), 'original_review_sha256': 'review',
            'original_review_status': 'valid-negative', 'qualifies': False, 'lineage_unchanged_after_review': True,
            'sampling_or_analysis_driver_changed': False}
        transport = {'state': 'passed', 'phase': 'native', 'original_review_sha256': 'review',
            'original_review_status': 'valid-negative', 'qualifies': False,
            'transport_source_freeze_sha256': assembly.TRANSPORT_REVIEW_SOURCE}
        return admission, binding, transport, review

    def test_valid_negative_native_lineage_stays_negative(self):
        admission, binding, transport, review = self.lineage()
        assembly.verify_native_lineage(admission, binding, transport, review, 'review', 'capture')
        self.assertFalse(review['qualifies'])
        self.assertEqual(review['status'], 'valid-negative')

    def test_each_native_lineage_join_rejects_mismatch(self):
        for field, value in [('lineage_before_effects_sha256', 'other'), ('original_review_sha256', 'other'),
                             ('lineage_unchanged_after_review', False), ('sampling_or_analysis_driver_changed', True),
                             ('source_freeze_sha256', 'other'), ('original_returncode', 2), ('qualifies', True)]:
            with self.subTest(field=field):
                admission, binding, transport, review = self.lineage()
                binding[field] = value
                with self.assertRaises(ValueError):
                    assembly.verify_native_lineage(admission, binding, transport, review, 'review', 'capture')

    def test_native_transfer_or_transport_mismatch_is_rejected(self):
        admission, binding, transport, review = self.lineage()
        with self.assertRaises(ValueError):
            assembly.verify_native_lineage(admission, binding, transport, review, 'review', 'other')
        transport['transport_source_freeze_sha256'] = 'other'
        with self.assertRaises(ValueError):
            assembly.verify_native_lineage(admission, binding, transport, review, 'review', 'capture')

    def phase(self, directory, phase='native'):
        directory = Path(directory)
        (directory / 'remote/results').mkdir(parents=True)
        native = phase == 'native'
        pairs, subruns, samples = (30, 512, 64) if native else (12, 0, 28)
        seeds = (20261021113, 20261021114) if native else (20261021111, 20261021112)
        complete = [{'workflow': workflow, 'passes_gate': not native, 'significant_native_regression': False}
                    for workflow in ('check', 'test')]
        status = {'state': 'complete', 'phase': phase, 'seal_sha256': assembly.SEAL, 'variants': assembly.EXPECTED,
                  'integrity_complete': ['check', 'test'], 'completed': complete}
        status_path = directory / 'remote/results' / (phase + '-status.json')
        status_path.write_bytes(assembly.encoded(status))
        manifest = {'files': {'results/' + phase + '-status.json': assembly.sha(status_path)}}
        (directory / 'transfer-manifest.json').write_bytes(assembly.encoded(manifest))
        review = {'phase': phase, 'status': 'valid-negative' if native else 'passed', 'integrity_status': 'passed',
            'final_evidence_and_review_source_rehash': 'passed', 'statistics_computed': True, 'variants': assembly.EXPECTED,
            'measurement_seal_sha256': assembly.SEAL, 'source_freeze_sha256': assembly.SOURCE,
            'bootstrap': {'confidence': .99, 'resamples': 20000, 'seed': 1701}, 'raw_file_sha256': manifest['files'],
            'transfer_manifest_sha256': assembly.sha(directory / 'transfer-manifest.json'), 'completed': complete,
            'terminal_status_sha256': assembly.sha(status_path), 'workflows': [
                {'workflow': workflow, 'status': 'passed', 'all_tables_logs_plans_sums_and_identities_match': True,
                 'pairs': pairs, 'warmup_pairs': 2, 'seed': seed, 'subruns': subruns, 'samples': samples,
                 'unwanted_compilation_signatures': 0} for workflow, seed in zip(('check', 'test'), seeds)],
            'significant_native_regression': False, 'ir_review_sha256': assembly.IR_REVIEW, 'qualifies': not native}
        source = directory / 'review.json'; source.write_bytes(assembly.encoded(review))
        return source, manifest, review

    def test_completed_negative_native_without_regression_can_be_disclosed(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest, review = self.phase(name)
            self.assertEqual(assembly.review_phase('native', source, manifest, Path(name)), review)

    def test_significant_native_regression_blocks_assembly(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest, review = self.phase(name)
            review['significant_native_regression'] = True
            source.write_bytes(assembly.encoded(review))
            with self.assertRaisesRegex(ValueError, 'regression blocks'):
                assembly.review_phase('native', source, manifest, Path(name))

    def test_incomplete_or_changed_counts_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest, review = self.phase(name)
            for field, value in [('pairs', 31), ('subruns', 520), ('seed', 99), ('unwanted_compilation_signatures', 1)]:
                changed = copy.deepcopy(review); changed['workflows'][0][field] = value
                source.write_bytes(assembly.encoded(changed))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'fixed independent workflow'):
                    assembly.review_phase('native', source, manifest, Path(name))
            changed = dict(review, statistics_computed=False)
            source.write_bytes(assembly.encoded(changed))
            with self.assertRaisesRegex(ValueError, 'review incomplete'):
                assembly.review_phase('native', source, manifest, Path(name))

    def test_failed_ir_gate_blocks_assembly(self):
        with tempfile.TemporaryDirectory() as name:
            source, manifest, review = self.phase(name, 'ir')
            review['qualifies'] = False
            source.write_bytes(assembly.encoded(review))
            with self.assertRaisesRegex(ValueError, 'IR gates did not qualify'):
                assembly.review_phase('ir', source, manifest, Path(name))


if __name__ == '__main__':
    unittest.main(verbosity=2)
