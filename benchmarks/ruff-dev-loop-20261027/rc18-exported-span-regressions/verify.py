"""Verify the four compiler arms using their actual process output and physical binary identities."""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rust-git', type=Path)
args = parser.parse_args()
here = Path(__file__).resolve().parent
arms = {
    'shipped': '618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7',
    '243': '748e5862ece9b0e3098cdae472e1b0d94c50da724b8438f2e267c9007aee8737',
    'rc18-export-r1': '56c284f25daf2ca93cac7bd2f37838dd024205725fd3cb51efac960c0f307708',
    'rc18-export-r2': '22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f',
}
with tarfile.open(here / 'native-streams.tar.gz') as archive:
    members = archive.getmembers()
    assert len(members) == len({m.name for m in members}) == 1154
    assert all(m.isfile() and m.size < 2**20 for m in members)
    files = {m.name: archive.extractfile(m).read() for m in members}


def digest(data):
    return hashlib.sha256(data).hexdigest()


for name, expected in json.loads(files['kit/test-inputs.json']).items():
    if name != 'module-child':
        assert digest(files['kit/' + name]) == expected

for arm, driver in arms.items():
    prefix = arm + '/'
    fixed = arm.startswith('rc18-export-')
    results = json.loads(files[prefix + 'results.json'])
    physical = json.loads(files[prefix + 'physical.json'])
    terminal = json.loads(files[prefix + 'terminal.json'])
    commands = json.loads(files[prefix + 'commands.json'])
    assert results['physical'] == physical == terminal['physical']
    assert physical['driver'] == driver and terminal['status'] == 0
    assert results['arm'] == arm and len(commands) == results['raw_commands'] == 141
    assert results['harness'] == commands[0]['rc'] == (0 if fixed else 1)
    miscompiled = []
    panics = []
    for index, command in enumerate(commands):
        leaf = f"{prefix}raw/{index:03d}-{command['tag']}"
        out, err = (files[leaf + '.' + ext] for ext in ('stdout', 'stderr'))
        assert digest(out) == command['stdout'] and digest(err) == command['stderr']
        scope = command['scope']
        if scope.startswith('ignore-') and command['tag'].endswith('-reader') and command['rc']:
            assert command['rc'] == 101 and b'module_children' in err and command['ice']
            panics.append(command['tag'])
        if scope.startswith('columns-') and command['tag'].endswith('-execute'):
            step = command['tag'].removesuffix('-execute')
            row, = (r for r in results['columns'][scope] if r['step'] == step)
            assert command['rc'] == 0 and int(out.strip()) == row['column']
            if row['column'] != 1 + row['shift']:
                miscompiled.append((scope, step))
    assert len(panics) == (0 if fixed else 8)
    assert len(miscompiled) == (0 if fixed else 12)
    assert len(results['deviations']) == len(panics) + len(miscompiled)
    print(f'{arm}: {len(commands)} commands, {len(panics)} panic results, {len(miscompiled)} stale column results')

if args.rust_git:
    def git(*args_):
        return subprocess.check_output(['git', '-C', str(args.rust_git), *args_])

    binding = json.loads((here / 'compiler-source.json').read_bytes())
    for rev in binding['equivalent_compiler_revisions']:
        assert git('rev-parse', rev + ':compiler').decode().strip() == binding['compiler_tree']
    for name in ('caller.rs', 'reader.rs', 'rmake.rs'):
        ref = binding['built_revision'] + ':tests/run-make/rdr-public-hash-module-child-spans/' + name
        assert git('show', ref) == files['kit/sources/' + name]
