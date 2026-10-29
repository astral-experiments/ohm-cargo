"""Run the unchanged compiler-option crossover with a caller-owned Ohm SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdk', type=Path, help='Ohm SDK containing bin/cargo, bin/rustc, and lib/rustlib')
    parser.add_argument('fresh_directory', type=Path)
    parser.add_argument('--expect', choices=['historical', 'correct', 'observe'], default='observe')
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    dest = args.fresh_directory.resolve()
    dest.mkdir(mode=0o700)
    rustup = shutil.which('rustup')
    if not rustup:
        raise SystemExit('rustup proxies are required')
    proxy = Path(rustup).parent
    private = dest / 'rustup'
    (private / 'toolchains').mkdir(parents=True)
    (private / 'toolchains/ohm').symlink_to(sdk, target_is_directory=True)
    (private / 'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
    cache = dest / 'cargo-home'
    cache.mkdir()
    env = {key: os.environ[key] for key in ('HOME', 'USER', 'LOGNAME', 'SYSTEMROOT') if key in os.environ}
    env.update(PATH=os.pathsep.join((str(proxy), '/usr/bin', '/bin')), RUSTUP_HOME=str(private), CARGO_HOME=str(cache), CARGO_NET_OFFLINE='true', CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never', RUSTUP_AUTO_INSTALL='0', CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8', TZ='UTC')
    totals = []
    for first, other in [('default', 'no'), ('no', 'default')]:
        lane = dest / ('from-' + first)
        source = lane / 'src'
        shutil.copytree(Path(__file__).parent / 'fixture', source)
        target = lane / 'products'
        build_store = lane / 'build-store'
        lane_env = {**env, 'CARGO_TARGET_DIR': str(target), 'CARGO_BUILD_BUILD_DIR': str(build_store)}
        code = source / 'probe/src/main.rs'
        original = code.read_bytes()
        for phase, mode in [('initial', first), ('initial-repeat', first), ('switch', other), ('switch-repeat', other), ('edit', other), ('restore', other), ('restore-repeat', other)]:
            selected = original + (b'fn force_real_build() -> bool { true }\n' if phase == 'edit' else b'')
            if code.read_bytes() != selected:
                code.write_bytes(selected)
            command = ['cargo', '+ohm'] + (['-Zrelink-only=no'] if mode == 'no' else [])
            command += ['build', '--locked', '--offline', '-p', 'probe', '--message-format=json']
            run = subprocess.run(command, cwd=source, env=lane_env, capture_output=True)
            (lane / (phase + '.stdout')).write_bytes(run.stdout)
            (lane / (phase + '.stderr')).write_bytes(run.stderr)
            run.check_returncode()
            events = [json.loads(line) for line in run.stdout.splitlines()]
            assert events[-1] == {'reason': 'build-finished', 'success': True}
            result = subprocess.run([target / 'debug/probe'], env=lane_env, capture_output=True, check=True)
            row = {'from': first, 'phase': phase, 'mode': mode, 'value': int(result.stdout), 'dirty': [e['target']['name'] for e in events if e['reason'] == 'compiler-artifact' and not e['fresh']], 'elf_sha256': digest(target / 'debug/probe')}
            totals.append(row)
            print(first, phase, row['value'], ','.join(row['dirty']) or 'fresh', flush=True)
    outputs = {row['mode']: row['value'] for row in totals if row['phase'] == 'initial'}
    assert outputs == {'default': 17, 'no': 29}
    for row in totals:
        if row['phase'] in ('switch', 'switch-repeat') and args.expect == 'observe':
            continue
        active = row['from'] if args.expect == 'historical' and row['phase'] in ('switch', 'switch-repeat') else row['mode']
        assert row['value'] == outputs[active], row
    report = {'cargo': digest(sdk / 'bin/cargo'), 'rustc': digest(sdk / 'bin/rustc'), 'rows': totals}
    (dest / 'result.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
