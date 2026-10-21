#!/usr/bin/env python3
"""Publishable copies of accepted IR evidence; no benchmark or native analysis."""
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
COLLECTION = WORK / 'parser-allocations-measurement-controls-host4-v1/collections/ir'
REMOTE = COLLECTION / 'remote'
CONTROLS = WORK / 'parser-allocations-measurement-controls-host4-v1'
OUTPUT = WORK / 'pr-evidence/parser-allocations-stack181'
POLICY = WORK / 'qualification-policy/instruction-only-publication-20261021'
REVIEW = WORK / 'benchmark-harness-reviews/parser-host4-ir-independent-review02-20261021'
PRIVATE_FIELDS = {'process_snapshot', 'other_workloads', 'competing', 'owned_processes',
                  'process_tree', 'foreign_processes', 'ancestor_processes'}
SECRETS = re.compile(rb'github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def private_fields(value):
    if isinstance(value, dict):
        return sorted((set(value) & PRIVATE_FIELDS) | {k for v in value.values() for k in private_fields(v)})
    if isinstance(value, list):
        return sorted({k for v in value for k in private_fields(v)})
    return []


def permitted(name):
    if name.startswith(('results/ir-check/', 'results/ir-test/', 'metadata/ir-check-preflight/',
                        'metadata/ir-test-preflight/', 'benchmark/')):
        return True, 'complete accepted IR data, preflight or original configuration/runner'
    if name in {'logs/ir-check-runner.log', 'logs/ir-test-runner.log'}:
        return True, 'successful IR runner log'
    if name.startswith(('controller/history/', 'controller/lineage/')):
        return False, 'historical operational lineage retained privately'
    if name.startswith('controller/'):
        if 'occupancy' in name.lower() and not name.endswith(('.py', '.diff', '.md')):
            return False, 'process occupancy metadata retained privately'
        if name.endswith(('.py', '.diff', '.patch', '.toml')):
            return True, 'original source or build patch'
        if name.endswith('.json'):
            return True, 'original controls, source/build provenance or correctness evidence'
        if name.startswith('controller/correctness/'):
            return True, 'focused correctness execution evidence'
    return False, 'operational or redundant transport metadata retained privately'


def put(name, data):
    assert not SECRETS.search(data), 'credential-like bytes in ' + name
    if name.endswith('.json'):
        assert not private_fields(json.loads(data)), 'private process metadata in ' + name
    p = OUTPUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as stream:
        stream.write(data)


def main():
    assert not OUTPUT.exists()
    assert sha(COLLECTION / 'transfer-manifest.json') == 'f525f658ec2ebe29a166d4a179322697b88c3a13dbd05298eb6b5008362c003f'
    assert sha(COLLECTION / 'payload.tar') == 'b65778fec4a26de0c5f767693f27fe7eb5df5e69987ff13adb43848bcf7c5d8a'
    assert sha(CONTROLS / 'root-ir-acceptance.json') == '6ca74836bfcba44094b4ad648b10bb5e72f5f5dc0ef6aa14a1494e7a383026a3'
    assert sha(REVIEW / 'review.json') == '9439e94b5eef546ef755a8060c9ef7210e7d8a442be7ddedb7a89e000dcf5553'
    assert sha(POLICY / 'root-acceptance.json') == 'c6372b7f460693082a7101db82afb8062ed969dc1c524bc1462be80469f77d27'
    manifest = json.loads((COLLECTION / 'transfer-manifest.json').read_text())
    assert len(manifest['files']) == 690
    selected, omitted = {}, {}
    for name, expected in sorted(manifest['files'].items()):
        source = REMOTE / name
        assert source.resolve() == source and source.is_file() and sha(source) == expected, name
        allow, reason = permitted(name)
        data = source.read_bytes() if allow else None
        if allow and source.suffix == '.json':
            fields = private_fields(json.loads(data))
            if fields:
                allow, reason = False, 'private process metadata fields: ' + ', '.join(fields)
        if allow and source.suffix not in {'.py', '.diff', '.patch'}:
            if b"'cpu_percent':" in data or b'"cpu_percent":' in data:
                allow, reason = False, 'operational process-detail bytes retained privately'
        if allow:
            assert not SECRETS.search(data), name
        record = {'sha256': expected, 'bytes': source.stat().st_size, 'reason': reason}
        (selected if allow else omitted)[name] = record
    required = {n for n in manifest['files'] if n.startswith(('results/ir-check/', 'results/ir-test/',
                'metadata/ir-check-preflight/', 'metadata/ir-test-preflight/', 'benchmark/'))}
    assert required <= set(selected), sorted(required - set(selected))
    profiles = [n for n in selected if '/callgrind-' in n]
    assert len(profiles) == 56
    assert set(selected).isdisjoint(omitted) and set(selected) | set(omitted) == set(manifest['files'])
    source = WORK / 'cargo-parser-allocations'
    patch = subprocess.check_output(['git', '-C', str(source), 'diff', '--no-ext-diff', '--no-textconv', '--binary', '--full-index', 'HEAD'])
    assert hashlib.sha256(patch).hexdigest() == '1a8cdf6483044ce3c683313fc5bd802cade777d64d1dc62bb3f9dc2afa49d148'
    ci = json.loads((WORK / 'parser-allocations-publication/ci-complete.json').read_text())
    assert ci['source_commit'] == 'e546abb9353061a13a2448e7b42df52d6ac520fc'
    assert ci['source_tree'] == 'eaf2be878e89248d1ceabff75ce7d2d3272224dd'
    assert ci['raw_run']['status'] == 'completed' and ci['raw_run']['conclusion'] == 'success'
    assert len(ci['required_jobs']) == 8 and all(j['conclusion'] == 'success' for j in ci['required_jobs'])
    OUTPUT.mkdir(parents=True)
    raw_archive = OUTPUT / 'raw-ir.tar.gz'
    with raw_archive.open('xb') as sink, gzip.GzipFile(filename='', fileobj=sink, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as archive:
            for name, row in sorted(selected.items()):
                p = REMOTE / name
                member = tarfile.TarInfo(name)
                member.size, member.mode, member.mtime = row['bytes'], 0o644, 0
                with p.open('rb') as stream:
                    archive.addfile(member, stream)
                assert sha(p) == row['sha256']
    archived = {}
    with tarfile.open(raw_archive, 'r|gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in selected and member.name not in archived
            with archive.extractfile(member) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            assert digest == selected[member.name]['sha256'] and member.size == selected[member.name]['bytes']
            archived[member.name] = digest
    assert set(archived) == set(selected)
    put('ORIGINAL-IR-MANIFEST.json', (COLLECTION / 'transfer-manifest.json').read_bytes())
    put('PUBLICATION-SUBSET.json', encoded({'original_archive_sha256': sha(COLLECTION / 'payload.tar'),
        'original_archive_bytes': (COLLECTION / 'payload.tar').stat().st_size,
        'original_manifest_sha256': sha(COLLECTION / 'transfer-manifest.json'),
        'original_collection_receipt_sha256': sha(COLLECTION / 'receipt.json'),
        'publication_archive_sha256': sha(raw_archive), 'selected': selected, 'omitted_private': omitted,
        'all_56_profiles_and_both_complete_raw_workflow_directories_included': True,
        'native_partial_data_and_failed_operational_archives_not_published': True}))
    for name in ('review.json', 'raw-integrity.json', 'check-reproduced-analysis.json', 'test-reproduced-analysis.json'):
        put('reviews/independent-' + name, (REVIEW / name).read_bytes())
    put('reviews/root-ir-acceptance.json', (CONTROLS / 'root-ir-acceptance.json').read_bytes())
    for name in ('amendment.md', 'decision.json', 'root-acceptance.json'):
        put('publication-policy/' + name, (POLICY / name).read_bytes())
    put('publication-policy/independent-review.json', (WORK / 'benchmark-harness-reviews/instruction-only-publication-amendment-review-20261021/review.json').read_bytes())
    put('native-interruption.json', (WORK / 'benchmark-harness-reviews/parser-native-failure02-opaque-20261021/sanitized-boundary.json').read_bytes())
    put('source.patch', patch)
    shim = WORK / 'profiling-tools/ohm-valgrind-env.c'
    assert sha(shim) == '503c8612d9972ed2ce4ef7b4431e569a8c98d0d5f0d1149dd0fff364513e691b'
    put('reproduction/ohm-valgrind-env.c', shim.read_bytes())
    put('ci.json', encoded({k: ci[k] for k in ['verified_at', 'source_commit', 'source_tree', 'run_id', 'run_url', 'required_jobs', 'optional_jobs']}))
    instructions = {}
    for workflow in ('check', 'test'):
        gate = json.loads((REMOTE / f'results/ir-{workflow}/gate.json').read_text())
        analysis = json.loads((REMOTE / f'results/ir-{workflow}/analysis.json').read_text())['metrics']['cargo_ir']['statistics']
        assert gate['passes_gate'] and all(gate['checks'].values())
        assert analysis['wins'] == analysis['pairs'] == 12 and analysis['losses'] == analysis['ties'] == 0
        instructions[workflow] = {'pairs': 12, 'warmup_pairs': 2, 'wins': 12,
            'reduction': gate['reduction'], 'interval_99': gate['interval_99'], 'sign_p': gate['sign_p'],
            'both_orders_positive': True, 'passes_original_instruction_gate': True}
    status = json.loads((REMOTE / 'results/ir-status.json').read_text())
    put('ir-status-projection.json', encoded({'projection_omits_process_metadata': True,
        'original_sha256': sha(REMOTE / 'results/ir-status.json'),
        **{k: status[k] for k in ('state', 'phase', 'started_at', 'completed_at', 'variants', 'uv', 'integrity_complete')},
        'completed_workflows': [x['workflow'] for x in status['completed']]}))
    put('summary.json', encoded({'source_commit': ci['source_commit'], 'source_tree': ci['source_tree'],
        'parent_commit': 'd81a093becb4321a975522624c2a383970f0d164',
        'parent_tree': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e',
        'uv_commit': '3d82a6ad5a7eab8c68236553b7846517767c4b61',
        'scope': 'Warm unchanged uv, Cargo-process instructions only; no uv test execution or compiler-child counts.',
        'instructions': instructions, 'native': {'status': 'interrupted', 'effects_analyzed': False,
        'regressions_assessed': False, 'wall_time_claim': False},
        'publication_criterion_changed_after_IR_before_native_effect_analysis': True,
        'original_full_protocol_completed': False, 'statistics_regenerated_by_packager': False,
        'matched_builds_have_no_PGO': True, 'correctness_tests_passed': 53,
        'exact_source_CI_passed': True, 'all_profiles_published': 56}))
    for name in ('README.md', 'REPRODUCE.md', 'reproduce_counts.py'):
        put(name, (HERE / name).read_bytes())
    put('assembly-source.py', Path(__file__).read_bytes())
    files = {str(p.relative_to(OUTPUT)): {'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(OUTPUT.rglob('*')) if p.is_file()}
    assert all(v['bytes'] < 100_000_000 for v in files.values())
    with (OUTPUT / 'SHA256SUMS').open('x') as stream:
        stream.writelines(v['sha256'] + '  ' + k + '\n' for k, v in sorted(files.items()))
    with (OUTPUT.with_name(OUTPUT.name + '-manifest.json')).open('xb') as stream:
        stream.write(encoded(files))
    record = {'status': 'assembled-not-published', 'assembled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'artifact': str(OUTPUT), 'publication_files': len(files) + 1, 'original_IR_files_verified': 690,
        'selected_IR_files': len(selected), 'omitted_operational_files': len(omitted), 'profiles': 56,
        'archive_sha256': sha(raw_archive), 'archive_bytes': raw_archive.stat().st_size,
        'manifest_sha256': sha(OUTPUT.with_name(OUTPUT.name + '-manifest.json'))}
    (HERE / 'assembly.json').write_bytes(encoded(record))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
