"""Exact native paired-statistics functions used by the frozen study."""
import math
import random
import statistics


def quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def exact_sign_test(wins, losses):
    non_ties = wins + losses
    if not non_ties:
        return 1.0
    tail = sum(math.comb(non_ties, count) for count in range(min(wins, losses) + 1))
    return min(1.0, 2 * tail / (2 ** non_ties))


def paired_statistics(pairs, confidence=0.99, resamples=20000, seed=0):
    if not pairs:
        raise ValueError("no measurement pairs")
    logs = [math.log(pair["baseline"] / pair["candidate"]) for pair in pairs]
    generator = random.Random(seed)
    bootstraps = [statistics.fmean(generator.choices(logs, k=len(logs))) for _ in range(resamples)]
    alpha = (1 - confidence) / 2
    interval = [math.exp(quantile(bootstraps, alpha)), math.exp(quantile(bootstraps, 1 - alpha))]
    ratio = math.exp(statistics.fmean(logs))
    wins = sum(pair["baseline"] > pair["candidate"] for pair in pairs)
    losses = sum(pair["baseline"] < pair["candidate"] for pair in pairs)
    return {
        "pairs": len(pairs),
        "baseline_median_seconds": statistics.median(pair["baseline"] for pair in pairs),
        "candidate_median_seconds": statistics.median(pair["candidate"] for pair in pairs),
        "baseline_mean_seconds": statistics.fmean(pair["baseline"] for pair in pairs),
        "candidate_mean_seconds": statistics.fmean(pair["candidate"] for pair in pairs),
        "paired_geometric_mean_speedup": ratio,
        "paired_median_speedup": statistics.median(math.exp(value) for value in logs),
        "paired_geometric_mean_time_reduction": 1 - 1 / ratio,
        "confidence": confidence,
        "bootstrap_speedup_interval": interval,
        "bootstrap_time_reduction_interval": [1 - 1 / interval[0], 1 - 1 / interval[1]],
        "bootstrap_resamples": resamples,
        "bootstrap_seed": seed,
        "wins": wins,
        "losses": losses,
        "ties": len(pairs) - wins - losses,
        "exact_two_sided_sign_p": exact_sign_test(wins, losses),
        "log_ratios": logs,
        "order": {
            order: {
                "pairs": len(selected),
                "geometric_mean_speedup": math.exp(statistics.fmean(math.log(pair["baseline"] / pair["candidate"]) for pair in selected)),
            }
            for order in ("AB", "BA")
            if (selected := [pair for pair in pairs if pair.get("order") == order])
        },
    }
