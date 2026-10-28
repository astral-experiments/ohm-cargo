"""Verify the manifest, CI heads, stock linker selection and Ruff qualification counts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ohm-git', type=Path)
parser.add_argument('--rust-git', type=Path)
args = parser.parse_args()
read = lambda name: json.loads((here / name).read_bytes())
sha = lambda data: hashlib.sha256(data).hexdigest()
old, new = read('17.json'), read('18.json')
assert new['status'] == 'pinned' and new['release']['toolchain_name'] == 'ohm-1.99.0-18'
assert old['bundled_tools'] == new['bundled_tools'] == {'wild': {'version': '0.11.0', 'sha256': '25012a78de164686f552b7703b5d0223adab4829c79cd1fb351108221d61c7d8'}}
assert {k for k in new['sources'] if old['sources'][k] != new['sources'][k]} == {'cargo', 'rust'}
assert sha((here / '18.json').read_bytes()) == 'a5e31712c01e57621d2cfdd29e91aa3b2292394253a2eb557618f851ab401b61'
rust = new['sources']['rust']['revision']
cargo = new['sources']['cargo']['revision']
coordinator = '2b25f863e3b7433a7103de4c315b8cb150413ecc'
checks = read('checks.json')
prs = {pr['url']: pr for pr in checks['pull_requests']}
assert len(prs) == 9
assert prs['https://github.com/astral-sh/ohm/pull/198']['headRefOid'] == coordinator
assert prs['https://github.com/astral-sh/ohm-rust/pull/246']['headRefOid'] == rust
assert prs['https://github.com/astral-sh/ohm-cargo/pull/262']['headRefOid'] == cargo
for url, pr in prs.items():
    checks_ = {c['name']: (c['status'], c['conclusion']) for c in pr['checks']}
    if '/ohm-cargo/' in url:
        assert checks_.pop('Clippy APFS replay') == ('COMPLETED', 'SKIPPED')
        assert len(checks_) == 8 and {'Cargo tests (depot-ubuntu-24.04-16)', 'Cargo tests (depot-macos-15)'} <= set(checks_)
    elif '/ohm-rust/' in url:
        assert set(checks_) == {'Compiler and regression tests', 'Compiler and regression tests (macOS)', 'Formatting and tidy'}
    else:
        assert set(checks_) == {'manifest', 'lint', 'all required jobs passed'}
    assert all(v == ('COMPLETED', 'SUCCESS') for v in checks_.values()), url
assert sum(c['conclusion'] == 'SUCCESS' for pr in prs.values() for c in pr['checks']) == 42

counts = read('ruff-counts.json')
assert set(counts) == {'check', 'build', 'test'}
for mode, total in [('check', 520), ('build', 501), ('test', 619)]:
    phases = counts[mode]
    assert set(phases) == {'cold', 'unchanged', 'edited', 'restored', 'final-unchanged'}
    assert all(r['reported'] == total for r in phases.values()) and phases['cold']['fresh'] == 0
    for phase in ('unchanged', 'final-unchanged'):
        r = phases[phase]
        assert (r['full'], r['link-only'], r['wild']) == ((1, 50, 50) if mode == 'test' else (0, 0, 0))
    assert 0 < phases['edited']['fresh'] < total and phases['restored']['fresh'] == phases['edited']['fresh']

darwin = read('macos-native.json')
assert darwin['status'] == 'completed' and darwin['conclusion'] == 'success'
assert darwin['id'] == 40730837103 and darwin['run_attempt'] == 1
assert darwin['head_sha'] == 'a34f48d944280a5de0bcf8a49c3d0cdb24082fd8'
assert darwin['compiler_tree'] == '47e23eb4bab742e271ca9a3cf1bbd583d5b4a640'
assert darwin['cargo_gitlink'] == cargo
assert darwin['artifact']['digest'] == 'sha256:0c40fb701af66465108e12da0db851c7c0593d68536c184529b7af2e147a14e0'
expected = {'original': '17,17', 'edited': '29,29', 'repeat': '29,29',
            'edited-empty': '29,29', 'restored': '17,17', 'restored-empty': '17,17'}
assert darwin['values']['fixed'] == expected
assert darwin['values']['stock'] == dict(expected, edited='17,17', repeat='17,17')
assert 'Darwin arm64' in darwin['host']
for arm in darwin['artifacts_replayed'].values():
    assert arm['commands'] == 20 and arm['native_runs'] == 6
    code = arm['producer_mach_o_text_sha256']
    assert code['original'] == code['restored'] != code['edited']

evidence = read('evidence.json')
assert len(evidence) == 9
for name, item in evidence.items():
    assert len(bytes.fromhex(item['commit'])) == 20 and len(bytes.fromhex(item['sha256sums'])) == 32
    assert item['url'] == f"https://github.com/astral-sh/ohm-cargo/tree/{item['commit']}/benchmarks/ruff-dev-loop-20261027/{name}"
assert evidence['native-proc-macro-darwin-ci-results']['sha256sums'] == '7531cd7a14f649ab90f9b6e7067325325f711a7f090f0350cbdd9343507649c7'

if args.ohm_git:
    for rev in ('17', '18'):
        blob = subprocess.check_output(['git', '-C', args.ohm_git, 'show', coordinator + ':toolchains/1.99.0/' + rev + '.json'])
        assert blob == (here / (rev + '.json')).read_bytes()
if args.rust_git:
    revparse = lambda ref: subprocess.check_output(['git', '-C', args.rust_git, 'rev-parse', ref], text=True).strip()
    assert revparse(rust + ':src/tools/cargo') == revparse(darwin['head_sha'] + ':src/tools/cargo') == cargo
    assert revparse(rust + ':compiler') == revparse(darwin['head_sha'] + ':compiler') == darwin['compiler_tree']
print(f'Qualified Cargo {cargo[:10]} and Rust {rust[:10]}, 9 PR heads, 15 Ruff commands, and the macOS native-macro replay.')
