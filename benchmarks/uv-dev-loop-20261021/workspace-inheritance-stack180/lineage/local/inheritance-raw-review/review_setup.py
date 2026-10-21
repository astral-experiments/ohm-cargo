#!/usr/bin/env python3
"""Read-only setup review; never loads performance samples or computes statistics."""
import argparse
import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import Evidence, FREEZE, ROOT, SEAL, STAGES, need, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'review output already exists')
    evidence = Evidence(args.controls, 'setup')
    evidence.bind()
    configs = {}
    records = set()
    for phase in STAGES:
        for workflow, _ in STAGES[phase]['plan']:
            config = evidence.config(phase, workflow)
            configs[phase + '-' + workflow] = {'sha256': evidence.files['benchmark/' + phase + '-' + workflow + '.json'],
                                             'record_files': len(config['record_files'])}
            records.update(config['record_files'])
    future = {ROOT + '/metadata/native-prerequisite.json'} | {
        ROOT + '/metadata/' + phase + '-' + workflow + '-preflight/report.json'
        for phase in STAGES for workflow, _ in STAGES[phase]['plan']}
    need(set(evidence.seal['future_reports']) == future, 'future-file set differs')
    need(set(evidence.seal['file_sha256']) == records - future - {ROOT + '/controller/measurement-seal.json'}, 'seal input union differs')
    need(not any(name.startswith('results/') or '-preflight/' in name for name in evidence.files), 'setup already contains performance artifacts')
    report = {'status': 'passed', 'reviewed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_freeze_sha256': FREEZE, 'measurement_seal_sha256': SEAL,
              'transfer_manifest_sha256': sha(evidence.directory / 'transfer-manifest.json'),
              'archive_sha256': sha(evidence.directory / 'payload.tar'),
              'files_verified': len(evidence.files), 'configs': configs,
              'sealed_input_count': len(evidence.seal['file_sha256']),
              'source_files': {name: sha(Path(__file__).parent / name) for name in ('review_setup.py', 'evidence.py')},
              'checks': {'fresh_production_pair_only': True, 'source_build_strip_correctness_ci_bound': True,
                         'base_record_files_preserved_with_exact_ordered_expansion': True,
                         'all_four_configs_and_input_union_bound': True, 'build_only_commands': True,
                         'ancestor_configuration_bound': True, 'no_collected_preflight_or_measurements': True},
              'scope': 'Independent local archive, input, source and generated-configuration review. Excluded runtime/binary payloads are bound through the frozen remote seal and audited production/delivery records. No host access, fixture execution or statistics.'}
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
