"""Offline full-event/payload replay. Python 3.11+, standard library only."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unpack(source, destination, expected):
    destination.mkdir()
    seen = set()
    with tarfile.open(source, 'r|gz') as archive:
        for member in archive:
            assert member.isfile() and not member.issym() and member.name in expected
            assert PurePosixPath(member.name).name == member.name and member.name not in seen
            assert member.mode == 0o644
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            row = expected[member.name]
            assert len(data) == member.size == row['bytes']
            assert hashlib.sha256(data).hexdigest() == row['sha256']
            (destination / member.name).open('xb').write(data)
            seen.add(member.name)
    assert seen == set(expected)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    actual = {str(path.relative_to(HERE)) for path in HERE.rglob('*') if path.is_file()}
    assert actual == set(manifest['files']) | {'manifest.json'}
    for name, row in manifest['files'].items():
        path = HERE / name
        assert path.is_file() and not path.is_symlink()
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
        assert stat.S_IMODE(path.stat().st_mode) == row['mode']
    proof = json.loads((HERE / 'grammar-proof.json').read_bytes())
    assert sha(HERE / 'decode_writes.original.py') == proof['original_sha256']
    assert sha(HERE / 'decode_writes.py') == proof['repaired_sha256']
    old = "        elif char in ')]}>':\n"
    new = "        elif (char == '>' and stack[-2:] == ['<', '[']\n              and re.search(r'<UNIX:\\[[0-9]+-$', text[:index])\n              and re.match(r'[0-9]+\\]>', text[index + 1:])):\n            continue\n" + old
    assert (HERE / 'decode_writes.py').read_text().replace(new, old) == (HERE / 'decode_writes.original.py').read_text()
    tests = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'test_decoder.py')], capture_output=True, text=True, check=True)
    assert len(json.loads(tests.stdout)['checks']) == 18 and tests.stderr == ''
    assert len(load('test_socket').checks()) == 10
    decoder, parser, context = load('decode_writes'), load('env_trace'), load('context_helpers')
    study = json.loads((HERE / 'study.json').read_bytes())
    payloads = json.loads((HERE / 'payloads.json').read_bytes())
    results = []
    with tempfile.TemporaryDirectory(prefix='registry-write-replay-') as temporary:
        root = Path(temporary)
        unpack(HERE / 'final-payloads.tar.gz', root / 'payloads', payloads)
        for call in study['calls']:
            folder = root / call['label']
            unpack(HERE / call['trace_archive'], folder, {row['name']: row for row in call['traces']})
            paths = sorted(folder.iterdir())
            count, events = 0, []
            for path in paths:
                rows = list(decoder.records(path.read_text()))
                count += len(rows)
                for event in rows:
                    if event['kind'] in ('execve', 'execveat'):
                        events.extend(parser.trace_records(path.name.rsplit('.', 1)[1] + ' ' + event['raw'] + '\n'))
            command = json.loads((HERE / 'calls' / call['label'] / 'command.json').read_bytes())
            assert command['returncode'] == 0 and command['error'] is None
            assert command['source_sha256'] == call['actual_native_source_sha256']
            successful = [event for event in events if event['successful']]
            compiler = [event for event in successful if event['executable'] == command['environment']['RUSTC']]
            assert len(compiler) == 1 and '--test' not in compiler[0]['argv']
            assert '--emit=dep-info,metadata' in compiler[0]['argv']
            assert not any(event['executable'] == command['environment']['RUSTDOC'] for event in successful)
            expected_context = json.loads((HERE / 'calls' / call['label'] / 'compiler-reference.json').read_bytes())
            assert context.normalized_compiler(compiler) == expected_context
            native = HERE / 'calls' / call['label']
            assert (native / 'native.stdout').read_bytes() == (native / 'reference.stdout').read_bytes()
            assert context.compile_packages((native / 'native.stderr').read_text()) == ['uv']
            assert context.diagnostics((native / 'native.stderr').read_text()) == context.diagnostics((native / 'reference.stderr').read_text())
            final = {name: root / 'payloads' / row['payload'] for name, row in call['final_slots'].items()}
            result = decoder.decode(paths, call['cache_directory'], final)
            observed = {'decoded_syscalls': count, 'successful_logical_write_bytes': result['successful_logical_write_bytes'],
                        'successful_commits': result['successful_commits'], 'final_logical_bytes': result['final_logical_bytes'],
                        'short_writes': len(result['short_writes']), 'failed_writes': len(result['failed_writes']),
                        'failed_commits': len(result['failed_commits'])}
            assert observed == call['expected']
            seen, replacements = set(), 0
            for commit in result['commits']:
                replacements += commit['target'] in seen
                seen.add(commit['target'])
            assert replacements == call['replacement_commits']
            disposition = json.loads((native / 'disposition.json').read_bytes())
            assert disposition['native_returncode'] == disposition['restoration_returncode'] == 0
            assert disposition['collector_returncode'] == 1 and disposition['full_output_gate_passed'] is False
            assert disposition['source_and_cargo_restored'] and disposition['banks_parked']
            assert all(row['equals_fixed_dirty_reference'] and not row['no_intervening_writer_established'] for row in disposition['restored_outputs'])
            results.append({'call': call['label'], **observed, 'pid_files': len(paths), 'replacement_commits': replacements,
                            'final_slots': len(final), 'original_collector_failure_preserved': True,
                            'original_dirty_output_snapshot_proven': False, 'physical_io_claimed': False})
    report = {'state': 'all-four-full-event-and-payload-replays-pass-with-output-gap', 'calls': results,
              'decoder_checks': 28, 'dropped_syscalls': 0, 'workload_or_guest_calls': 0,
              'timing_or_instruction_comparison': False, 'physical_io_claimed': False}
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        assert not args.output.resolve().is_relative_to(HERE)
        args.output.open('x').write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
