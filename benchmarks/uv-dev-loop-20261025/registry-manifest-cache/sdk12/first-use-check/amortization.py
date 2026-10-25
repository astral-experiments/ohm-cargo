"""Exact pre-result same-host amortization helpers; phases are resampled separately."""
import random


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
