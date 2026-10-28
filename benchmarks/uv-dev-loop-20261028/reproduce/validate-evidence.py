"""Read the evidence as a recipient, check the nested archives, and reproduce the report."""
import argparse
import csv
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
import tempfile
import zipfile


secrets = re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|'
                     rb'\b(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{24,}|'
                     rb'(?:AKIA|ASIA)[A-Z0-9]{16}|xox[baprs]-[0-9A-Za-z-]{22,}|'
                     rb'sk-(?:proj-)?[A-Za-z0-9_-]{32,})\b|'
                     rb'(?i:authorization\s*[:=]\s*["\']?(?:Bearer|Basic)\s+[A-Za-z0-9+/_=-]{20,})')


def scan(archive, parent=''):
    count = 0
    assert len(archive.namelist()) == len(set(archive.namelist()))
    for info in archive.infolist():
        name = PurePosixPath(info.filename)
        assert not name.is_absolute() and '..' not in name.parts, name
        if name.name in {'.netrc', 'credentials.toml', '.git-credentials', 'id_rsa', 'id_ed25519'}:
            raise ValueError(f'credential file in {parent}{name}')
        data = archive.read(info)
        if data.startswith(b'PK\x03\x04'):
            with zipfile.ZipFile(BytesIO(data)) as nested:
                count += scan(nested, f'{parent}{name}/')
        elif secrets.search(data):
            raise ValueError(f'credential-shaped content in {parent}{name}')
        elif any(marker in data.lower() for marker in (b'internal.api.' + b'openai.org', b'.openai.' + b'internal')):
            raise ValueError(f'private build-host identifier in {parent}{name}')
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--complete', action='store_true', help='verify the final registered cohorts and build identities')
    args = parser.parse_args()
    output = args.output.resolve()
    file = output / 'uv-ohm-benchmarks.zip'
    with zipfile.ZipFile(file) as archive, tempfile.TemporaryDirectory() as path:
        count = scan(archive)
        root = Path(path)
        archive.extractall(root)
        report = output / 'uv-ohm-results.md'
        expected = (report if report.is_file() else output / 'README.md').read_bytes()
        assert (root / 'report.md').read_bytes() == expected
        assert (root / 'samples.csv').read_bytes() == (output / 'samples.csv').read_bytes()
        with (root / 'samples.csv').open() as raw:
            data = list(csv.DictReader(raw))
        assert all(float(r['value']) >= 0 for r in data)
        for change, ep in [('unit', 'test'), ('warnings', 'check'), ('feature', 'check'),
                           ('depfile', 'build'), ('semver', 'check')]:
            for cohort, n in [('confirm', 12), ('replica', 8), ('release-like', 8)]:
                rows = [r for r in data if (r['change'], r['cohort'], r['endpoint']) == (change, cohort, ep)]
                assert len(rows) == n * 2 and len({r['pair'] for r in rows}) == n
        if args.complete or any(r['change'] == 'pgo-unit' for r in data):
            for stage, ep in [('unit','test'), ('warnings','check'), ('feature','check'), ('depfile','build'), ('semver','check'), ('std','build')]:
                for cohort, n in [('confirm', 12), ('replica', 8)]:
                    rows = [r for r in data if (r['change'], r['cohort'], r['endpoint']) == ('pgo-' + stage, cohort, ep)]
                    assert len(rows) == n * 2 and len({r['pair'] for r in rows}) == n
        role = root / 'components/edited-roles/identical'
        if (role / 'summary.md').is_file():
            original = (role / 'summary.md').read_bytes()
            subprocess.run([sys.executable, '-B', role / 'summarize.py'], check=True)
            assert (role / 'summary.md').read_bytes() == original
        wall = root / 'components/eight-wall'
        if args.complete:
            def read(path):
                return json.loads((root / path).read_text())
            for doc in ('README.md', 'REPRODUCTION.md', 'reproduce/repro-pgo.md', 'reproduce/first-five.md',
                        'reproduce/eight-wall/reproduce.md', 'components/eight-roles/reproduce.md',
                        'components/edited-roles/INDEX.md', 'components/wild-prefix/README.md'):
                for link in re.findall(r'\]\(([^\s)]+)\)', (root / doc).read_text()):
                    if link.startswith(('http:', 'https:', '#', 'mailto:')):
                        continue
                    path = posixpath.normpath(posixpath.join(posixpath.dirname(doc), link.split('#')[0]))
                    assert path == 'uv-ohm-benchmarks.zip' or (root / path).exists(), (doc, path)
            assert (wall / 'results.json').is_file()
            wall_audit = read('components/eight-wall/complete-audit.json')
            assert set(wall_audit) == {'initial', 'replica'}
            for group, receipt in wall_audit.items():
                directory = wall / 'results' / group
                assert receipt['arms'] == 48 and receipt['test_executable_count'] == 72
                assert receipt['visible_target_vacant'] and receipt['original_slots_restored']
                assert sha256((directory / 'pairs.csv').read_bytes()).hexdigest() == receipt['raw_pairs_sha256']
                assert len(receipt['native_traces']) == 4
                for label, trace in receipt['native_traces'].items():
                    assert len(list((directory / label).glob('exec.[0-9]*'))) == trace['per_pid_trace_files']
                    assert sorted(trace['actual_execs'].values()) == [1, 5, 6]
            roles = root / 'components/eight-roles'
            role_result = json.loads((roles / 'summary.json').read_text())
            verification = json.loads(subprocess.check_output([sys.executable, '-B', roles / 'verify.py'], cwd=roles))
            assert verification['joint_qualification'] == role_result['qualified']
            for name, audited in verification['cohorts'].items():
                assert audited['state'] == role_result['cohorts'][name]['state']
            audit = read('components/edited-roles/complete-audit.json')
            receipts = [r for group in audit.values() for r in group.values()]
            assert sum(r['held_out_arm_observations'] for r in receipts) == 96
            assert sum(len(r['native_per_pid_receipts']) for r in receipts) == 12
            for group, endpoints in audit.items():
                for ep, receipt in endpoints.items():
                    raw = root / 'components/edited-roles' / group / 'results' / ep / 'samples.csv'
                    assert receipt['visible_target_vacant'] and sha256(raw.read_bytes()).hexdigest() == receipt['raw_csv_sha256']
            for kind, directory in [('wall', wall), ('roles', root / 'components/edited-roles')]:
                names = ('order-sensitivity-results.json', 'order-sensitivity-results.md')
                saved = [(directory / name).read_bytes() for name in names]
                subprocess.run([sys.executable, '-B', wall / 'order_sensitivity.py', kind, directory], check=True)
                assert saved == [(directory / name).read_bytes() for name in names]
            checks = read('verification/ci-snapshot.json')
            assert len(checks['drafts']) == 8 and all(p['isDraft'] and p['state'] == 'OPEN' for p in checks['drafts'])
            for key in ('wild_native', 'wild_prefix_native'):
                assert checks[key]['conclusion'] == 'success' and len(checks[key]['jobs']) == 3
            arms = read('profile-build/pgo-confirmation-v2/audit.json')['arms']
            plan = read('reproduce/pgo-steps/registration.json')
            for stage in plan['stages']:
                name = stage['name']
                if name == 'std':
                    continue
                folder = Path('profile-build/intermediates/records') / name
                arm = read(folder / 'ready.json')
                assert arm['pull_request'] == stage['pr'] and arm['training_commands_verified'] == 24
                assert sha256((root / folder / 'merged.profdata').read_bytes()).hexdigest() == arm['profdata_sha256']
                arms[name] = arm
            with (root / 'profile-build/intermediates/driver-index.tsv').open() as index:
                drivers = list(csv.DictReader(index, delimiter='\t'))
            assert {r['arm'] for r in drivers} == set(arms) and len(drivers) == 7
            for r in drivers:
                assert r['binary_sha256'] == arms[r['arm']]['cargo_sha256']
                assert r['profile_sha256'] == arms[r['arm']]['profdata_sha256']
                assert r['retained_raw_profiles'] == r['verified_training_commands'] == '24'
            assert len({r['profile_sha256'] for r in drivers}) == 7
            assert len({r['std_rlib_sha256'] for r in drivers if r['arm'] != 'guard-stack'}) == 1
            for stage in plan['stages']:
                for run, key in [('confirm', 'primary'), ('replica', 'repeat')]:
                    protocol = read(f"runs/pgo-{stage['name']}-{run}/protocol.json")
                    assert protocol['seed'] == stage[key + '_seed']
                    assert protocol['cargo_sha256'] == {'base': arms[stage['base']]['cargo_sha256'],
                                                        'candidate': arms[stage['head']]['cargo_sha256']}
            ordinary_argv = {'check': ['check'], 'build': ['build'], 'test': ['test', '--no-run']}
            for run in ('pgo-ordinary', 'distributed-control'):
                assert read(f'runs/{run}/protocol.json')['argv'] == ordinary_argv
                for ep in ordinary_argv:
                    with (root / 'runs' / run / 'pairs.csv').open() as stream:
                        assert sum(r['endpoint'] == ep for r in csv.DictReader(stream)) == 16
            for ep in ('check', 'build', 'test'):
                d = root / 'components/edited-roles/replica'
                assert (d / 'eligibility' / (ep + '.json')).is_file()
                if json.loads((d / 'eligibility' / (ep + '.json')).read_text())['passed_initial_gate']:
                    result = d / 'results' / ep
                    assert (result / 'samples.csv').is_file() or list(result.glob('rejected-*.json'))
        if (wall / 'results.json').is_file():
            original = [(wall / name).read_bytes() for name in ('results.json', 'summary.md')]
            subprocess.run([sys.executable, '-B', wall / 'summarize.py'], check=True)
            assert [(wall / name).read_bytes() for name in ('results.json', 'summary.md')] == original
            for cohort in ('initial', 'replica'):
                rows = [r for r in data if (r['change'], r['cohort'], r['endpoint']) == ('eight-combined', cohort, 'test')]
                assert len(rows) == 48 and len({r['pair'] for r in rows}) == 24
        subprocess.run([sys.executable, '-B', root / 'reproduce/render_results.py', '--runs', root / 'runs',
                        '--output', root / 'rerendered.md'], check=True)
        assert (root / 'rerendered.md').read_bytes() == expected
    names = ['samples.csv', 'uv-ohm-benchmarks.zip']
    manifest = ''.join(f'{sha256((output / n).read_bytes()).hexdigest()}  {n}\n' for n in names)
    path = output / 'SHA256SUMS'
    if path.is_file():
        assert path.read_text() == manifest, 'published sample or archive digest changed'
    else:
        path.write_text(manifest)
    print(f'{len(data)} ordered observations, {count} archive entries checked, report reproduced byte-for-byte.')


if __name__ == '__main__':
    main()
