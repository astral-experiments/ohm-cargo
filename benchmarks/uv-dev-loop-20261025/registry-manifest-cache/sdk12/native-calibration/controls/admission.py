"""Private inputs remain unusable until the frozen native prerequisites exist."""
from pathlib import Path

HOSTS = ['host-1', 'host-2']
PRIMARY = '61ef7109939c2c979bd4bce5f0abc8e0234348da7ceede7232b0211bb5e2bfed'
PAIR = '28a3c989dd2351726e79131de8a8a6b913bde45670bb405b55af3a728f4995de'
BASE = '4f7104d7aaf0dec561d8e1457d136f02e0dcdd479fe0bb0957724fba46060306'
CANDIDATE = '19a28bb010372c23ba289f1e2a88c9c519155cb25ab0bb412e88069b2bf15af7'


def donor_arm(phase, label):
    assert phase in ('aa', 'ab') and label in ('baseline', 'candidate')
    return 'baseline' if phase == 'aa' else label


def instruction_bank(old, root, arm):
    assert old['endpoint'] == 'check' and arm in ('baseline', 'candidate')
    parts = old['state_banks'][arm]
    expected = Path(root)/'state-bank'/'check'/arm
    assert set(parts) == {'target', 'shared', 'package-home'}
    assert all(Path(path) == expected/name for name, path in parts.items())
    return expected


def validate_prerequisites(packet, old, protocol, read):
    phase = packet['phase']; assert phase in ('aa', 'ab')
    assert protocol['hosts'] == HOSTS
    assert protocol['primary_protocol_sha256'] == old['protocol']['sha256'] == PRIMARY
    assert protocol['matched_pair_acceptance_sha256'] == PAIR
    assert protocol['AB_cargo_by_label'] == {'baseline': BASE, 'candidate': CANDIDATE}
    assert protocol['AA_cargo_by_label'] == {'baseline': BASE, 'candidate': BASE}
    assert packet['host_index'] == HOSTS.index(packet['hostname'])
    assert set(packet['controls']) == {p.name for p in Path(__file__).parent.glob('*.py')}
    assert packet['hostname'] == old['host']['hostname']
    assert old['endpoint'] == 'check' and old['source']['path'].endswith('/crates/uv/src/lib.rs')
    for arm in ('baseline', 'candidate'):
        instruction_bank(old, protocol['root'], arm)
    assert packet['correctness_acceptance']['sha256'] == PAIR
    correctness = read(packet['correctness_acceptance'])
    assert correctness['correctness_passed'] is True
    assert {r['arm']: r['stripped']['sha256'] for r in correctness['artifacts']} == protocol['AB_cargo_by_label']
    qualification = read(packet['primary_qualification'])
    assert qualification['state'] == 'two-independent-fixed-blocks' and qualification['both_passed'] is True
    assert qualification['cargo_sha256'] == protocol['AB_cargo_by_label']
    cold = read(packet['cold_review'])
    assert cold['state'] == 'accepted-registry-cold-disposition-for-native'
    assert cold['native_protocol_sha256'] == packet['protocol']['sha256']
    assert cold['cold_both_raw_valid'] is True and cold['footprint_and_additional_writes_reviewed'] is True
    release = read(packet['instruction_release'])
    assert release['state'] == 'released-registry-host-to-native'
    assert release['hostname'] == packet['hostname']
    assert release['instruction_inputs_sha256'] == packet['instruction_inputs']['sha256']
    assert release['owned_workloads_remaining'] == release['owned_connections_remaining'] == 0
    assert release['source_and_cargo_restored'] and release['banks_parked']


def validate_bound_input(packet, old, protocol, read):
    assert packet['state'] == 'bound-registry-native-inputs'
    validate_prerequisites(packet, old, protocol, read)
    phase = packet['phase']
    assert packet['source_donors'] == {a: donor_arm(phase, a) for a in ('baseline', 'candidate')}
    assert set(packet['banks']) == set(packet['contexts']) == set(packet['start_manifests']) == {'baseline', 'candidate'}
    assert set(packet['native_output_specs']) == set(packet['native_diagnostics']) == set(packet['native_contexts']) == {'baseline', 'candidate'}
    for label in ('baseline', 'candidate'):
        arm = donor_arm(phase, label)
        assert packet['native_output_specs'][label] == old['output_specs']['check'][arm]
        spec, = packet['native_output_specs'][label]
        assert spec['kind'] == 'exact' and len(spec['sha256']) == 1 and Path(spec['path']).suffix == '.rmeta'
        prior_context = read(old['variants'][arm]['context'])
        current = packet['contexts'][label]
        assert {k: v for k, v in current.items() if k != 'rustc_info'} == {k: v for k, v in prior_context.items() if k != 'rustc_info'}
        assert {k: v for k, v in current['rustc_info'].items() if k != 'inode'} == {k: v for k, v in prior_context['rustc_info'].items() if k != 'inode'}
        assert type(current['rustc_info']['inode']) is int and current['rustc_info']['inode'] > 0
        assert Path(packet['banks'][label]) == Path(protocol['native_root']) / 'phases' / phase / 'banks' / label
        import registry_cache
        witness = read(packet['start_cache_witnesses'][label])
        registry_cache.validate_snapshot(witness, Path(packet['banks'][label])/'package-home', arm)
        preflight = read(old['variants'][arm]['preflight']['check'])
        assert packet['native_contexts'][label] == preflight['rows']['native']['normalized_compiler']
        assert len(packet['native_contexts'][label]) == 1
        command = read(packet['native_command_refs'][label])
        assert command['returncode'] == 0 and command['error'] is None
        assert command['source_sha256'] == preflight['rows']['native']['prepared']['after_sha256']
        assert command['environment'] == old['cargo_environment']
        assert command['argv'][-len(protocol['command']):] == protocol['command']
        for suffix in ('stdout', 'stderr'):
            row = packet['native_diagnostics'][label][suffix]
            expected = old['root'] + '/records/check-preflight-' + arm + '-01/native.' + suffix
            assert row['path'] == expected and row['sha256'] == command[suffix + '_sha256']
    assert packet['native_contexts']['baseline'] == packet['native_contexts']['candidate']
    copy_proof = read(packet['copy_independence'])
    assert copy_proof['state'] == 'native-phase-copies-verified'
    assert copy_proof['phase'] == phase and copy_proof['source_donors'] == packet['source_donors']
    assert copy_proof['no_cross_bank_aliases'] and copy_proof['no_donor_aliases'] and copy_proof['bytes_modes_mtimes_hardlinks_exact']
    assert copy_proof['start_manifests'] == packet['start_manifests']
    capacity = read(packet['raw_retention_capacity'])
    assert capacity['phase'] == phase and capacity['free_bytes'] >= capacity['required_bytes']
    assert capacity['reserve_bytes'] == protocol['disk']['reserve_bytes'] and capacity['original_disposal_authorized'] is False
    if packet['margin'] is not None:
        margin = read(packet['margin_acceptance'])
        assert margin['state'] == 'both-excluded-native-pairs-accepted'
        assert margin['protocol_sha256'] == packet['protocol']['sha256']
        assert margin['hosts'] == HOSTS and margin['individual_times_retained'] == 0
        assert margin['common_margin'] == packet['margin']
    if phase == 'ab':
        decision = read(packet['aa_decision'])
        assert decision['state'] == 'two-independent-native-blocks'
        assert decision['phase'] == 'aa' and decision['both_passed'] is True
        assert decision['protocol_sha256'] == packet['protocol']['sha256']
        assert decision['hosts'] == HOSTS and packet['margin'] is not None

