from pathlib import Path
from hashlib import sha256
import subprocess

lab = Path(__file__).resolve().parent
repo = lab.parent / 'ohm-cargo'
stages = [
    ('base', None, 'a0c7d08c898d3fdff992f2f431dec57d2486add2'),
    ('unit', 264, '567b7d201b325e745d2dadd1553363b5c85f30d7'),
    ('warnings', 267, '4246bb695caa5f713c7234b037512c5262b6891f'),
    ('feature', 268, 'a3c13409c1d98f3e1072d86c1d968368feb90f9c'),
    ('depfile', 269, '9256d6a21da8e6c0a2ba9502999d74544ed850cd'),
    ('semver', 270, '94c95d6b8ef97b0e63e04b250bc88d1a388a31af'),
]
files = set((lab/'affected-files.txt').read_text().splitlines())
rows=['variant\tpr\thead\ttree\taffected_files\n']
previous = None
for stage, pr, head in stages:
    parent, tree = subprocess.check_output(['git','-C',repo,'show','-s','--format=%P %T',head],text=True).split()
    assert previous is None or parent == previous
    previous = head
    manifest = {name: digest for digest, name in (line.split('  ',1) for line in (lab/f'logs/{stage}.source.sha256').read_text().splitlines())}
    assert set(manifest) == files
    for name, expected in manifest.items():
        data = subprocess.check_output(['git','-C',repo,'show',f'{head}:{name}'])
        assert sha256(data).hexdigest() == expected, (name, head)
    rows.append(f'{stage}\t{pr or ""}\t{head}\t{tree}\t{len(files)}\n')
(lab/'published-identities.tsv').write_text(''.join(rows))
print(f'{len(stages)} stored stages match all {len(files)} touched source files at the published commits')
