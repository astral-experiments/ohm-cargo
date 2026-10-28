"""Summarize command and artifact observations after the independent verifier succeeds."""
from collections import Counter
import json
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
import verify


def report():
    verified = verify.verify()
    with tarfile.open(root / 'native.tar.xz') as tar:
        def read(name):
            return json.load(tar.extractfile(name))

        output = {'commands': {}, 'native': {}, 'portable': {}, 'final': read('complete.json')}
        rosters = {}
        for mode in ('check', 'build', 'test'):
            mode_rows = {}
            for phase in ('cold', 'unchanged', 'edited', 'restored', 'final-unchanged'):
                key = f'{mode}/{phase}'
                row = read(f'{key}/result.json')
                held = read(f'{key}/retained-links.json')
                store = held['elf']
                if phase == 'cold':
                    rosters[mode] = store
                baseline = rosters[mode]
                common = store.keys() & baseline.keys()
                mode_rows[phase] = {
                    **verified[key], 'dirty_count': len(row['dirty']),
                    'noncold_dirty': Counter(row['dirty']) if phase != 'cold' else None,
                    'typed_diagnostics': Counter(d['level'] for d in row['diagnostics']),
                    'ordinary_consumers': row['ordinary'], 'retained_elf': len(store),
                    'wild_retained_after_command': sum(w['retained'] for w in held['wild']),
                    'cold_elf_same_path': len(common),
                    'cold_elf_equal_at_same_path': sum(store[f]['sha256'] == baseline[f]['sha256'] for f in common),
                }
            output['commands'][mode] = mode_rows
        retained = read('retained-storage.json')['objects']
        output['native'] = {'unique_byte_objects': len(retained), 'total_bytes': sum(retained.values())}
        originals = read('originals.json')['files']
        output['portable'] = {'members': len(originals), 'original_bytes': sum(x['original_bytes'] for x in originals.values()), 'substituted_members': sum(bool(x['replaced']) for x in originals.values())}
    return output


if __name__ == '__main__':
    print(json.dumps(report(), sort_keys=True, indent=2))
