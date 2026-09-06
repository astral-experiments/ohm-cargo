#!/usr/bin/env python3
"""Untimed cache/process attribution only, on a small local trusted APFS fixture."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/private/tmp/codex-cargo-targets/cargo/isolated/clippy-warm-trace')
OUT = Path(__file__).parent / 'warm-trace'
CARGO = Path('/private/tmp/codex-cargo-targets/cargo/clippy-seeding/ohm/release/cargo')
ROOT.mkdir(exist_ok=False)
OUT.mkdir(exist_ok=False)
sysroot = Path(subprocess.check_output(['rustc', '+ohm', '--print', 'sysroot'], text=True).strip())
env = dict(os.environ)
for key in list(env):
    if key.startswith(('CARGO_', '__CARGO_', 'RUSTC_', 'RUSTUP_', 'RUSTFLAGS', 'DYLD_')):
        env.pop(key)
env.update(CARGO_HOME='/private/tmp/codex-cargo-home', CARGO=str(CARGO),
           RUSTC=str(sysroot / 'bin/rustc'), RUSTUP_TOOLCHAIN='ohm',
           CARGO_TARGET_DIR=str(ROOT / 'outputs'), CARGO_BUILD_BUILD_DIR=str(ROOT / 'shared'),
           CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all', CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',
           CARGO_LOG='cargo::util::rustc=debug',
           PATH=os.pathsep.join([str(CARGO.parent), str(sysroot / 'bin'),
                                 '/Users/charliemarsh/.cargo/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']))
donor = ROOT / 'donor'
(donor / 'src').mkdir(parents=True)
(donor / 'Cargo.toml').write_text('[package]\nname="warm_trace"\nversion="0.1.0"\nedition="2024"\n')
(donor / 'src/lib.rs').write_text('pub fn value() -> u32 { 42 }\n')
(donor / '.gitignore').write_text('/Cargo.lock\n')
rows = []
for label, argv in [('init', ['git', 'init']), ('add', ['git', 'add', '.']),
                    ('commit', ['git', '-c', 'user.name=Benchmark', '-c', 'user.email=benchmark@example.invalid',
                                '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture']),
                    ('build', [str(CARGO), 'build', '--offline']),
                    ('clippy-first', [str(CARGO), 'clippy', '--offline']),
                    ('clippy-warm1', [str(CARGO), 'clippy', '--offline']),
                    ('clippy-warm2', [str(CARGO), 'clippy', '--offline'])]:
    result = subprocess.run(argv, cwd=donor, env=env, capture_output=True, text=True)
    (OUT / (label + '.log')).write_text(result.stdout + result.stderr)
    rows.append({'label': label, 'argv': argv, 'returncode': result.returncode,
                 'cache_trace': [line for line in result.stderr.splitlines() if 'cargo::util::rustc:' in line]})
    assert result.returncode == 0, result.stderr
receipt = {'scope': 'Untimed tiny local APFS fixture, attribution only; not representative performance evidence',
           'cargo_sha256': hashlib.file_digest(CARGO.open('rb'), 'sha256').hexdigest(),
           'cargo_version': subprocess.check_output([CARGO, '-Vv'], text=True),
           'environment': {key: value for key, value in env.items() if key.startswith(('CARGO_', 'RUST')) or key == 'PATH'},
           'isolated_paths': [str(path) for path in (ROOT / 'shared').rglob('.ohm-clippy-v1')],
           'commands': rows}
assert receipt['isolated_paths']
(OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
