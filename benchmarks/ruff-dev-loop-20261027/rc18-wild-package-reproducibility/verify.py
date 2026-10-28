"""Verify the two independent build receipts and the released ELF compatibility comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ohm-git', type=Path)
parser.add_argument('--wild-git', type=Path)
args = parser.parse_args()
here = Path(__file__).resolve().parent
read = lambda name: json.loads((here / name).read_bytes())
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = read('18.json')
wild = manifest['bundled_tools']['wild']
source = wild['source']
h7, h8 = read('h7.json'), read('h8.json')
image = 'docker.io/library/rust@sha256:' + source['builder_sha256']
digest = source['binary_sha256']
assert h7['build_rc'] == h8['status'] == 0
assert h7['image_digest'] == image and image in h8['args']
assert h7['source'] == h8['inputs']['source.tar.gz'] == wild['sha256']
assert h7['patch'] == h8['inputs']['source.patch'] == source['patch_sha256']
assert h7['base'] == source['revision'] and h7['default_features'] == ['fork', 'plugins', 'wasm', 'zstd']
assert h7['results']['wild'] == {'mode': '0o755', 'sha256': digest, 'size': 10315032}
assert h8['binary_sha256'] == digest == '9de3bdd6675f02e08d687045383c097ab0ef6027c779f153a7823153ecf8445e'
script = (here / 'build-wild.sh').read_bytes()
assert sha(script) == h8['inputs']['build-wild.sh']
assert ' '.join(h7['cargo_argv']) in script.decode().splitlines()
old, new = (read('portability.json')[k] for k in ('released', 'candidate'))
assert old['sha'] == '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
assert new['sha'] == digest
assert old['needed'] == new['needed'] == ['ld-linux-x86-64.so.2', 'libc.so.6', 'libgcc_s.so.1']
assert old['glibc'] == new['glibc'] and old['glibc'][-1] == 'GLIBC_2.34'
assert 'OS: Linux, ABI: 3.2.0' in old['notes'] and 'OS: Linux, ABI: 3.2.0' in new['notes']
if args.ohm_git:
    rev = '45eff60438eb97464dfc00eaf0e3c1b66a9fc177'
    def git(path):
        return subprocess.check_output(['git', '-C', args.ohm_git, 'show', rev + ':' + path])
    assert git('scripts/build-wild.sh') == script
    assert git('toolchains/1.99.0/18.json') == (here / '18.json').read_bytes()
    assert sha(git('release/wild-patches/' + source['patch_sha256'] + '.patch')) == source['patch_sha256']
if args.wild_git:
    cmd = ['git', '-C', args.wild_git, 'diff', '--binary', '--full-index', h7['base'], h7['commit']]
    assert sha(subprocess.check_output(cmd)) == source['patch_sha256']
print(f"Two independent links produced {digest}, {new['size']} bytes, highest referenced glibc version 2.34, matching dynamic dependencies")
