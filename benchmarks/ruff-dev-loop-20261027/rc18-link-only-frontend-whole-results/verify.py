"""Recompute the whole-Ruff endpoint from every timed ordinary Cargo command and its recorded controls."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
if not __debug__:
    raise SystemExit('Run without Python optimization.')

def read(name):
    return json.loads((here / name).read_bytes())

def sha(name):
    return hashlib.sha256((here / name).read_bytes()).hexdigest()

assert sha('analysis.py') == '7c8e6bd96f9287eedd2003b8190273b3a24e83321888133580d358012cff5d5a'
assert sha('order.json') == '2660149dae2759504657449e52aa55e029a5dddd022333f606c46c7b3797562e'
inputs = read('bindings.json')
assert inputs['analysis'] == sha('analysis.py') and inputs['order'] == sha('order.json')
assert inputs['functional'] == sha('functional/result.json') and inputs['source'] == sha('source.json')
assert sha('functional/SHA256SUMS') == '7a9e633a4369a277b0a78a444a07feab9e5a46f13041f1dbe619a5cf1e8f1e0a'
subprocess.run([sys.executable, '-IB', here / 'functional/verify.py'], cwd=here / 'functional', check=True)
function = read('functional/result.json')
assert function['complete'] and function['admissible'] and not function['fatal_checks']
assert all(function['checks'].values())
source = read('source.json')
source_commits = {'A': '7caf39914da1e28a67744ecbc963a5f26361474d', 'B': 'c9c7fb9df6ca7e8f0c9c12f2471a0d8663bf5c19'}
for arm in ('A', 'B'):
    expected = source['arms'][arm]
    a = function['arms'][arm]
    assert expected['cargo_git_commit'] == source_commits[arm] == a['commit']
    assert expected['sha256'] == inputs['images'][arm] == a['sha256']
    assert len(a['source_phases']) == 5
    for name, phase in a['source_phases'].items():
        assert phase['units'] == 619 and phase['e2e_list_count'] == 200
        is_edited = phase['state'] == 'notebook'
        assert set(phase['selected_rust_tests'].values()) == {101 if is_edited else 0}
        assert phase['e2e_sha256'] == ('d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8' if is_edited
                                       else 'be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7')
    repeat = a['source_phases']['final-repeat']
    assert repeat['fresh'] == 563 and repeat['counts']['rustc-full'] == 1 and repeat['counts']['rustc-link-only'] == repeat['counts']['stock-wild'] == 50
overrides = function['independent_configured_native_matrix']
assert (overrides['commands'], overrides['configurations'], overrides['matched_nonzero_errors']) == (132, 18, 2)
assert sha('component-pairs.json') == read('component-statistics.json')['raw_result_sha256']
component = read('component-pairs.json')
assert len(component) == 240 and Counter(x['endpoint'] for x in component) == {'cargo-edit': 96, 'ruff-link-saturated': 96, 'ruff-link-empty': 48}
pairs, guards = read('pairs.json'), read('guards.json')
assert len(pairs) == len(guards) == 2
for batch, guard, schedule in zip(pairs, guards, read('order.json')['batches'], strict=True):
    assert len(batch) == len(guard['host']) == 24
    assert guard['binding']['admission'] == inputs['admission']
    for native in guard['native'].values():
        assert native == {'rustc-full': 1, 'rustc-link-only': 50, 'gcc': 50, 'collect2': 50, 'stock-wild': 50}
    for p, h, planned in zip(batch, guard['host'], schedule['order'], strict=True):
        assert p['order'] == planned
        assert not h['before']['other_build_tools'] and not h['after']['other_build_tools']
        for arm in ('A', 'B'):
            assert p[arm]['units'] == 619 and p[arm]['fresh'] == 563 and p[arm]['exit'] == 0
            assert len(bytes.fromhex(p[arm]['cargo_stdout_sha256'])) == len(bytes.fromhex(p[arm]['cargo_stderr_sha256'])) == 32
recomputed = json.loads(subprocess.check_output([sys.executable, '-IB', here / 'analysis.py', here / 'pairs.json', '--order', here / 'order.json']))
assert read('statistics.json') == recomputed
subprocess.run([sys.executable, '-IB', here / 'edited/verify.py'], check=True)
assert sha('replication/SHA256SUMS') == '4bb592309829c1e35d45cdad3444feb09a30b94ff995195fbb4d7545613d5794'
subprocess.run([sys.executable, '-IB', here / 'replication/verify.py'], cwd=here / 'replication', check=True)
print(json.dumps(recomputed, indent=2))
