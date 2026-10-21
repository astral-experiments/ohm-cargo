#!/usr/bin/env python3
"""Five pure checks and one immutable source/lineage input freeze."""
import ast
import copy
import datetime
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lineage


def main():
    need, common = lineage.common.need, lineage.common
    need(not (HERE / 'source-freeze.json').exists(), 'source freeze already exists')
    selected = {name: {'sha256': 'a' * 64, 'size': 1} for name in common.MOVABLE}
    moves = [{'original': name, 'retained': common.HISTORY + '/' + Path(name).name, 'record': selected[name]}
             for name in common.MOVABLE]
    lineage.verify_moves(moves, selected)
    checks = ['accepts exact synthetic two-metadata move']
    mutations = [
        (lambda rows: rows.reverse(), 'rejects reversed scope/order'),
        (lambda rows: rows.append(copy.deepcopy(rows[0])), 'rejects an extra move'),
        (lambda rows: rows[0].update(retained='results/native-check/samples.json'), 'rejects a workload/result destination'),
    ]
    for mutate, name in mutations:
        changed = copy.deepcopy(moves);mutate(changed)
        try:
            lineage.verify_moves(changed, selected)
        except ValueError:
            checks.append(name)
        else:
            raise ValueError(name + ' did not fail closed')
    wrapper = ast.parse((HERE / 'review.py').read_text())
    calls = [ast.unparse(node.func) for node in ast.walk(wrapper) if isinstance(node, ast.Call)]
    need(calls.count('original.main') == 1 and calls.count('lineage.verify') == 2
         and not any(name.startswith(('subprocess.', 'os.system')) for name in calls), 'wrapper boundary changed')
    checks.append('one unchanged reviewer call between two lineage checks; no subprocess/host call')
    for path in HERE.glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    common.write(HERE / 'source-checks.json', {'status': 'passed', 'checks': checks,
                 'statistics_computed': False, 'native_collection_read': False, 'host_actions': False})
    inputs = {str(path.relative_to(lineage.WORK)): common.sha(path)
              for path in sorted(lineage.ADMISSION.rglob('*')) if path.is_file()}
    for name in ('root-native-replay-launch-review.json', 'root-native-launch-review.json', 'driver.py', 'stage.py', 'source-freeze.json'):
        path = lineage.CONTROLS / name;inputs[str(path.relative_to(lineage.WORK))] = common.sha(path)
    for path in sorted((lineage.CONTROLS / 'native-admission-history/attempt-01').iterdir()):
        need(path.is_file() and not path.is_symlink(), 'unexpected local retained history')
        inputs[str(path.relative_to(lineage.WORK))] = common.sha(path)
    common.write(HERE / 'source-freeze.json', {
        'operation': 'native-admission-lineage-before-unchanged-terminal-review',
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'files': {path.name: common.sha(path) for path in sorted(HERE.iterdir()) if path.is_file()},
        'local_inputs': inputs, 'original_transport_source_freeze_sha256': lineage.TRANSPORT_SOURCE,
        'scope': 'Only a preliminary/final lineage guard; original raw and statistical reviewer byte-identical.'})
    digest = common.sha(HERE / 'source-freeze.json')
    lineage.verify_source(digest)
    print(__import__('json').dumps({'source_freeze_sha256': digest, 'local_inputs': len(inputs), 'pure_checks': len(checks)}, indent=2))


if __name__ == '__main__':
    main()
