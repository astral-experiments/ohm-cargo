#!/usr/bin/env python3
"""Pure mocked process-table checks; never runs ps or a benchmark."""
import ast
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
old = HERE / 'native_controller-v3.py'
new = HERE / 'native_controller-v4.py'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
before, after = ast.parse(old.read_text()), ast.parse(new.read_text())
for tree in (before, after):
    tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef) or node.name != 'quiet']
assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
spec = importlib.util.spec_from_file_location('allocator_v4_occupancy_checks', new)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Probe:
    pid = 99
    returncode = 0

    def __init__(self, output):
        self.output = output

    def communicate(self):
        return self.output, None


cases = [
    ('normal quiet', '20 0.0 0.0 bash\n', True),
    ('spaced command', '20 0.0 0.0 tmux: server\n', True),
    ('busy spaced command at threshold', '20 50.0 0.0 tmux: server\n', False),
    ('spaced command below threshold', '20 49.9 0.0 tmux: server\n', True),
    ('idle compiler', '20 0.0 0.0 rustc\n', False),
    ('padded idle compiler', '20 0.0 0.0 rustc   \n', False),
    ('idle Cargo variant', '20 0.0 0.0 cargo-candidate\n', False),
    ('idle Callgrind helper', '20 0.0 0.0 callgrind-amd64\n', False),
    ('self and own probe excluded', '10 99.0 0.0 python3\n99 100.0 0.0 ps\n', True),
    ('unrelated busy probe rejected', '20 100.0 0.0 ps\n', False),
    ('quiet spaced process does not mask builder', '20 0.0 0.0 tmux: server\n21 0.0 0.0 rustc\n', False),
]
observed = []
for label, output, expected in cases:
    with patch.object(module.subprocess, 'Popen', return_value=Probe(output)) as popen, \
         patch.object(module.os, 'getpid', return_value=10), \
         patch.object(module.os, 'getloadavg', return_value=(0, 0, 0)):
        try:
            result = module.quiet()
            assert result['process_snapshot'] == output.splitlines()
            accepted = True
        except AssertionError:
            accepted = False
        popen.assert_called_once_with(['ps', '-eo', 'pid=,pcpu=,pmem=,comm=', '--sort=-pcpu'],
                                     stdout=module.subprocess.PIPE, text=True)
    assert accepted == expected, label
    observed.append({'case': label, 'accepted': accepted, 'expected': expected})

report = {'status': 'passed', 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'previous_controller_sha256': sha(old), 'controller_sha256': sha(new),
          'check_script_sha256': sha(Path(__file__)), 'every_ast_node_outside_quiet_unchanged': True,
          'cases': observed, 'no_process_probe_or_cargo_executed': True}
destination = HERE / 'controller-occupancy-v4-checks.json'
assert not destination.exists()
destination.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': 'passed', 'cases': len(cases), 'controller_sha256': sha(new),
                  'report_sha256': sha(destination)}))
