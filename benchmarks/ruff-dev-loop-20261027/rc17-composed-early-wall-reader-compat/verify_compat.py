"""Run the pinned terminal receiver with the registered score worker's exact progress transcript."""
import collections
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RECEIVER = HERE.parent / 'rc17-composed-early-wall-export-v3c'
MANIFEST_SHA256 = 'c8c0ecc9816c43b71b2b83eea7bcf3f4c576ae8c1047fb668a62a75820f3d9f9'
SOURCE_SHA256 = '322942b938ff235e1eda7964bf909603ff3aa7da658e4230bea08eaceff8f1a6'
OLD = r"""assert raw('launcher/score.out')==''.join(f'{i}/24 guarded pairs\n' for i in range(1,25))"""
NEW = """assert raw('launcher/score.out')==expected_score_stdout(schedule,obj,byname)"""


def expected_score_stdout(schedule, read_receipt, slots):
    """Reproduce the registered native worker's line after each slot, then the wall worker's line after each pair."""
    lines = []
    for block, position, _arm, name in schedule:
        products = read_receipt(name + '/unchanged/products.json')
        counts = dict(collections.Counter(
            job['kind'] if job['exit'] == 0 else job['kind'] + '-failed'
            for job in slots[name]['jobs']
        ))
        assert counts == products['counts']
        lines.append(f"unchanged units {products['units']} fresh {products['fresh']} "
                     f"ELF {len(products['native'])} jobs {counts}\n")
        if position == 2:
            lines.append(f'{block}/24 guarded pairs\n')
    return ''.join(lines)


def load(name):
    """Retain the original command-line interface, data paths and every other verification check."""
    if not __debug__:
        raise RuntimeError('verification requires Python assertions')
    manifest = (RECEIVER / 'SHA256SUMS').read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == MANIFEST_SHA256
    for line in manifest.decode().splitlines():
        expected, relative = line.split('  ', 1)
        path = RECEIVER / relative
        assert path.resolve() == path and hashlib.sha256(path.read_bytes()).hexdigest() == expected
    source_path = RECEIVER / 'verify.py'
    source = source_path.read_bytes()
    assert hashlib.sha256(source).hexdigest() == SOURCE_SHA256
    text = source.decode()
    assert text.count(OLD) == 1
    env = {'__file__': str(source_path), '__name__': name, 'expected_score_stdout': expected_score_stdout}
    exec(compile(text.replace(OLD, NEW), str(source_path), 'exec'), env)
    return env


if __name__ == '__main__':
    load('__main__')
