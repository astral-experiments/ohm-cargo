"""Read-only adapters for the original J4 archive and frozen raw validators.

The only path mapping is the exact original cohort root to its authenticated
`remote/` archive namespace. No path, flag, counter, sample, or plan is normalized.
"""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = '/tmp/ohm-hillclimb-20261022-joint-183-185-stack181-host2'
HOST = 'charlie-oss-2'
PROTOCOL = '78f34e146b0da9a25f0d6f74bd5d339107c0c7df2aad6b4c6a606159d441936e'
ORIGINAL_MANIFEST = 'de81c8f1eb3d94fd63da45a3242ee385041e1c716b210b014c98cc7c45f58d1c'
ORIGINAL_COMPLETION = 'ae1b7a282878a363e331cce8521bee6ba6af8f490569f4ecd5f9317f2526e743'
ORIGINAL_TAR = 'db3e0ee9132c9d893833ae3271de1af47903d71ddc0e104b8534218e41964c89'
SETUP_MANIFEST = 'f754239d752fe028dfd112dbb4255bd459cb6b77ce0179f709a9eac9696a6732'
SEAL = '14fe39acf1db3ea439ff5dc2b61ec40d78eabb6617d8714ae8f936154a0895f5'
QUALIFICATION = 'da7f203219aa9208834681eb6d007e1ce627d34f050175851169d6313bc0713c'
REVIEW = '006b75a64f5d326c1b188c42a7d48fcbb3918812dcdbc193c760aa7f3f3ba9de'
INTEGRITY = '2f9d1d17049793e07af635a0d8559dd077d7245872d4e5985674a6b7bdbd441d'
SELECTION = 'f49552e77f8c05bd6c660842cfe6ffdca61762b3866d0efd7a796da2bc055076'
PRIVATE_SNAPSHOT = '2980ed3e4600d9d8bc5838c93dddb1c378109df07a1c7f206296c93d1e09c15c'
VARIANTS = {'baseline': '4a80fa441367b53cc8489b126452865a441ef37fe4c59a0ace3fb7d5e3660ae6',
            'candidate': 'adeb8f94e62340b14a4bda2456b1b692b1c3083b9df4195c1da4d252fb7ea09a'}
TREES = {'baseline': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e',
         'candidate': '86a812c401f6a8966e5d9f428775f280c19b7b90'}
SEEDS = (('check', 20261022151), ('test', 20261022152))


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(name):
    need(type(name) is str and name and '\x00' not in name
         and not PurePosixPath(name).is_absolute()
         and str(PurePosixPath(name)) == name
         and not any(part in ('', '.', '..') for part in name.split('/')),
         'unsafe or noncanonical archive path')
    return name


def read_json_bytes(data):
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def public_file(here, name):
    relative(name)
    path = here / name
    need(path.is_file() and not path.is_symlink(), 'missing/linked publication file: ' + name)
    for parent in path.parents:
        if parent == here:
            break
        need(not parent.is_symlink(), 'linked publication directory')
    return path.read_bytes()


def original_record(data, record):
    need(set(record) == {'bytes', 'sha256'} and type(record['bytes']) is int
         and len(data) == record['bytes'] and digest(data) == record['sha256'],
         'original member bytes/hash differ')


def member_record(member):
    relative(member.name)
    need(member.isfile() and member.type == tarfile.REGTYPE and member.mode == 0o644
         and member.uid == member.gid == member.mtime == 0
         and member.uname == member.gname == '' and not member.pax_headers
         and not member.linkname, 'archive member metadata differs')


