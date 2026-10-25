"""Replay both fixed Cargo-parent blocks from the published Callgrind profiles."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import random
import re
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


def paired_count_statistics(pairs, confidence=0.99, resamples=20000, seed=0):
    if any(pair[variant] <= 0 for pair in pairs for variant in ("baseline", "candidate")):
        return {"pairs": len(pairs), "note": "At least one count is zero; paired ratio statistics omitted."}
    statistics_result = paired_statistics(pairs, confidence, resamples, seed)
    replacements = {"seconds": "count", "speedup": "ratio", "time_reduction": "count_reduction"}
    result = {}
    for name, value in statistics_result.items():
        for old, new in replacements.items():
            name = name.replace(old, new)
        result[name] = value
    result["order"] = {
        order: {"pairs": values["pairs"], "geometric_mean_ratio": values["geometric_mean_speedup"]}
        for order, values in statistics_result["order"].items()
    }
    return result


def final_ir(raw,stderr,expected_argv):
    text=raw.decode();assert text.endswith('\n')and 'positions: line\n'in text and 'events: Ir\n'in text and 'desc: Trigger: Program termination\n'in text
    assert re.findall(r'^part: (\d+)$',text,re.M)==['1']
    cmd=re.findall(r'^cmd:\s*(.*)$',text,re.M);assert cmd==[' '.join(expected_argv)]
    totals=re.findall(r'^totals: (\d+)$',text,re.M);headers=re.findall(r'^summary: (\d+)$',text,re.M);assert len(totals)==len(headers)==1
    final,header=int(totals[0]),int(headers[0]);self_total=0;pending=False
    for line in text.splitlines():
        if line.startswith('calls='):assert not pending;pending=True
        elif line and line[0]in'0123456789+-*':
            match=re.fullmatch(r'(?:\d+|[+-]\d+|\*)\s+(\d+)\s*',line);assert match
            if pending:pending=False
            else:self_total+=int(match[1])
    assert not pending and self_total==final
    collected=re.findall(r'^==\d+== Collected\s*:\s*(\d+)\s*$',stderr,re.M);assert len(collected)==1 and int(collected[0])==final
    return {'final_ir':final,'header_summary_ir':header,'final_minus_header':final-header,'self_cost_sum':self_total,'stderr_collected':int(collected[0]),'brk_overflow_warning':'brk segment overflow'in stderr}


COMMAND = ['cargo', '-Zohm-defaults=yes', 'test', '--no-run', '--locked', '--offline', '-j', '8']
ORDERS = [('BA', 'AB', 'BA', 'AB', 'AB', 'BA', 'BA', 'AB'), ('AB', 'BA', 'AB', 'BA', 'BA', 'AB', 'AB', 'BA')]
SEEDS = (20261025327, 20261025328)


def read(path):
    return json.loads(path.read_text())


def checked_blob(path, row):
    content = path.read_bytes()
    assert len(content) == row['bytes'] and hashlib.sha256(content).hexdigest() == row['sha256'], path
    return content


def main():
    root = Path(__file__).resolve().parent
    for name, row in read(root / 'CORE-MANIFEST.json')['files'].items():
        checked_blob(root / name, row)
    samples = read(root / 'profiles' / 'PROFILE-MANIFEST.json')['profiles']
    blocks = read(root / 'counts.json')['blocks']
    assert len(samples) == 32 and len(blocks) == 2
    decoded = []
    for i, block in enumerate(blocks):
        name = f'block-{i + 1}'
        assert block['name'] == name and block['seed'] == SEEDS[i]
        assert tuple(pair['order'] for pair in block['pairs']) == ORDERS[i]
        pairs = []
        for index, order in enumerate(ORDERS[i]):
            pair = {'pair': index, 'order': order}
            for position, letter in enumerate(order):
                arm = 'baseline' if letter == 'A' else 'candidate'
                key = f'{name}/pair-{index}-{position}-{arm}'
                row = samples[key]
                assert row['file'] == key + '.callgrind.gz'
                payload = checked_blob(root / 'profiles' / row['file'], row)
                raw = gzip.decompress(payload)
                assert len(raw) == row['raw_bytes'] and hashlib.sha256(raw).hexdigest() == row['raw_sha256']
                metric = final_ir(raw, row['counter_line'] + chr(10), COMMAND)
                assert metric == row['metric'] and metric['final_ir'] > 0
                assert metric['brk_overflow_warning'] is False
                pair[arm] = metric['final_ir']
            recorded = block['pairs'][index]
            assert all(recorded[k] == pair[k] for k in ('order', 'baseline', 'candidate'))
            pairs.append(recorded)
        decoded.append(pairs)
    reports = []
    for i, pairs in enumerate(decoded):
        stats = paired_count_statistics(pairs, confidence=0.99, resamples=200000, seed=SEEDS[i])
        expected = read(root / 'results' / f'block-{i + 1}.json')
        assert stats == expected['statistics']
        passed = (stats['wins'] == 8 and stats['exact_two_sided_sign_p'] < 0.01
                  and stats['bootstrap_count_reduction_interval'][0] > 0.01)
        assert passed == expected['block_gate_passed']
        reports.append({'block': i + 1, 'paired_reduction': stats['paired_geometric_mean_count_reduction'],
                        'ci99': stats['bootstrap_count_reduction_interval'], 'wins': stats['wins'],
                        'exact_sign_p': stats['exact_two_sided_sign_p'], 'passed': passed})
    print(json.dumps({'cargo_parent_instructions': reports, 'both_blocks_passed': all(r['passed'] for r in reports)}, indent=2))


if __name__ == '__main__':
    main()
