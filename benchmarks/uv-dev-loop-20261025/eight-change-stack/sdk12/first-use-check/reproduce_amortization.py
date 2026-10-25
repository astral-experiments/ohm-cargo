"""Replay same-host signed first-use cost and additional warm-check payback."""
from pathlib import Path
import hashlib
import json
import random
import subprocess
import sys

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interpolate(values, quantile):
    rank = (len(values) - 1) * quantile
    index = int(rank)
    return values[index] * (1 - (rank - index)) + values[index + 1] * (rank - index)


def amortization(warm_savings, first_use_costs, seed, draws=200_000):
    assert len(warm_savings) == len(first_use_costs) == 8
    assert all(isinstance(n, int) and n > 0 for n in warm_savings)
    assert all(isinstance(n, int) for n in first_use_costs)
    saved, paid = sum(warm_savings), sum(first_use_costs)
    additional_checks = (max(0, paid) + saved - 1) // saved
    rng = random.Random(seed)
    ratios = []
    for _ in range(draws):
        cold = sum(first_use_costs[int(rng.random() * 8)] for _ in range(8))
        warm = sum(warm_savings[int(rng.random() * 8)] for _ in range(8))
        ratios.append(cold / warm)
    ratios.sort()
    return {
        'mean_first_use_additional_cargo_ir': paid / 8,
        'mean_warm_saved_cargo_ir': saved / 8,
        'first_use_cost_in_warm_checks': paid / saved,
        'additional_warm_checks_to_break_even': additional_checks,
        'descriptive_ratio_interval99': [interpolate(ratios, q) for q in (.005, .995)],
        'bootstrap_draws': draws,
        'seed': seed,
    }


WARM_COUNTS_SHA256 = '4b1cd4c0cfb6c8789dc6746775f9d90dd48a182ccd47a1ba9c10603ff48bc3c7'
AMORTIZATION_SEEDS = (202610250301, 202610250302)
FIRST_USE_SEEDS = (20261025325, 20261025326)
WARM_SEEDS = (20261025321, 20261025322)


def main():
    root = Path(__file__).resolve().parent
    # The complete first-use profile replay is a prerequisite to this payback view.
    subprocess.run([sys.executable, str(root / 'reproduce.py')], check=True)
    assert sha(root / 'warm-counts.json') == WARM_COUNTS_SHA256
    read = lambda name: json.loads((root / name).read_bytes())
    warm, cold, expected = read('warm-counts.json'), read('counts.json'), read('amortization.json')
    assert len(warm['blocks']) == len(cold['blocks']) == len(expected['hosts']) == 2
    assert expected['pooled_statistics'] is None and expected['wall_time_claim'] is False
    results = []
    for index, (a, b) in enumerate(zip(warm['blocks'], cold['blocks'], strict=True)):
        assert a['name'] == b['name'] == f'block-{index + 1}'
        assert a['seed'] == WARM_SEEDS[index] and b['seed'] == FIRST_USE_SEEDS[index]
        assert len(a['pairs']) == len(b['pairs']) == 8
        saved = [pair['baseline'] - pair['candidate'] for pair in a['pairs']]
        paid = [pair['candidate'] - pair['baseline'] for pair in b['pairs']]
        result = {'host': f'host-{index + 1}', 'warm_signed_savings': saved,
                  'first_use_signed_costs': paid,
                  **amortization(saved, paid, AMORTIZATION_SEEDS[index])}
        assert result == expected['hosts'][index]
        results.append(result)
    print(json.dumps({'same_host_amortization': results, 'pooled_statistics': None,
                      'wall_time_claim': False}, indent=2))


if __name__ == '__main__':
    main()
