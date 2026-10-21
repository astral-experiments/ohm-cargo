#!/usr/bin/env python3
"""Pure schema/guard checks using completed historical data, never Cargo."""
import ast
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
WORK = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


driver = load('inheritance_driver_checks', HERE / 'driver.py')
occupancy = load('inheritance_occupancy_checks', HERE / 'occupancy.py')
checks = []
historical = {}
for phase in ('ir', 'native'):
    for workflow in ('check', 'test'):
        suffix = 'production-ir-confirmation' if phase == 'ir' else 'native-local-confirmation'
        directory = WORK / 'benchmark/results' / (workflow + '-four-changes-stack176-5a16c750-' + suffix)
        result = driver.gate(phase, directory)
        assert result['passes_gate'] is (phase == 'ir')
        assert not result['significant_native_regression']
        driver.audit_sample_tables(directory, driver.read(directory / 'samples.json'), phase)
        historical[str(directory)] = {name: sha(directory / name) for name in ('analysis.json', 'samples.json', 'samples.jsonl', 'samples.csv')}
        checks.append(phase + '-' + workflow + ': unchanged completed schema, gate, and raw table linkage')

with tempfile.TemporaryDirectory(prefix='inheritance-gate-check-') as temporary:
    output = Path(temporary)
    source = WORK / 'benchmark/results/check-four-changes-stack176-5a16c750-native-local-confirmation/analysis.json'
    value = driver.read(source)
    value.update(bootstrap_time_reduction_interval=[-0.04, -0.01],
                 paired_geometric_mean_time_reduction=-0.025, exact_two_sided_sign_p=0.0001)
    (output / 'analysis.json').write_text(json.dumps(value))
    result = driver.gate('native', output)
    assert not result['passes_gate'] and result['significant_native_regression']
    checks.append('Synthetic negative99% interval plus sign test blocks a native regression')


class Probe:
    pid = 99
    returncode = 0

    def __init__(self, output):
        self.output = output

    def communicate(self):
        return self.output, None


cases = [
    ('own probe and controller', '10 python3 99 0\n99 ps 100 0\n', {}, True),
    ('idle unrelated process', '20 python3 0 0\n', {20: b'python3\0unrelated.py\0'}, True),
    ('compiler even while idle', '20 rustc 0 0\n', {}, False),
    ('unrelated busy ps', '20 ps 100 0\n', {}, False),
    ('benchmark controller between children', '20 python3 0 0\n', {20: b'python3\0/tmp/other/native_driver.py\0'}, False),
    ('build queue between children', '20 python3 0 0\n', {20: b'python3\0/tmp/other/build_driver_cohort.py\0'}, False),
]
for label, output, commands, expected in cases:
    def command_bytes(path):
        return commands.get(int(path.parts[2]), b'')
    with patch.object(occupancy.subprocess, 'Popen', return_value=Probe(output)), \
         patch.object(occupancy.os, 'getpid', return_value=10), \
         patch.object(occupancy.os, 'getloadavg', return_value=(0, 0, 0)), \
         patch.object(Path, 'read_bytes', command_bytes):
        try:
            occupancy.require_quiet()
            observed = True
        except AssertionError:
            observed = False
    assert observed == expected, label
    checks.append('Occupancy: ' + label)

protocol = json.loads((WORK / 'workspace-inheritance-candidate/protocol.json').read_text())
for phase in ('ir', 'native'):
    assert protocol[phase]['pairs'] == driver.STAGES[phase]['pairs']
    assert protocol[phase]['seeds'] == dict(driver.STAGES[phase]['plan'])
checks.append('Exact protocol pair counts and immutable seeds')
for path in HERE.glob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
checks.append('Every controller source parses without execution')

report = {'status': 'passed', 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'checks': checks, 'historical_schema_input_sha256': historical,
          'source_sha256': {name: sha(HERE / name) for name in ('driver.py', 'occupancy.py', 'check_controls.py')},
          'scope': 'No host commands, compiler invocation, profiling, timing, resampling or new candidate result inspection.'}
destination = HERE / 'schema-guard-checks.json'
assert not destination.exists()
destination.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': 'passed', 'checks': len(checks), 'report_sha256': sha(destination)}))
