"""Reconstruct the write witness's recorded file modes in a temporary copy."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    source = Path(__file__).resolve().parent / 'first-use-writes'
    manifest = source / 'manifest.json'
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == 'c100b8276ca6a717022575647f8cd532206d3336a29bacef5ac5a68aea75db64'
    files = json.loads(manifest.read_bytes())['files']
    assert {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(files) | {'manifest.json'}
    with tempfile.TemporaryDirectory(prefix='registry-write-witness-') as temporary:
        target = Path(temporary)
        for name in sorted(set(files) | {'manifest.json'}):
            relative = Path(name)
            assert not relative.is_absolute() and '..' not in relative.parts
            original = source / relative
            assert original.is_file() and not original.is_symlink()
            copy = target / relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, copy)
            copy.chmod(0o644 if name == 'manifest.json' else files[name]['mode'])
        subprocess.run([sys.executable, '-I', '-S', '-B', str(target / 'reproduce.py')], check=True)


if __name__ == '__main__':
    main()
