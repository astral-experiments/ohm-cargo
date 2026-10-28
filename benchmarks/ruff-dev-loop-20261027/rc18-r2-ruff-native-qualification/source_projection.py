"""Identify the release Cargo gitlink, Rust compiler tree and physical PGO/BOLT inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

root = Path(__file__).resolve().parent
rust = Path('/home/dev-user/code/oss/ohm-rust-rc18-cargo-pin-20261028')
cargo = Path('/home/dev-user/code/oss/ohm-cargo-rc18-qualified-20261028')
release = '9828b82f475f18bf9077ee25f36de43d4fec8277'
earlier = 'fb1389e92fd0563c36075108cb00db65642e2118'
archive = root / 'r2-build-original-receipts.tar.gz'


def rev(repo, name):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', repo, 'rev-parse', name], text=True).strip()


with tarfile.open(archive) as tar:
    source = json.load(tar.extractfile('source-commit.json'))
    build = json.load(tar.extractfile('receipt.json'))
    assert source == build['source_identity']
    roots = {m.name: hashlib.sha256(tar.extractfile(m).read()).hexdigest() for m in tar if m.isfile()}

compiler_tree = rev(rust, release + ':compiler')
assert compiler_tree == rev(rust, source['selected_commit'] + ':compiler') == source['selected_compiler_tree']
assert compiler_tree == rev(rust, earlier + ':compiler')
changed = subprocess.check_output(['git', '--no-optional-locks', '-C', rust, 'diff', '--name-only', earlier, release], text=True).splitlines()
assert changed == ['tests/run-make/public-api-hash-artifact/rmake.rs']
linked_cargo = rev(rust, release + ':src/tools/cargo')
assert linked_cargo == '7181bfa6256f94da142f80fd6af09cee02ec2c78'
assert linked_cargo == rev(rust, earlier + ':src/tools/cargo')
assert rev(cargo, linked_cargo + '^{tree}') == '5386201eedb3970d3cc74521f12bd644cdf33396'
print(json.dumps({'rust_release_commit':release, 'earlier_release_commit':earlier, 'release_tree_changes':changed,
    'compiler_build_commit':source['selected_commit'],
    'compiler_tree_in_both':compiler_tree, 'cargo_gitlink':linked_cargo,
    'cargo_tree':rev(cargo, linked_cargo + '^{tree}'), 'build_original_archive':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'driver_build_files':roots, 'candidate_prebolt':build['candidate_prebolt'], 'candidate_postbolt':build['candidate_postbolt'],
    'frontend':build['frontend'], 'cargo_binary':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8',
    'original_packaged_linux_wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}, sort_keys=True, indent=2))
