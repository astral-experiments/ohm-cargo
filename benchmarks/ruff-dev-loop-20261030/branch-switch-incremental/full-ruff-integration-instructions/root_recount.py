"""Recount the Ruff command, counter, test verdict and disk ledger from each original ZIP."""
import argparse
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent
PILOT = ROOT.parent / 'ohm-ruff-integration-kernel-f-pilot-reader-20261031-v1'
PHASES = ('cold-A', 'first-B', 'return-A', 'return-B', 'unchanged-B', 'invalid', 'repair')
ARMS = ('Foff', 'Fon')
GROUPS = {p: (p,) for p in PHASES} | {
    'return_sum': ('return-A', 'return-B'), 'first_switch_and_return_A': ('first-B', 'return-A'),
    'cold_through_return_B': PHASES[:4], 'all_five_successful': PHASES[:5], 'all_seven': PHASES,
}
COMMAND = ['cargo', '+ohm', 'test', '-p', 'ruff', '--test', 'integration_test', '--no-run',
           '--locked', '--offline', '-j4', '--message-format=json']
REVS = {'A': 'b5dba861cc38e3f7fb4524c9ceba3e01a474ea13', 'B': '7b13f01ba1569887a25670820764b24c206da8e5'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(z, name):
    if not isinstance(z, ZipFile):
        return z.payload(name)
    raw = z.read(name)
    return gzip.decompress(raw) if name.endswith('.gz') else raw


def record(z, name):
    return json.loads(read(z, name))


def recount_bytes(z, prefix, expected):
    files = record(z, prefix + 'path-inodes.json.gz')
    inodes = {}
    for dev, ino, _, _, blocks, _ in files.values():
        key = (dev, ino)
        assert inodes.setdefault(key, blocks) == blocks
    allocated = sum(inodes.values()) * 512
    storage = record(z, prefix + 'storage.json')
    readers = record(z, prefix + 'allocation-readers.json')
    assert allocated == expected == storage['allocated'] == readers['du_bytes'] == readers['find_bytes']
    assert len(inodes) == storage['all_inodes'] == readers['find_inodes'] and len(files) == storage['all_names']
    return allocated


def check_oracles(z, prefix, branch, reference):
    listing = read(z, prefix + 'libtest-list.stdout.gz').splitlines()
    output = read(z, prefix + 'libtest-full.stdout.gz').splitlines()
    names = {s[:-6] for s in listing if s.endswith(b': test')}
    passed = [m[1] for line in output if (m := re.fullmatch(rb'test (.+) \.\.\. ok', line))]
    assert len(names) == len(passed) == 96 and set(passed) == names
    assert any(line.startswith(b'test result: ok. 96 passed; 0 failed; 0 ignored;') for line in output)
    for role in ('libtest-list', 'libtest-full'):
        cmd = record(z, prefix + role + '.json')
        assert cmd['exit'] == 0
        assert sha(read(z, prefix + role + '.stdout.gz')) == cmd['stdout']
        assert sha(read(z, prefix + role + '.stderr.gz')) == cmd['stderr']
    suite = record(z, prefix + 'libtest.json')
    children = suite['children']
    assert suite['total'] == suite['passed'] == 96 and set(children) == {'check_input_from_argfile', 'missing_argfile_reports_error'}
    for test, child in children.items():
        launches = read(z, prefix + test + '.exec.gz').decode().splitlines()
        pid = child['ruff_pid']
        assert pid != child['harness_pid'] and child['argv'][0] == child['ruff_path']
        assert any(line.startswith(f'{pid} execve("{child["ruff_path"]}",') and line.endswith(' = 0') for line in launches)
    size = 64 if branch == 'A' else 56
    assert read(z, prefix + 'reader-run.stdout.gz') == f'Expr={size} valid=1 rejected\n'.encode()
    for probed in (56, 64):
        name = prefix + f'layout-{probed}'
        cmd = record(z, name + '.json.gz')
        rc = int(probed != size)
        assert cmd['exit'] == cmd['expected'] == rc
        stderr = read(z, name + '.stderr.gz')
        assert sha(stderr) == cmd['stderr_sha256']
        codes = [(json.loads(line).get('code') or {}).get('code') for line in stderr.splitlines()]
        assert ('E0308' in codes) == bool(rc)
    assert set(reference) == {'cli', 'harness', 'reader'}
    if isinstance(z, ZipFile):
        assert all('native-bodies/' + h + '.zst' in z.NameToInfo for h in reference.values())
    else:
        assert all(z.has_verified_body(h) for h in reference.values())
    return sha(b'\n'.join(sorted(names)) + b'\n')


def recount(z, pos, run, head):
    if isinstance(z, ZipFile):
        assert len(z.namelist()) == len(set(z.namelist()))
    en = record(z, 'enrollment.json')
    order = list(ARMS if int(pos) % 2 else reversed(ARMS))
    assert (en['run'], en['head'], en['attempt'], en['position'], en['order'], en['argv']) == (run, head, 1, pos, order, COMMAND)
    assert sha(read(z, 'PLAN.md')) == en['plan']
    end = record(z, 'complete.json')
    assert end['qualified'] and end['boot'] == en['boot'] and end['order'] == order
    counts, evidence, names = {}, {}, set()
    for arm in order:
        counts[arm], evidence[arm] = {}, {}
        empty = {}
        for branch in REVS:
            prefix = f'clean/{arm}/{branch}/'
            v = record(z, prefix + 'visit.json')
            assert (v['state'], v['arm'], v['typed'], v['distinct_dirty'], v['full'], v['wild'], v['link_only'], v['code']) == (branch, arm, 390, 390, 394, 72, 0, 0)
            assert record(z, prefix + 'source.json')['commit'] == REVS[branch]
            empty[branch] = v['products']
            names.add(check_oracles(z, prefix, branch, empty[branch]))
        for phase in PHASES:
            prefix = f'history/{arm}/{phase}/'
            v = record(z, prefix + 'visit.json')
            clock = record(z, prefix + 'clock.json')
            window = record(z, prefix + 'window.json')
            cmd = record(z, prefix + 'cargo.json.gz')
            src = record(z, prefix + 'source.json')
            failed = phase == 'invalid'
            code = 101 if failed else 0
            branch = 'A' if phase in ('cold-A', 'return-A') else 'B'
            assert src['commit'] == REVS[branch] and (v['arm'], v['phase'], v['branch']) == (arm, phase, branch)
            assert cmd['expected'] == cmd['exit'] == v['exit'] == clock['code'] == code
            assert cmd['argv'] == COMMAND and cmd['observer_argv'][-len(COMMAND):] == COMMAND
            stdout = read(z, prefix + 'cargo.stdout.gz')
            assert sha(stdout) == cmd['stdout_sha256'] and sha(read(z, prefix + 'cargo.stderr.gz')) == cmd['stderr_sha256']
            events = [json.loads(s) for s in stdout.splitlines()]
            assert events[-1] == {'reason': 'build-finished', 'success': not failed}
            assert clock['event_errno'] == 0 and 0 < clock['running'] <= clock['enabled'] and 1000 * clock['running'] >= 995 * clock['enabled']
            assert window['before_cargo'] <= clock['start'] < clock['stop'] == window['clock_stop'] <= window['before_any_oracle'] <= window['after_all_oracles']
            assert clock['instructions'] == v['instructions'] > 0
            if failed:
                errors = [m['message'] for m in events if m['reason'] == 'compiler-message' and (m['message'].get('code') or {}).get('code') == 'E0308']
                assert any(s['is_primary'] and s['file_name'] == 'crates/ruff_python_parser/src/lib.rs' and s['line_start'] == s['line_end'] == 626 for e in errors for s in e['spans'])
            else:
                units = [m for m in events if m['reason'] == 'compiler-artifact']
                assert len(units) == v['typed'] == 390 and sum(not u['fresh'] for u in units) == v['dirty']
                assert v['elf'] == empty[branch] and v['passed'] == 96
                names.add(check_oracles(z, prefix, branch, empty[branch]))
            counts[arm][phase] = clock['instructions']
            evidence[arm][phase] = {'instructions': clock['instructions'], 'allocated': recount_bytes(z, prefix, v['allocated']),
                                    'typed': v['typed'], 'dirty': v['dirty'], 'exit': code}
    assert len(names) == 1
    pairs = {name: [sum(counts[arm][p] for p in phases) for arm in ARMS] for name, phases in GROUPS.items()}
    return {'boot': en['boot'], 'plan': en['plan'], 'order': order, 'suite_names_sha': names.pop(), 'phases': evidence, 'pairs': pairs}


def population(rows):
    assert len(rows) == 12 and len({r['boot'] for r in rows.values()}) == 12
    assert len({r['suite_names_sha'] for r in rows.values()}) == len({r['plan'] for r in rows.values()}) == 1
    result = {}
    for name in GROUPS:
        values = sorted(Fraction(*r['pairs'][name]) for r in rows.values())
        result[name] = {key: [v.numerator, v.denominator] for key, v in
                        [('rank2', values[1]), ('rank11', values[10]), ('median', (values[5] + values[6]) / 2)]}
        result[name]['distinct'] = len(set(values))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('pilot', 'confirmation'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    is_pilot = args.mode == 'pilot'
    spec = json.loads((ROOT / 'enrollment.json').read_bytes())
    positions = ('01', '02') if is_pilot else tuple(sorted(spec['positions']))
    rows = {}
    for pos in positions:
        if is_pilot:
            ref = json.loads((PILOT / f'position-{pos}.json').read_bytes())
            path = Path(ref['complete_original_path'])
        else:
            ref = json.loads((ROOT / 'results' / f'receipt-{pos}.json').read_bytes())
            assert ref['run'] == spec['run'] and ref['head'] == spec['head'] and ref['job'] == spec['positions'][pos]
            path = Path(spec['original_store']) / f'{ref["run"]}-{ref["archive"]["id"]}.zip'
        assert ref['conclusion'] == 'success' and ref['position'] == pos
        assert path.is_file() and not path.is_symlink() and path.stat().st_size == ref['archive']['size_in_bytes']
        with path.open('rb') as f:
            assert 'sha256:' + hashlib.file_digest(f, 'sha256').hexdigest() == ref['archive']['digest']
        with ZipFile(path) as archive:
            rows[pos] = recount(archive, pos, ref['run'], ref['head'])
        rows[pos]['original'] = ref['archive']['digest']
    result = {'mode': args.mode, 'positions': rows}
    if not is_pilot:
        assert all(r['plan'] == spec['plan'] for r in rows.values())
        prior = json.loads((Path(spec['source']) / 'scripts/ruff-integration-pmu/excluded-boots.json').read_bytes())
        assert len(prior) == len(set(prior)) == 41 and not {r['boot'] for r in rows.values()}.intersection(prior)
        result['distribution'] = population(rows)
    payload = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    if args.output.exists():
        assert args.output.read_bytes() == payload
    else:
        args.output.write_bytes(payload)
    print(args.mode, len(rows), len(rows) * len(PHASES) * len(ARMS), sha(payload))


if __name__ == '__main__':
    main()
