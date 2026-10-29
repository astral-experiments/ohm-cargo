#!/usr/bin/env python3
"""Reproduce an Ohm Cargo test-fixture notification race on Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

HERE = Path(__file__).resolve().parent
COMMIT = '242e7bdc885910beff6872f71300968933293410'
FRESHNESS = 'e2f95194f7aaa7563a922bfa331f8302ca4d750a756a8a1f28da99e04d41008e'
WRAPPERS = {'original': '3ddfc37d39a26bc28c7972c98ce1d537442d0b39107560cff9ce329c8eb5b604',
            'proposed': '7281321d9f3b40dbdc73c34c4a7c0ddb9d4d8cde6d59d52d6b9ba710dbf6d6c5'}
FLUSH = '            io::stderr().flush().expect("flush metadata notification");\n'
GATE = '''
            if env::var("EVIDENCE_PRODUCER").ok().as_deref() == crate_name.as_deref()
                && let Some(waiter) = env::var_os("EVIDENCE_WAITER")
            {
                assert!(Command::new(waiter).status().expect("run bounded handshake").success());
            }
'''
MARKERS = ('dependency-metadata', 'dependency-failed', 'parent-started', 'parent-started-early',
           'dependency-finished', 'parent-timed-out', 'qa-notification-delivered',
           'qa-consumer-observed', 'qa-handshake-timeout')

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

def binary(rustup, supplied, toolchain, command):
    if supplied is None:
        supplied = subprocess.check_output(
            [rustup, 'which', '--toolchain', toolchain, command], text=True).strip()
    path = Path(supplied).resolve(strict=True)
    require(os.access(path, os.X_OK) and path != rustup, f'expected the installed {command} executable')
    return path

def prepare(args, root, rustup):
    rustc = binary(rustup, args.rustc, '1.99.0', 'rustc')
    cargo = binary(rustup, args.cargo, 'ohm', 'cargo')
    sdk = root / 'rustup' / 'toolchains' / 'ohm'
    (sdk / 'bin').mkdir(parents=True)
    (sdk / 'lib').symlink_to(rustc.parent.parent / 'lib', target_is_directory=True)
    proxies = root / 'proxies'
    proxies.mkdir()
    for tool, original in [('cargo', cargo), ('rustc', rustc)]:
        (sdk / 'bin' / tool).symlink_to(original)
        (proxies / tool).symlink_to(rustup)
    env = {'HOME': str(root / 'home'), 'PATH': os.environ['PATH'], 'LC_ALL': 'C',
           'RUSTUP_HOME': str(root / 'rustup'), 'RUSTUP_AUTO_INSTALL': '0',
           'CARGO_NET_OFFLINE': 'true', 'CARGO_TERM_COLOR': 'never', 'TMPDIR': str(root / 'tmp')}
    for key in ('HOME', 'TMPDIR'):
        Path(env[key]).mkdir()
    tools = {tool: {'version': subprocess.check_output(
        [proxies / tool, '+ohm', '-Vv'], env=env, text=True), 'sha256': sha(original.read_bytes())}
             for tool, original in [('cargo', cargo), ('rustc', rustc)]}
    save(root / 'tools.json', tools)
    require('release: ' in tools['cargo']['version'], 'could not identify selected Cargo')
    original = (HERE / 'source-wrapper.rs').read_bytes()
    if args.checkout:
        file = subprocess.check_output(['git', '-C', args.checkout, 'show',
                                       COMMIT + ':tests/testsuite/freshness.rs'])
        require(sha(file) == FRESHNESS, 'unexpected checkout freshness.rs')
        fun = file.decode().split('fn conditional_metadata_pipeline_wrapper()', 1)[1]
        literal = fun.split('"src/main.rs",', 1)[1].split('r#"', 1)[1].split('"#,', 1)[0]
        require((textwrap.dedent(literal).strip()+'\n').encode() == original, 'checkout wrapper mismatch')
    (root / 'original.rs').write_bytes(original)
    subprocess.run(['patch', '--batch', '--fuzz=0', '--output', root / 'proposed.rs',
                    root / 'original.rs', HERE / 'marker-order.diff'], cwd=root, check=True)
    gate = root / 'gate-wait'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', HERE/'gate-wait.c',
                    '-o', gate], env=env, check=True)
    for arm, expected in WRAPPERS.items():
        source = (root / (arm + '.rs')).read_bytes()
        require(sha(source) == expected, f'{arm} wrapper digest mismatch')
        raw = source.decode()
        require(raw.count(FLUSH) == 1, 'expected one flush point')
        live = root / (arm + '-bounded.rs')
        live.write_text(raw.replace(FLUSH, FLUSH + GATE))
        subprocess.run([proxies/'rustc', '+ohm', '--edition=2024', '--crate-name', 'pipeline_wrapper',
                        live, '-o', root/(arm+'-wrapper')], env=env, check=True)
    return proxies/'cargo', env

def history(root, arm, cargo, base_env, trace):
    dest = root / arm
    crate = dest / 'app'
    (crate/'src').mkdir(parents=True)
    (crate/'dep/src').mkdir(parents=True)
    (crate/'Cargo.toml').write_text('[package]\nname="app"\nversion="0.1.0"\nedition="2024"\n'
                                   '[dependencies]\ndep={path="dep"}\n')
    (crate/'dep/Cargo.toml').write_text('[package]\nname="dep"\nversion="0.1.0"\nedition="2015"\nauthors=[]\n')
    (crate/'src/lib.rs').write_text('pub fn value() -> i32 { dep::value() }')
    dep = crate/'dep/src/lib.rs'
    dep.write_text('pub fn value() -> i32 { 1 }')
    log = dest/'wrappers.log'
    env = {**base_env, 'CARGO_HOME':str(dest/'cargo-home'), 'CARGO_TARGET_DIR':str(dest/'target'),
           'CARGO_BUILD_BUILD_DIR':str(dest/'build'), 'RUSTC_WRAPPER':str(root/(arm+'-wrapper')),
           'RUSTFLAGS':'-Zpublic-api-hash', 'CONDITIONAL_PIPELINE_LOG':str(log)}
    summary = {}
    for phase in ('seed','failure','recovery','unchanged'):
        settings = dict(env)
        if phase == 'failure':
            dep.write_text('pub fn value() -> i32 { 2 }')
            settings.update(CONDITIONAL_PIPELINE_PHASE='failure', CONDITIONAL_PIPELINE_CONTROL=str(crate),
                            EVIDENCE_PRODUCER='dep', EVIDENCE_EXPECT='parent-started',
                            EVIDENCE_WAITER=str(root/'gate-wait'))
        if phase == 'recovery':
            for key in MARKERS:
                (crate/key).unlink(missing_ok=True)
            settings['CONDITIONAL_PIPELINE_PHASE']='changed'
        log.write_bytes(b'')
        stage = dest / phase
        stage.mkdir()
        cmd = [cargo, '+ohm', '-Zohm-defaults=no', 'build', '--offline', '-j2']
        if trace:
            syscalls = 'execve,exit_group'
            if phase == 'failure':
                syscalls += ',write,writev,openat,newfstatat,statx'
            cmd = ['strace','-f','-qq','-ttt','-s','450','-e','trace='+syscalls,
                   '-o',stage/'kernel.trace',*cmd]
        with (stage/'stdout').open('wb') as out, (stage/'stderr').open('wb') as err:
            completed = subprocess.run(cmd,cwd=crate,env=settings,stdout=out,stderr=err,timeout=45)
        markers = sorted(k for k in MARKERS if (crate/k).is_file())
        compiles = sorted(log.read_text().splitlines())
        files = [f for directory in (dest/'build',dest/'target') for f in directory.rglob('lib-dep.public-api-hash')]
        state = {'exit':completed.returncode,'compiles':compiles,'markers':markers,
                 'public_hashes':[sha(f.read_bytes()) for f in files]}
        if trace:
            state['trace_sha256']=sha((stage/'kernel.trace').read_bytes())
        save(stage/'observed.json',state)
        require(completed.returncode == (101 if phase=='failure' else 0) and
                compiles == ([] if phase=='unchanged' else ['app','dep']) and
                len(files) == (0 if phase=='failure' else 1),
                f'{arm}/{phase}: unexpected build or fingerprint; see {stage}')
        if phase=='failure':
            expected={'dependency-failed','dependency-metadata','parent-started',
                      'qa-notification-delivered','qa-consumer-observed'}
            if arm=='proposed':
                expected.add('parent-started-early')
            require(set(markers)==expected, f'{arm}: unexpected marker observations {markers}')
        summary[phase]=state
    require(summary['seed']['public_hashes'] != summary['recovery']['public_hashes'] ==
            summary['unchanged']['public_hashes'], f'{arm}: fingerprint failed to recover')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='new, absent directory for both histories')
    parser.add_argument('--cargo', type=Path, help='physical Ohm Cargo; default: rustup which --toolchain ohm cargo')
    parser.add_argument('--rustc', type=Path, help='physical stock rustc; default: rustup which --toolchain 1.99.0 rustc')
    parser.add_argument('--checkout', type=Path, help='independently compare bundled wrapper with the pinned Git source')
    parser.add_argument('--trace',action='store_true',help='also record strace of native compiler and filesystem events')
    args=parser.parse_args()
    require(sys.platform=='linux','the bounded inotify gate requires Linux')
    for program in ['rustup','cc','patch']+(['strace'] if args.trace else []):
        require(shutil.which(program), f'missing {program}')
    root=args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    cargo,env=prepare(args,root,Path(shutil.which('rustup')).resolve())
    results={arm:history(root,arm,cargo,env,args.trace) for arm in ('original','proposed')}
    if args.trace:
        subprocess.run([sys.executable,'-IB',HERE/'verify-replay-trace.py',root],check=True)
    save(root/'verified.json',results)
    for arm, phases in results.items():
        print(f"{arm}: failure={phases['failure']['exit']}, early-marker="
              f"{'parent-started-early' in phases['failure']['markers']}, "
              f"recovery={phases['recovery']['compiles']}, unchanged={phases['unchanged']['compiles']}")

if __name__=='__main__':
    main()
