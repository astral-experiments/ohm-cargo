"""Replay separate warm/cold packages, then report per-host instruction amortization."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def amortize(warm_savings, cold_costs, seed):
    path = Path(__file__).with_name('amortization.py')
    spec = importlib.util.spec_from_file_location('frozen_root_amortization', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.amortization(warm_savings, cold_costs, seed)


def compare(warm, cold):
    for root, kind, gate in [(warm, 'warm', 'both_blocks_passed'), (cold, 'cold', 'both_blocks_valid')]:
        assert read(root / 'validation.json')['kind'] == kind
        replay = subprocess.run([sys.executable, '-I', '-S', '-B', str(root / 'reproduce.py')], capture_output=True)
        assert replay.returncode == 0 and json.loads(replay.stdout)[gate] is True
    assert read(warm / 'source-and-recipe.json') == read(cold / 'source-and-recipe.json')
    assert read(warm / 'validation.json')['cargo_sha256'] == read(cold / 'validation.json')['cargo_sha256']
    warm_hosts = read(warm / 'endpoint-inputs.json')['hosts']
    cold_hosts = read(cold / 'endpoint-inputs.json')['hosts']
    warm_blocks = read(warm / 'counts.json')['blocks']
    cold_blocks = read(cold / 'counts.json')['blocks']
    assert len(warm_hosts) == len(cold_hosts) == len(warm_blocks) == len(cold_blocks) == 2
    results = []
    for i in range(2):
        assert warm_hosts[i]['host']['machine_id_sha256'] == cold_hosts[i]['host']['machine_id_sha256']
        wp, cp = warm_blocks[i]['pairs'], cold_blocks[i]['pairs']
        assert len(wp) == len(cp) == 8
        saved = sum(p['baseline'] - p['candidate'] for p in wp)
        extra = sum(p['candidate'] - p['baseline'] for p in cp)
        results.append({'block': i + 1, 'machine_id_sha256': warm_hosts[i]['host']['machine_id_sha256'],
            'warm_saving_sum_ir': saved, 'warm_pairs': 8, 'warm_mean_saving_ir': saved / 8,
            'cold_extra_sum_ir': extra, 'cold_pairs': 8, 'cold_mean_extra_ir': extra / 8,
            **amortize([p['baseline'] - p['candidate'] for p in wp],
                       [p['candidate'] - p['baseline'] for p in cp], 202610250301 + i),
            'warm_statistics': read(warm / 'results' / f'block-{i+1}.json')['statistics'],
            'cold_statistics': read(cold / 'results' / f'block-{i+1}.json')['statistics']})
    return {'state': 'separate-valid-warm-and-cold-counts-replayed', 'hosts': results,
        'warm_counts_sha256': sha(warm / 'counts.json'), 'cold_counts_sha256': sha(cold / 'counts.json'),
        'warm_profile_manifest_sha256': sha(warm / 'profiles/PROFILE-MANIFEST.json'),
        'cold_profile_manifest_sha256': sha(cold / 'profiles/PROFILE-MANIFEST.json'),
        'model': 'One first-use command followed by n commands with the measured warm-cache mixture; arithmetic paired count differences are additive.',
        'limits': 'Descriptive same-host amortization with separate eight-pair resampling for each phase and 200,000 draws. No pooling, full process-tree cost, elapsed-time break-even, guaranteed hit rate, or proof of independent pairs. Cache loss/invalidation repeats the first-use cost.',
        'cold_sign_was_not_a_release_gate': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warm', type=Path, required=True)
    parser.add_argument('--cold', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.warm.resolve(), args.cold.resolve()), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
