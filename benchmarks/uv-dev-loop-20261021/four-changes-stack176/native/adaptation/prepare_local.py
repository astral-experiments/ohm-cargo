#!/usr/bin/env python3
"""Materialize and seal the prospective local native amendment; never run Cargo."""
import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
SELF = Path(__file__).resolve()
HERE = SELF.parent
WORK = HERE.parents[1]
OLD = WORK / 'benchmark/current_stack_native'
STAGER = OLD / 'frozen/stage_native-7fe584b190b2.py'
TEMPLATE = OLD / 'frozen/native_driver-4e75a11fac62.py'
TEMPLATE_SHA = '4e75a11fac626f36f2416ca869765d92d1ad7901e5076c3ad291e3f8dcdaf4b4'
STAGER_SHA = '7fe584b190b214cb2c233f60ac370b934583bc0ef6893caf46567df764ee82ab'
PROTOCOL = WORK / 'benchmark/protocol-four-changes-stack176-native-local-amendment.md'
REMOTE_PREFIX = '/tmp/ohm-hillclimb-20261021/native-pr175-confirmation'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == data, path
    else:
        with path.open('xb') as stream:
            stream.write(data)


def dump(path, value):
    put(path, (json.dumps(value, indent=2) + '\n').encode())


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def translated(value):
    if isinstance(value, str):
        return value.replace(REMOTE_PREFIX, str(WORK))
    if isinstance(value, list):
        return [translated(row) for row in value]
    if isinstance(value, dict):
        return {key: translated(row) for key, row in value.items()}
    return value