def load_payload(here, subset, original):
    here = Path(here).resolve()
    inventory = read_json_bytes(public_file(here, 'PUBLICATION-FILES.json'))
    expected_files = inventory['files']
    actual_files = {str(path.relative_to(here)) for path in here.rglob('*') if path.is_file()}
    need(actual_files == set(expected_files) | {'PUBLICATION-FILES.json'}
         and not any(path.is_symlink() for path in here.rglob('*')), 'publication membership differs')
    for name, record in expected_files.items():
        original_record(public_file(here, name), record)
    original_bytes = public_file(here, 'ORIGINAL-IR-MANIFEST.json')
    completion_bytes = public_file(here, 'ORIGINAL-IR-COMPLETION.json')
    need(digest(original_bytes) == ORIGINAL_MANIFEST and read_json_bytes(original_bytes) == original,
         'original transfer record changed')
    need(digest(completion_bytes) == ORIGINAL_COMPLETION, 'original completion changed')
    completion = read_json_bytes(completion_bytes)
    need(completion['state'] == 'complete' and completion['transfer_manifest_sha256'] == ORIGINAL_MANIFEST
         and completion['files_verified_before_and_after'] == 431
         and completion['boundary'] == {'integrity_complete': ['check', 'test'], 'state': 'complete', 'workflow': None},
         'original collection completion differs')
    need(original['root'] == ROOT and original['host'] == HOST and original['phase'] == 'ir'
         and original['measurement_seal_sha256'] == SEAL and len(original['files']) == 431,
         'original collection identity differs')
    selected, omitted = subset['selected'], subset['omitted_private']
    need(set(selected).isdisjoint(omitted) and set(selected) | set(omitted) == set(original['files']),
         'original-to-public conservation differs')
    decision_bytes = public_file(here, 'publication-selection-decision.json')
    need(digest(decision_bytes) == SELECTION, 'exact one-member selection decision changed')
    decision = read_json_bytes(decision_bytes)
    need(set(omitted) == {'delivery-occupancy.json'}
         and decision['public_regular_members'] == 432 and decision['public_collected_files'] == 430,
         'an original member other than the single approved private snapshot was omitted')
    for name, record in selected.items():
        relative(name)
        need(record == original['files'][name], 'selected original record changed')
    for name, record in omitted.items():
        need(record['original_record'] == original['files'][name]
             == {'bytes': 861, 'sha256': PRIVATE_SNAPSHOT}
             and record['reason'] == decision['single_omitted_member']['reason'],
             'omitted original record or reason changed')
    need(subset['original_tar_sha256'] == ORIGINAL_TAR
         and subset['original_manifest_sha256'] == ORIGINAL_MANIFEST
         and subset['all_56_profiles_included'] is True, 'original archive binding differs')
    compressed = public_file(here, 'raw-ir.tar.gz')
    need(digest(compressed) == subset['publication_archive_sha256'], 'compressed archive hash differs')
    need(compressed[:4] == b'\x1f\x8b\x08\x00' and compressed[4:8] == b'\0\0\0\0',
         'gzip wrapper is not deterministic')
    raw = gzip.decompress(compressed)
    need(digest(raw) == subset['publication_tar_sha256'], 'publication tar hash differs')
    if not omitted:
        need(digest(raw) == ORIGINAL_TAR and subset['original_tar_byte_identical'] is True,
             'complete original tar was rewritten')
    else:
        need(subset['original_tar_byte_identical'] is False, 'subset mislabeled as original tar')
    payload, observed, metadata = {}, [], {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive:
            member_record(member)
            name = member.name
            need(name not in observed, 'duplicate archive member')
            observed.append(name)
            data = archive.extractfile(member).read()
            need(len(data) == member.size, 'truncated archive member')
            if name in ('transfer-manifest.json', 'collection-complete.json'):
                metadata[name] = data
                continue
            need(name.startswith('remote/'), 'foreign archive namespace')
            logical = name[len('remote/'):]
            relative(logical)
            need(logical in selected and logical not in payload, 'unselected/duplicate original file')
            original_record(data, selected[logical])
            payload[logical] = data
    need(observed == subset['member_order'] and len(observed) == len(selected) + 2,
         'archive order/member count differs')
    need(set(payload) == set(selected) and metadata == {
        'transfer-manifest.json': original_bytes, 'collection-complete.json': completion_bytes},
        'archive metadata or complete original-file membership differs')
    return payload


class MemoryFile:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def read_bytes(self):
        return self.data

    def read_text(self, errors='strict'):
        return self.data.decode('utf-8', errors=errors)

    def open(self, mode='r', newline=None):
        need(mode in ('r', 'rb'), 'public replay attempted a write')
        return io.BytesIO(self.data) if mode == 'rb' else io.StringIO(self.read_text(), newline=newline)


class Evidence:
    def __init__(self, payload, template_validator):
        self.payload = payload
        self.files = {name: digest(data) for name, data in payload.items()}
        self.seal = read_json_bytes(payload['controller/measurement-seal.json'])
        self.assets = read_json_bytes(payload['controller/assets.json'])
        self.template_validator = template_validator

    def file(self, path):
        need(type(path) is str and path.startswith(ROOT + '/'), 'foreign original cohort path')
        name = relative(path[len(ROOT) + 1:])
        need(name in self.payload, 'missing authenticated original file: ' + name)
        return MemoryFile(name, self.payload[name])

    def config(self, phase, workflow):
        need(phase == 'ir' and workflow in ('check', 'test'), 'unplanned workflow')
        template = read_json_bytes(self.payload['controller/templates/ir-' + workflow + '.json'])
        base = read_json_bytes(self.payload['controller/base-configs/ir-' + workflow + '.json'])
        self.template_validator.validate_template(base, template)
        expected = {**base, 'record_files': sorted(set(self.assets['file_sha256']) | {
            ROOT + '/controller/assets.json', ROOT + '/controller/measurement-seal.json',
            ROOT + '/benchmark/ir-check.json', ROOT + '/benchmark/ir-test.json',
            ROOT + '/metadata/ir-' + workflow + '-preflight/report.json'})}
        name = 'benchmark/ir-' + workflow + '.json'
        actual = read_json_bytes(self.payload[name])
        need(actual == expected and digest(self.payload[name]) == self.seal['configs'][ROOT + '/' + name],
             'derived final configuration differs')
        return actual


def strict_preflight(trace, text, configuration):
    command = configuration['command']
    need(command.count('{cargo}') == 1, 'ambiguous configured Cargo argument slot')
    cargo = [configuration['canonical_executable'], *command[command.index('{cargo}') + 1:]]
    expected = [
        {'executable': '/usr/bin/taskset', 'argv': ['/usr/bin/taskset', '-c', '0-7', *cargo], 'successful': True},
        {'executable': configuration['canonical_executable'], 'argv': cargo, 'successful': True},
    ]
    need(trace.trace_records(text) == expected, 'strict preflight executable/complete argv differs')


def audit_public(here, payload, original, subset, summary):
    here = Path(here).resolve()
    bindings = read_json_bytes(public_file(here, 'bindings.json'))
    for name, record in bindings['original_records'].items():
        original_record(public_file(here, name), record)
    need(digest(public_file(here, 'protocol.json')) == PROTOCOL
         and digest(public_file(here, 'root-qualification.json')) == QUALIFICATION
         and digest(public_file(here, 'independent-review.json')) == REVIEW
         and digest(public_file(here, 'independent-raw-integrity.json')) == INTEGRITY,
         'accepted original protocol/review/integrity/qualification changed')
    protocol = read_json_bytes(public_file(here, 'protocol.json'))
    qualification = read_json_bytes(public_file(here, 'root-qualification.json'))
    review = read_json_bytes(public_file(here, 'independent-review.json'))
    integrity = read_json_bytes(public_file(here, 'independent-raw-integrity.json'))
    need(qualification['qualifies_instruction_only'] is True and qualification['both_required_primary_endpoints'] is True
         and qualification['raw_profiles_verified'] == 56 and qualification['binary_variants'] == VARIANTS
         and qualification['measurement_seal_sha256'] == SEAL
         and qualification['transfer_manifest_sha256'] == ORIGINAL_MANIFEST
         and qualification['raw_integrity_sha256'] == INTEGRITY,
         'accepted qualification joins differ')
    need(review['independent_integrity_accepted'] is True and review['independent_qualification_accepted'] is True
         and review['raw_profiles_verified'] == 56 and review['original_runtime_aliases_verified'] == 2
         and review['open_findings'] == [], 'independent review is not complete')
    need(integrity['status'] == 'passed' and integrity['no_effects_evaluated'] is True,
         'original raw checkpoint did not pass before effects')
    need(digest(payload['controller/measurement-seal.json']) == SEAL, 'measurement seal changed')
    seal = read_json_bytes(payload['controller/measurement-seal.json'])
    need(seal['variants'] == VARIANTS and seal['trees'] == TREES and seal['root'] == ROOT
         and seal['protocol_sha256'] == PROTOCOL and seal['native_phase_planned'] is False
         and seal['stages'] == {'ir': {'pairs': 12, 'plan': [[w, s] for w, s in SEEDS]}},
         'sealed source/pair/stage identities differ')
    setup_bytes = public_file(here, 'ORIGINAL-SETUP-MANIFEST.json')
    need(digest(setup_bytes) == SETUP_MANIFEST, 'original setup catalog changed')
    setup = read_json_bytes(setup_bytes)
    for collection in (setup, original):
        captured = collection['immutable_inputs']
        need(captured['state'] == 'passed' and captured['mismatches'] == []
             and captured['runtime_alias_error'] is None and captured['file_sha256'] == seal['file_sha256']
             and len(captured['file_sha256']) == 847, 'original immutable input catalog differs')
    aliases = setup['immutable_inputs']['runtime_aliases']
    need(len(aliases) == 2 and original['immutable_inputs']['runtime_aliases'] == aliases
         == read_json_bytes(payload['metadata/setup.json'])['runtime_aliases'], 'original runtime alias identity differs')
    need(seal['file_sha256'][ROOT + '/delivery-occupancy.json'] == PRIVATE_SNAPSHOT
         and ROOT + '/delivery-occupancy.json' in original['immutable_inputs']['file_sha256']
         and 'delivery-occupancy.json' not in payload,
         'private sealed provenance exception was removed, altered, or publicly included')
    need(payload['controller/protocol.json'] == public_file(here, 'protocol.json'), 'deployed protocol differs')
    ci = read_json_bytes(payload['controller/provenance/ci.json'])
    need(payload['controller/provenance/ci.json'] == public_file(here, 'source-ci.json')
         and ci['status'] == 'passed' and ci['head_sha'] == protocol['source']['candidate']['commit']
         and ci['head_tree'] == TREES['candidate'] and ci['run_id'] == 39696693562
         and len(ci['required_jobs']) == 8
         and all(job['status'] == 'completed' and job['conclusion'] == 'success' for job in ci['required_jobs']),
         'exact combined source CI differs')
    for name, key in (('source.patch', 'patch_sha256'), ('source.json', 'source_record_sha256'),
                      ('source-manifest.json', 'source_manifest_sha256'), ('source.bundle', 'bundle_sha256')):
        need(digest(public_file(here, name)) == protocol['source']['candidate'][key],
             'combined source identity differs: ' + name)
    need(public_file(here, 'source/full-baseline.patch') == payload['controller/provenance/baseline_patch.data']
         and public_file(here, 'source/full-candidate.patch') == payload['controller/provenance/candidate_patch.data'],
         'complete producer patch copies differ')
    pair = read_json_bytes(payload['controller/provenance/root_review.data'])
    names = {'baseline': 'joint-stack181-baseline', 'candidate': 'joint-stack181-combined'}
    need(pair['status'] == 'passed'
         and {key: pair['binaries'][name] for key, name in names.items()} == VARIANTS
         and {key: pair['source_trees'][name] for key, name in names.items()} == TREES,
         'accepted production pair differs')
    need(summary['source'] == protocol['source'] and summary['binary_variants'] == VARIANTS
         and summary['protocol_sha256'] == PROTOCOL and summary['native_speed_and_regressions'] == 'unverified'
         and summary['both_primary_gates_required'] is True and summary['additive_claim'] is False,
         'summary claim/source scope differs')
    validator = module(here / 'harness/template_validation.py', 'joint_template_validation')
    raw = module(here / 'harness/raw_integrity.py', 'joint_raw_integrity')
    trace = module(here / 'harness/strict_trace.py', 'joint_strict_trace')
    evidence = Evidence(payload, validator)
    for workflow, _ in SEEDS:
        for variant in ('baseline', 'candidate'):
            strict_preflight(trace, payload['metadata/ir-' + workflow + '-preflight/' + variant + '.execve.log'].decode(),
                             evidence.config('ir', workflow))
    workflows = {workflow: raw.raw_workflow(evidence, 'ir', workflow, seed) for workflow, seed in SEEDS}
    need(sum(len(value['profiles']) for value in workflows.values()) == 56,
         'both complete raw datasets are required before statistics')
    accepted = {}
    for value in qualification['effects']:
        accepted[value['workflow']] = {'pairs': value['measured_pairs'], 'wins': value['wins'],
            'losses': value['losses'], 'ties': value['ties'], 'reduction': value['reduction'],
            'interval_99': value['interval_99'], 'sign_p': value['sign_p'], 'orders': value['orders'],
            'gate_checks': value['gate_checks'], 'passes_gate': value['passes_gate'], 'seed': value['seed']}
    need(summary['instructions'] == accepted and set(accepted) == {'check', 'test'}
         and summary['qualifies_instruction_only'] is True, 'derived full-precision summary differs')
    return {'full_profiles': 56, 'complete_workflows': ['check', 'test'],
            'original_input_hash_entries_compared': 847, 'original_runtime_aliases': 2,
            'all_tables_logs_plans_and_contexts_checked': True,
            'effects_calculated': False, 'omitted_original_files': sorted(subset['omitted_private']),
            'private_original_sealed_payload_not_publicly_rehashed': [ROOT + '/delivery-occupancy.json'],
            'full_original_closure_authenticated_locally_before_effects': True}
