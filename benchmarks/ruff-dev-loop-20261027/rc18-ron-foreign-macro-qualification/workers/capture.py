"""Read the genuine retained Ron unit. Do not invoke Cargo or mutate its stores."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import ast
import json
import os
import re
import struct
import sys


def digest(data):
    return sha256(data).hexdigest()


def decode(record):
    pos = 0

    def take(n):
        nonlocal pos
        block = record[pos:pos+n]
        assert len(block) == n
        pos += n
        return block

    def u32():
        return int.from_bytes(take(4), 'little')

    def field():
        return take(u32())

    assert take(5) == bytes.fromhex('01000000ff')
    version = int.from_bytes(take(1))
    files = []
    for _ in range(u32()):
        kind, path = int.from_bytes(take(1)), field()
        has_checksum = int.from_bytes(take(1))
        if has_checksum:
            take(8)
            field()
        files.append((kind, path, bool(has_checksum)))
    env_count = u32()
    for _ in range(env_count):
        field()
        if int.from_bytes(take(1)):
            field()
    assert take(4) == b'OBS1'
    observer = u32()
    status = int.from_bytes(take(1))
    body, seal = record[:pos], take(32)
    assert pos == len(record)
    marker = files[observer][1]
    assert marker.endswith(b'.d/ohm-foreign-span-bytes')
    return {'version': version, 'number_of_paths': len(files), 'checksummed': sum(x[2] for x in files),
            'package_relative': sum(x[0] == 0 for x in files), 'env_count': env_count,
            'marker_index': observer, 'marker_status': status,
            'marker_suffix': marker.rsplit(b'/', 2)[-2].decode() + '/ohm-foreign-span-bytes',
            'marker_path_sha256': digest(marker), 'body_sha256': digest(body), 'blake3_seal': seal.hex()}


def main(root, labels):
    def read(path):
        return json.loads(path.read_bytes())

    output = {}
    for label in labels:
        d = root / 'reports' / label
        summary = read(d/'result.json')
        jobs = read(d/'native.json')
        ron, = [row for row in jobs if row['kind'] == 'full' and row['id'] == 'ron']
        lines = (d/'trace'/('exec.'+str(ron['pid']))).read_bytes().splitlines()
        args = []
        for line in lines:
            if not (line.startswith(b'execve(') and line.endswith(b'= 0') and b'"--crate-name", "ron"' in line):
                continue
            match = re.fullmatch(rb'execve\(("(?:(?:\\.)|[^"\\])*"),\s*(\[.*\]), (?:0x[\da-f]+|NULL).*?\)\s+= 0', line)
            assert match
            a = ast.literal_eval(match[2].decode())
            assert digest(match[2]) == ron['argv_sha256']
            args.append(a)
        argv, = args
        externs = []
        for i, item in enumerate(argv):
            if item == '--extern':
                name, filename = argv[i+1].split('=',1)
                p = Path(filename)
                raw = p.read_bytes()
                externs.append(dict(name=name, kind=p.suffix, size=len(raw), sha256=digest(raw),
                                    literal_path_sha256=digest(os.fsencode(p)), current_inode=p.stat().st_ino))
        out = Path(argv[argv.index('--out-dir')+1]); assert out.is_relative_to(root)
        fps = out.parent/'fingerprint'; encoded = (fps/'dep-lib-ron').read_bytes()
        source_file, = out.glob('ron-*.d'); source = source_file.read_bytes()
        marker = b'ohm-foreign-span-bytes'
        pkg_artifact, = [m for m in (json.loads(s) for s in (d/'cargo.stdout').read_bytes().splitlines())
                         if m.get('reason') == 'compiler-artifact' and m['target']['name'] == 'ron']
        fp = read(fps/'lib-ron.json')
        command = read(d/'command.json')
        output[label] = {'history': {k:summary[k] for k in ['arm','state','scope','units','fresh','native']},
            'declared_cargo_fresh':pkg_artifact['fresh'], 'invocation_sha256':ron['argv_sha256'],
            'compiler_binary_sha256':command['images'], 'ron_process':ron['pid'],
            'output_history':{k:{Path(p).suffix:v for p,v in summary[k].items()} for k in ['ron_before','ron_after']},
            'genuine_observer_dir_at_read_time':{'raw_rustc_depinfo_sha256':digest(source),
                'rustc_marker_mentions':source.count(marker), 'cargo_record_sha256':digest(encoded),
                'cargo_record':decode(encoded), 'cargo_fingerprint_sha256':digest((fps/'lib-ron.json').read_bytes()),
                'dependency_names':sorted(dep[1] for dep in fp['deps']),
                'public_hash_descriptor_sha256':digest((fps/'lib-ron.public-api-hash').read_bytes())},
            'extern_files_at_read_time':externs, 'source_literal_path_sha256':digest(os.fsencode(next(v for v in argv if v.endswith('/ron-0.12.0/src/lib.rs')))),
            'experimental_flags':[v for v in argv if v.startswith('-Z')],
            'cargo_artifact_says_registry':pkg_artifact['package_id'].startswith('registry+'),
            'features':pkg_artifact['features']}
    return output


if __name__ == '__main__':
    print(json.dumps(main(Path.home()/'.cache/ohm-18-ty-e2e-link-20261028', sys.argv[1:]), sort_keys=True, indent=2))