def materialize():
    assert sha(STAGER) == STAGER_SHA and sha(TEMPLATE) == TEMPLATE_SHA
    stager = load(STAGER, 'reviewed_native_stager')
    files = stager.local_inputs()
    assert not (HERE / 'status.json').exists() and not (HERE / 'native-seal.json').exists()
    original_names = {'native_driver.py', 'stage_native.py', 'source-freeze.json',
                      'schema-review.json', 'gate-schema-review.json',
                      'superseded-source-freeze.json', 'assets.json'}
    retained = []
    for name, source in files.items():
        relative = Path(name).relative_to('current-stack')
        if str(relative) in original_names:
            relative = Path('host8-original') / relative
        elif relative.parts[0] == 'base-configs':
            relative = relative.with_name('host8-' + relative.name)
        destination = HERE / relative
        put(destination, source.read_bytes())
        destination.chmod(source.stat().st_mode & 0o777)
        assert sha(destination) == sha(source)
        retained.append(destination)
    retained.extend([PROTOCOL, SELF])
    put(HERE / 'protocols' / PROTOCOL.name, PROTOCOL.read_bytes())
    retained.append(HERE / 'protocols' / PROTOCOL.name)
    for name in ['transfer.stderr', 'transfer-sha256.json']:
        destination = HERE / 'host8-original/failed-stage' / name
        put(destination, (OLD / name).read_bytes())
        retained.append(destination)
    for source in sorted((OLD / 'occupancy-snapshots').glob('*.json')):
        destination = HERE / 'host8-original/failed-stage' / source.name
        put(destination, source.read_bytes())
        retained.append(destination)
    stop = WORK / 'compiler-audit/obsolete-analysis-stop.json'
    put(HERE / 'occupancy/obsolete-analysis-stop.json', stop.read_bytes())
    retained.extend([stop, HERE / 'occupancy/obsolete-analysis-stop.json'])

    source = TEMPLATE.read_text()
    changes = [
        ('"""Seal and run the prospective host8 current-stack native confirmation."""',
         '"""Seal and run the prospective local current-stack native confirmation."""'),
        ('ROOT = SELF.parents[1]', 'ROOT = SELF.parents[2]'),
        ("STATUS = ROOT / 'native-current-stack-status.json'", "STATUS = SELF.parent / 'status.json'"),
        ("assert socket.gethostname() == 'charlie-oss-8'", "assert socket.gethostname() == 'charlie-oss'"),
        ("PROTOCOLS = {\n", "PROTOCOLS = {\n    " + repr(PROTOCOL.name) + ': ' + repr(sha(PROTOCOL)) + ',\n'),
        ("return {'config': ROOT / 'benchmark' / (label + '-native.json'),\n"
         "            'preflight': ROOT / 'metadata' / (label + '-native-preflight'),\n"
         "            'output': ROOT / 'results' / (label + '-native-confirmation'),\n"
         "            'log': ROOT / 'logs' / (label + '-native-runner.log')}",
         "return {'config': ROOT / 'benchmark' / (label + '-native-local.json'),\n"
         "            'preflight': ROOT / 'benchmark/results' / (label + '-native-local-preflight'),\n"
         "            'output': ROOT / 'benchmark/results' / (label + '-native-local-confirmation'),\n"
         "            'log': ROOT / 'logs' / (label + '-native-local-runner.log')}"),
        ("assert read(ROOT / 'native-combined-status.json')['state'] == 'complete'",
         "assert read(SELF.parent / 'ir-prerequisites.json')['all_four_gates_and_integrity_pass']"),
    ]
    for before, after in changes:
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    driver = HERE / 'native_driver.py'
    put(driver, source.encode())
    retained.append(driver)
    old_ast, new_ast = ast.parse(TEMPLATE.read_text()), ast.parse(source)
    old_functions = {node.name: ast.dump(node) for node in old_ast.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: ast.dump(node) for node in new_ast.body if isinstance(node, ast.FunctionDef)}
    assert set(old_functions) == set(new_functions)
    changed_functions = sorted(name for name in old_functions if old_functions[name] != new_functions[name])
    assert changed_functions == ['paths', 'run', 'verify_assets']
    difference = ''.join(difflib.unified_diff(TEMPLATE.read_text().splitlines(True), source.splitlines(True),
                                            fromfile=str(TEMPLATE), tofile=str(driver)))
    put(HERE / 'source.diff', difference.encode())
    retained.append(HERE / 'source.diff')
    config_reviews = {}
    for workflow in ['check', 'test']:
        original = read(HERE / 'base-configs' / ('host8-' + workflow + '.json'))
        config = translated(original)
        config['env']['CARGO_HOME'] = '/tmp/codex-cargo-home'
        # Historical build records are retained separately; these are the live
        # runtime inputs inherited by the new configuration before provenance.
        config['record_files'] = [path for path in config['record_files']
                                  if '/binaries/stripped/' not in path and '/patches/' not in path
                                  and not path.endswith(('/protocol-upstream-175.md', '/protocol-cumulative-177-178.md',
                                                         '/protocol-native-host8.md', '/diagnose-build-output-remap-loader-v2.py',
                                                         '/native_combined_driver.py'))]
        for path in config['record_files']:
            assert Path(path).is_file(), path
        assert config['command'] == original['command'] and config['prepare_command'] == original['prepare_command']
        assert config['repetitions'] == original['repetitions'] == 8
        assert config['repeatable_workload'] == original['repeatable_workload'] == 'noop'
        expected_environment = translated(original['env'])
        expected_environment['CARGO_HOME'] = '/tmp/codex-cargo-home'
        assert config['env'] == expected_environment
        destination = HERE / 'base-configs' / (workflow + '.json')
        dump(destination, config)
        retained.append(destination)
        config_reviews[workflow] = {'source_sha256': sha(HERE / 'base-configs' / ('host8-' + workflow + '.json')),
                                    'translated_sha256': sha(destination),
                                    'environment': config['env'], 'command': config['command'],
                                    'translation_only_except_cargo_home_and_record_files': True}
    review = {'original_driver_sha256': TEMPLATE_SHA, 'local_driver_sha256': sha(driver),
              'changed_functions': changed_functions,
              'unchanged_functions': sorted(set(old_functions) - set(changed_functions)),
              'changes': ['host identity', 'local work prefix', 'local result paths', 'local amendment binding',
                          'replace historical host8 completion prerequisite with already-required four IR gates'],
              'configurations': config_reviews,
              'no_cargo_or_native_observation': True}
    dump(HERE / 'source-review.json', review)
    retained.append(HERE / 'source-review.json')
    freeze = {'files': {str(path.relative_to(WORK)): sha(path) for path in [SELF, driver, PROTOCOL, HERE / 'source.diff', HERE / 'source-review.json']},
              'scope': 'Prospective local host/fixture amendment; measurement and analysis functions unchanged.'}
    dump(HERE / 'source-freeze.json', freeze)
    retained.append(HERE / 'source-freeze.json')
    assets = {'local_ir_seal_sha256': stager.IR_SEAL_SHA,
              'files': {str(path.relative_to(WORK)): sha(path) for path in sorted(set(retained))}}
    dump(HERE / 'assets.json', assets)
    (WORK / 'tmp').mkdir(exist_ok=True)
    print(json.dumps({'event': 'local_source_materialized', 'assets_sha256': sha(HERE / 'assets.json'),
                      'source_freeze_sha256': sha(HERE / 'source-freeze.json'),
                      'driver_sha256': sha(driver), 'files': len(assets['files'])}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--materialize', action='store_true')
    mode.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    if args.materialize:
        materialize()
    else:
        module = load(HERE / 'native_driver.py', 'local_native_seal')
        module.prepare(module.load_core())


if __name__ == '__main__':
    main()
