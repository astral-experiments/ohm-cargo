"""Verify the sealed files and reconstruct the regression results without rebuilding Rust."""
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('ohm_saved_report', Path(__file__).resolve().with_name('report.py'))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def read(path):
    return json.loads(path.read_bytes())


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
manifest = read(root / 'sha256.json')
for name, expected in manifest.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name

subject = read(root / 'subject.json')
summary = read(root / 'subject/summary.json')
assert subject['driver'] == summary['driver']['driver']
head = read(root / 'pr-head.json')
assert subject['commit'] == head['compiled_source_commit'] and subject['pr_head'] == head['pr_head']
assert subject['compiler_tree'] == head['compiled_tree'] == head['current_tree']
assert all(f.startswith('tests/') for f in head['test_only_changes'])
compile_receipt = read(root / 'release-build.json')
assert compile_receipt['candidate_postbolt'] == subject['driver'] and compile_receipt['frontend'] == subject['frontend']
assert compile_receipt['sources'] == {f:pair[1] for f,pair in read(root / 'release-build-source-sha256.json').items()}
rows = json.loads(gzip.decompress((root / 'subject/observations.json.gz').read_bytes()))
assert len(rows) == 12 and summary['issues'] == []
for case, phases in rows.items():
    collected = {p['phase']: report.endpoint(p) for p in phases if p['clean']}
    assert set(collected) == {'caller', 'caller-restore'}
    assert collected == summary['by_case'][case]['endpoints'], case

negative = json.loads(gzip.decompress((root / 'released-control/observations.json.gz').read_bytes()))
assert set(negative) == {'files-shrink', 'local-expn-shrink', 'foreign-expn-shrink'}
for case, phases in negative.items():
    changed = next(p for p in phases if p['phase'] == 'caller')
    assert changed['warm']['cargo_exit'] == 101 and changed['warm']['outside_good']['ice'], case
    assert changed['clean']['cargo_exit'] == changed['clean']['outside_good']['exit'] == 0, case

bridge = read(root / 'ordinary-bridge/observations.json')
assert set(bridge) == {'macro', 'private-impl'}
for case, phases in bridge.items():
    p = phases['prime']['warm']
    assert p['children']['review_producer']['public_flags'][-1] == '-Zpublic-api-hash', case
    assert p['children']['review_bridge']['public_flags'][-1] == '-Zpublic-api-hash=no', case
    for phase in ('producer-edit', 'producer-restore'):
        obs = phases[phase]['warm']
        assert obs['producer_hash'] == p['producer_hash'] and not obs['children']['review_bridge']['link_only'], (case, phase)
    for phase, expected in [('caller-edit', '11'), ('caller-restore', '7')]:
        warm, cold = phases[phase]['warm'], phases[phase]['cold']
        assert warm['elf'] == cold['elf'] and warm['stdout'] == cold['stdout'] == expected
        assert warm['exit'] == cold['exit'] == warm['run_exit'] == cold['run_exit'] == 0
upgrade = read(root / 'upgrade/observations.json')
assert upgrade['toolchains']['new']['version'] == upgrade['toolchains']['old']['version']
old_tools, new_tools = [upgrade['toolchains'][k]['paths_sha256'] for k in ('old','new')]
changed_paths = [f for f,h in old_tools.items() if h != new_tools[f]]
assert len(changed_paths) == 1 and new_tools[changed_paths[0]] == subject['driver']
rows = upgrade['rows']
old, changed, fresh, cold = [rows[k] for k in ('old-prime', 'upgrade', 'new-fresh', 'new-cold')]
assert len({rows[k]['target'] for k in ('old-prime', 'old-fresh', 'upgrade', 'new-fresh')}) == 1
assert len({rows[k]['build'] for k in ('old-prime', 'old-fresh', 'upgrade', 'new-fresh')}) == 1
assert old['source'] == changed['source'] == fresh['source'] == cold['source']
assert old['context'] != changed['context'] == fresh['context']
assert changed['workspace_contexts'] == sorted([old['context'],changed['context']])
assert changed['shared_context_locks'] == [f'context-{s}.lock' for s in changed['workspace_contexts']]
assert changed['elf'] == fresh['elf'] == cold['elf']
for key, count in [('old-prime',3),('old-fresh',0),('upgrade',3),('new-fresh',0),('new-cold',3)]:
    r = rows[key]
    assert sum(not state for state in r['fresh'].values()) == len(r['compiler']) == count and r['runtime'] == '17\n'
    for invocation in r['compiler'].values():assert invocation['public_hash_flags'][-1] == '-Zpublic-api-hash=no' and not invocation['link_only']
print(f'Verified {len(manifest)} files, 24 semantic endpoints, 3 shipped-release regressions, 4 ordinary-profile comparisons and the driver-only upgrade.')
