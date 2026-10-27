"""Recompute all four edit endpoints and both immediate unchanged controls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

here = Path(__file__).resolve().parent
tag = 'posobs4fmt-c3'
endpoints = ['doc-build', 'doc-test', 'parser-build', 'parser-test']
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    with tarfile.open(here / 'timing-receipts.tar.gz') as archive:
        for member in archive:
            dest = root / member.name
            assert member.isfile() and dest.resolve().is_relative_to(root) and member.size < 7_000_000
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                shutil.copyfileobj(archive.extractfile(member), stream)
    studies = [root / f'pairs-{tag}-{e}' for e in endpoints]
    registered = json.loads((here / 'plan.json').read_bytes())
    for e, s in zip(endpoints, studies, strict=True):
        assert json.loads((s / 'plan.json').read_bytes())['orders'] == registered['endpoints'][e]['orders']
        assert (here / f'{e}.csv').read_bytes() == (s / 'observations.csv').read_bytes()
    calls = {
        'timings.json': [here / 'analyze-native.py', *studies],
        'immediate-noops.json': [here / 'secondary-noops.py', root, tag, here / 'analyze-native.py'],
    }
    for name, command in calls.items():
        actual = json.loads(subprocess.check_output([sys.executable, '-B', *map(str, command)]))
        assert actual == json.loads((here / name).read_bytes()), name
        for r in actual:
            lo, hi = r['paired_bootstrap_95_pct']
            print(f"{r['endpoint']}  {r['parent_median_s']:.3f}s -> {r['candidate_median_s']:.3f}s"
                  f"  {r['geometric_elapsed_reduction_pct']:.1f}% [{lo:.1f}, {hi:.1f}]"
                  f"  Holm p={r['holm_p_across_submitted_endpoints']:.4f}")
