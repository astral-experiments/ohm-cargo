"""Run fresh, unscored three-arm controls with the previously published Ruff leaf fixture."""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys

root = Path(os.environ['OHM_SCOPED_FIXTURE_ROOT']).resolve(strict=True)
inputs = root / 'inputs'
here = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def published(name, filename, digest):
    path = inputs / filename
    assert sha(path) == digest, filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fixture = published('fixture', 'fixture.py', 'b1fadf771e343f808e258bf735067218c8bba2bac56c3f08badf9c6830eb2187')
original = published('original_times', 'run-times.py', '0d56a7567ad93be7958b7ec2d895bcb434992719c9a77ed805d7721d8ff0b028')


def configure(binding):
    assert socket.gethostname() == binding['hostname']
    assigned = set(binding['cpus'])
    assert len(assigned) == 4 and assigned <= os.sched_getaffinity(0)
    assert root == Path(binding['fixture_root']) and root.parent == Path(binding['storage_root'])
    assert shutil.disk_usage(root).free > binding['free_floor_bytes']
    assert set(binding['cargo']) == set('BPN')
    assert len({c['sha256'] for c in binding['cargo'].values()}) == 3
    for c in [*binding['cargo'].values(), binding['common_driver']]:
        assert sha(Path(c['path'])) == c['sha256'], c['path']
    sdk = Path(binding['sdk']).resolve(strict=True)
    for rel, digest in binding['sdk_files'].items():
        assert not Path(rel).is_absolute() and '..' not in Path(rel).parts and sha(sdk / rel) == digest
    assert {'bin/rustc', 'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'} <= set(binding['sdk_files'])
    assert binding['common_driver']['soname'].startswith('librustc_driver-')
    assert (sdk / 'lib' / binding['common_driver']['soname']).is_file()
    wt = Path(binding['ruff_worktree']).resolve(strict=True)
    git = ['git', '--no-optional-locks', '-C', str(wt)]
    assert subprocess.check_output([*git, 'rev-parse', 'HEAD']).decode().strip() == fixture.proof['ruff']
    assert not subprocess.check_output([*git, 'status', '--porcelain'])
    payload = wt / 'crates/ruff_text_size/src/range.rs'
    assert sha(payload) == sha(inputs / 'range.rs') == fixture.proof['original_file_sha256']
    assert sha(inputs / 'edited.rs') == fixture.proof['edited_file_sha256']
    assert sha(inputs / 'package.patch') == fixture.proof['patch_sha256']

    def scope(state, arm):
        return ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc',
                '--bind', root, root, '--tmpfs', '/tmp',
                '--bind', state / 'target', root / 'canonical/target',
                '--bind', state / 'build', root / 'canonical/build',
                '--bind', state / 'home', root / 'canonical/home',
                '--ro-bind', state / 'payload', payload,
                '--ro-bind', sdk, root / 'sdk',
                '--ro-bind', binding['cargo'][arm]['path'], root / 'sdk/bin/cargo',
                '--ro-bind', binding['common_driver']['path'], root / 'sdk/lib' / binding['common_driver']['soname'],
                '--chdir', wt, '--', 'taskset', '-c', ','.join(map(str, sorted(assigned)))]

    fixture.WT = wt
    fixture.src = payload
    fixture.scope = scope
    fixture.keys = {a: c['sha256'] for a, c in binding['cargo'].items()}
    assert list(fixture.env.get(k) for k in ('RUSTFLAGS', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER',
        'CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST', 'CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST')) == [None] * 5


def setup():
    # The input material is the only writable historical state admitted across runs.
    assert not any((root / d).exists() for d in ('records', 'states', 'canonical', 'rustup'))
    for d in ('sdk', 'tmp', 'home', 'canonical/target', 'canonical/build', 'canonical/home', 'rustup/toolchains'):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / 'rustup/toolchains/ohm').symlink_to(root / 'sdk', target_is_directory=True)
    (root / 'rustup/settings.toml').write_text('version = "12"\nprofile = "minimal"\n')


def qualifier(binding):
    configure(binding)
    setup()
    controls = {}
    for kind in ('check', 'build'):
        references = {}
        for state_name in ('B', 'P', 'N', 'B2', 'P2', 'N2'):
            arm = state_name[0]
            state = fixture.init_state(state_name, kind)
            phases = {}
            for phase, edited, write in [('original', False, False), ('edit', True, True),
                    ('unchanged_edit', True, False), ('restore', False, True), ('unchanged_restore', False, False)]:
                if write:
                    fixture.source(state, edited)
                row = fixture.observe(state, kind, arm, phase + '-' + state_name, edited)
                fresh = phase.startswith('unchanged')
                tr = row['trace']
                queries = int(arm == 'P' and not fresh)
                assert row['units'] == 1 and row['fresh'] == fresh and not row['foreign_marker']
                assert row['checksummed_sources'] == 4 and tr['observer_probes'] == queries
                assert len(tr['jobs']) == int(not fresh)
                if not fresh:
                    job, = tr['jobs']
                    assert job['crate'] == 'ruff_text_size' and job['depinfo_flag'] == (arm == 'P')
                if phase != 'original':
                    assert tr['executable_basename_counts'].get('rustc', 0) == int(not fresh) + queries
                if fresh:
                    assert row['outputs'] == phases[phase.removeprefix('unchanged_')]['outputs']
                expected = original.native(row)
                if phase in references:
                    assert expected == references[phase], (kind, state_name, phase)
                else:
                    references[phase] = expected
                phases[phase] = row
            controls[kind + '-' + state_name] = phases
    return controls


if __name__ == '__main__':
    binding = json.loads((inputs / 'frozen-binding.json').read_bytes())
    # A wall experiment needs a separately registered runner, immutable native results and a grant.
    with Path(binding['host_lock']).open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = qualifier(binding)
    print(json.dumps({'binding': sha(inputs / 'frozen-binding.json'), 'controls': result}, separators=(',', ':')))
