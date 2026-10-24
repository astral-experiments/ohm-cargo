#!/usr/bin/env python3
"""Verify publication files and every archived byte; optionally extract a new copy."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or str(path) != name:
        raise ValueError(f'Unsafe archive path: {name!r}')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract', type=Path, help='New output directory; must not exist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'publication-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        safe_name(name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing/nonregular publication file: {name}')
        if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
            raise ValueError(f'Publication file changed: {name}')
    actual = {str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()}
    expected = set(manifest['files']) | {'publication-manifest.json'}
    if actual != expected:
        raise ValueError('Unexpected or missing publication files')
    if args.extract is not None:
        args.extract = args.extract.resolve()
        args.extract.mkdir(parents=True, exist_ok=False)
    report = {}
    for label, record in json.loads((root / 'archives.json').read_text()).items():
        source = root / record['archive']
        if digest(source) != record['archive_sha256'] or source.stat().st_size != record['archive_bytes']:
            raise ValueError(f'Archive differs: {label}')
        members = json.loads((root / record['member_manifest']).read_text())
        seen = set()
        with tarfile.open(source, 'r|gz') as archive:
            for member in archive:
                safe_name(member.name)
                if not member.isfile() or member.name in seen or member.name not in members:
                    raise ValueError(f'Unexpected archive member: {member.name}')
                seen.add(member.name)
                data = archive.extractfile(member).read()
                expected = members[member.name]
                if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                    raise ValueError(f'Archive member differs: {member.name}')
                if args.extract is not None:
                    destination = args.extract / label / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as stream:
                        stream.write(data)
                    destination.chmod(member.mode & 0o777)
        if seen != set(members) or len(seen) != record['members']:
            raise ValueError(f'Missing archive members: {label}')
        report[label] = {'members': len(seen), 'all_member_bytes_verified': True}
    print(json.dumps({'publication_files_verified': len(manifest['files']), 'archives': report}, indent=2))


if __name__ == '__main__':
    main()
