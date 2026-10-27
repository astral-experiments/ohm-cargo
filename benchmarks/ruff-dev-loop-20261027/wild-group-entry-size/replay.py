"""Measure Wild's .rodata header with identical inputs under two worker budgets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SHIPPED = '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data):
    assert data.startswith(b'\x7fELF\x02\x01')
    table = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 58)
    assert stride == 64
    offset = struct.unpack_from('<Q', data, table + stride * names_index + 24)[0]
    sections = {}
    for i in range(count):
        h = table + i * stride
        name = offset + struct.unpack_from('<I', data, h)[0]
        end = data.index(b'\x00', name)
        sections[data[name:end].decode()] = h
    rodata = sections['.rodata']
    note_offset, note_size = struct.unpack_from('<QQ', data, sections['.note.gnu.build-id'] + 24)
    namesz, descsz, kind = struct.unpack_from('<III', data, note_offset)
    assert (namesz, descsz, kind, note_size) == (4, 32, 3, 48)
    assert data[note_offset + 12:note_offset + 16] == b'GNU\x00'
    allowed = set(range(note_offset + 16, note_offset + 16 + descsz)) | set(range(rodata + 56, rodata + 64))
    return struct.unpack_from('<Q', data, rodata + 56)[0], allowed


def run(linker):
    env = {k: v for k, v in os.environ.items() if not k.startswith('WILD_')}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        objects = [root / (name + '.o') for name in ('start', 'ordinary', 'eight')]
        for obj in objects:
            subprocess.run(['as', HERE / (obj.stem + '.s'), '-o', obj], check=True)
        rows, images = [], {}
        for jobs in (1, 4):
            for group in (None, 1, 100):
                cmd = [linker, f'--threads={jobs}', '--no-fork', '-m', 'elf_x86_64', '--build-id', '-e', '_start', '--gc-sections', '-o', 'image', *objects]
                extra = {} if group is None else {'WILD_FILES_PER_GROUP': str(group)}
                subprocess.run(cmd, cwd=root, env=env | extra, check=True)
                image = root / 'image'
                assert subprocess.run([image]).returncode == 42
                data = image.read_bytes()
                entsize, allowed = inspect(data)
                images.setdefault(digest(data), (data, allowed))
                rows.append({'workers': jobs, 'files_per_group': group, 'entsize': entsize, 'elf_sha256': digest(data), 'program_exit': 42})
        baseline, allowed = next(iter(images.values()))
        for data, other_allowed in images.values():
            assert len(data) == len(baseline) and allowed == other_allowed
            assert {pos for pos, (old, new) in enumerate(zip(baseline, data)) if old != new} <= allowed
        subject = digest(linker.read_bytes())
        if subject == SHIPPED:
            assert [r['entsize'] for r in rows] == [0, 8, 0, 8, 8, 8] and len(images) == 2
        return {'linker_sha256': subject, 'object_sha256': {p.name: digest(p.read_bytes()) for p in objects}, 'observations': rows}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('linker', type=Path)
    print(json.dumps(run(cli.parse_args().linker.resolve()), indent=2))
