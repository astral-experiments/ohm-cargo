#!/usr/bin/env python3
"""Collect only the exact failed native admission metadata after source review."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common


def unpack(path, output):
    seen, manifest = {}, None
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            name = common.relative(member.name)
            common.need(member.isfile() and not member.issym() and not member.islnk() and member.name not in seen,
                        'unsafe capture member')
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            common.need(target.parent.resolve() == target.parent and not target.exists(), 'unsafe extraction path')
            with archive.extractfile(member) as source, target.open('xb') as destination:
                shutil.copyfileobj(source, destination)
            seen[member.name] = common.record(target)
            if member.name == 'transfer-manifest.json':
                manifest = common.read(target)
    common.need(manifest is not None and set(seen) == set(manifest['files']) | {'transfer-manifest.json'}, 'incomplete capture archive')
    common.need(all(seen[name] == expected for name, expected in manifest['files'].items()), 'capture hash/size mismatch')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-freeze-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = common.verify_sources(HERE, args.source_freeze_sha256)
    output = args.output.absolute()
    common.need(output.parent.resolve() == output.parent and not output.exists(), 'capture output must be new and canonical')
    output.mkdir()
    controls = output / 'controls';controls.mkdir()
    for name in (*frozen['files'], 'source-freeze.json'):
        target = controls / common.relative(name);target.parent.mkdir(parents=True, exist_ok=True)
        with (HERE / name).open('rb') as source, target.open('xb') as destination:
            shutil.copyfileobj(source, destination)
    remote = (HERE / 'common.py').read_text() + '\n' + (HERE / 'capture_remote.py').read_text()
    request = {'operation': 'capture-native-zero-work-failure', 'source_freeze_sha256': args.source_freeze_sha256,
               'remote_source_sha256': hashlib.sha256(remote.encode()).hexdigest(),
               'closed_ir_manifest': (HERE / 'inputs/closed-ir-transfer-manifest.json').read_text()}
    common.write(output / 'request.json', request)
    command = ['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh', common.HOST,
               '--', '/usr/bin/env', '-u', 'PYTHONHOME', '-u', 'PYTHONPATH', '-u', 'PYTHONSTARTUP', '-u', 'PYTHONINSPECT',
               '/usr/bin/python3', '-I', '-B', '-c', remote]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (output / 'request.json').open('rb') as incoming, (output / 'payload.tar').open('xb') as stdout, \
         (output / 'transfer.stderr').open('xb') as stderr:
        result = subprocess.run(command, stdin=incoming, stdout=stdout, stderr=stderr)
    common.write(output / 'transport.json', {
        'started_at': started, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'returncode': result.returncode, 'host': common.HOST, 'source_freeze_sha256': args.source_freeze_sha256,
        'archive': common.record(output / 'payload.tar'), 'stderr': common.record(output / 'transfer.stderr'),
        'request_sha256': common.sha(output / 'request.json')})
    common.need(result.returncode == 0, 'capture transport failed; retained without qualification')
    manifest = unpack(output / 'payload.tar', output)
    common.need(manifest['host'] == common.HOST and manifest['root'] == common.ROOT and manifest['seal_sha256'] == common.SEAL
                and manifest['source_freeze_sha256'] == args.source_freeze_sha256, 'capture identity differs')
    common.verify_sources(HERE, args.source_freeze_sha256)
    files = {str(path.relative_to(output)): common.record(path) for path in sorted(output.rglob('*')) if path.is_file()}
    common.write(output / 'capture.json', {'status': 'captured', 'qualification': 'not evaluated', 'files': files,
                 'source_freeze_sha256': args.source_freeze_sha256, 'host_actions': 'read-only capture',
                 'scope': 'No Cargo, measurement, analysis, recovery or moving of any original file.'})
    print(json.dumps({'status': 'captured', 'files': len(files), 'capture_sha256': common.sha(output / 'capture.json'),
                      'payload_sha256': common.sha(output / 'payload.tar')}, indent=2))


if __name__ == '__main__':
    main()
