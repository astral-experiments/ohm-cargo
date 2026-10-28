"""Reconstruct the 48 Cargo outcomes from their native logs and compiler depfiles."""
from pathlib import Path
import hashlib
import json
import re
import tarfile

here = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
with tarfile.open(here / 'native.tar.gz', 'r:gz') as tar:
    members = tar.getmembers()
    assert len({m.name for m in members}) == len(members) == 422
    assert all(m.isfile() and m.size < 4 * 1024**2 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    raw = {m.name: tar.extractfile(m).read() for m in members}
index = json.loads(raw.pop('index.json'))
assert index == {k: [len(v), sha(v)] for k, v in raw.items()}
reg = json.loads(raw['protocol/registration.json'])
assert reg['commit'] == 'd0df7863460b1500b264e1c3e687b766d51a72d1'
assert reg['manifest'] == sha(raw['protocol/SHA256SUMS']) and reg['host'] == sha(raw['protocol/host.py'])
for line in raw['protocol/SHA256SUMS'].decode().splitlines():
    digest, path = line.split('  ', 1)
    assert digest == sha(raw['protocol/' + path])

def caller_launches(trace):
    lines = trace.splitlines()
    found = 0
    for line in lines:
        if b'execve(' not in line or b'/toolchains/ohm/bin/rustc", [' not in line or b'"--crate-name", "hold_direct"' not in line:
            continue
        if line.endswith(b'<unfinished ...>'):
            pid = line.split(maxsplit=1)[0]
            resumes = [n for n in lines if n.startswith(pid + b' <... execve resumed>')]
            assert len(resumes) == 1
            line = resumes[0]
        assert line.endswith(b'= 0'), line[-100:]
        found += 1
    return found

subjects = {
    'released-sources': ('0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2', '52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'),
    'candidate': ('d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde', 'ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99'),
    'explicit-probe': ('03c851e44a863bb0d2cb8c9a98df1eef33310c8f3fbc77cdbb48aee516e68400', 'ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99'),
}
values = json.loads((here / 'values.json').read_bytes())
assert values == json.loads(raw['complete.json'])
diagnostic = 'found crates (`escape_fixture` and `escape_fixture`) with colliding StableCrateId values'
assert diagnostic.encode() in raw['original-aborted/stdout'] and caller_launches(raw['original-aborted/exec']) == 1
counts = [0, 0, 0]
for arm, (cargo, driver) in subjects.items():
    identity = json.loads(raw[f'{arm}/identity.json'])
    assert (identity['cargo'], identity['driver'], identity['frontend']) == (cargo, driver, '4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f')
    assert json.loads(raw[f'{arm}/complete.json']) == values[arm]
    for kind in ('external-rlib', 'tracked-file'):
        for stamp in ('current', 'preserved'):
            case = f'{arm}/{kind}-{stamp}/'
            report = json.loads(raw[case + 'result.json'])
            assert (report['kind'], report['stamp']) == (kind, stamp)
            a, b = report['first_input'], report['changed_input']
            assert a['inode'] != b['inode'] and a['size'] == b['size'] and a['sha256'] != b['sha256']
            assert (a['mtime'] == b['mtime']) if stamp == 'preserved' else (a['mtime'] < b['mtime'])
            assert raw[case + 'observed'] == b'17' and raw[case + 'release'] == b'1'
            assert (b'wait_value!(file)' if kind == 'tracked-file' else b'escape_fixture::sampled!(wait_value)') in raw[case + 'caller.rs']
            if kind == 'tracked-file':
                assert (a['sha256'], b['sha256'], a['size']) == (sha(b'17'), sha(b'29'), 2)
            for phase in ('initial', 'repeat', 'again', 'clean'):
                base = case + phase + '/'
                row = json.loads(raw[base + 'result.json'])
                assert row == report['rows'][phase]
                trace = raw[base + 'exec']
                assert row['trace'] == sha(trace)
                physical = caller_launches(trace)
                events = [json.loads(line) for line in raw[base + 'stdout'].splitlines()]
                artifacts = [e for e in events if e['reason'] == 'compiler-artifact']
                if kind == 'external-rlib' and phase == 'initial':
                    assert events[-1] == {'reason':'build-finished','success':False} and row['exit'] == 101 and physical == 1
                    assert [e['message']['message'] for e in events if e['reason'] == 'compiler-message' and e['message']['level'] == 'error'] == [diagnostic]
                    assert row['native'] is False and row['value'] is None
                    counts[0] += 1
                else:
                    assert events[-1] == {'reason':'build-finished','success':True}
                    caller, = [e for e in artifacts if e['target']['name'] == 'hold_direct']
                    assert (caller['fresh'], all(e['fresh'] for e in artifacts), physical) == (row['fresh'], row['all_fresh'], int(not row['fresh']))
                    dep, fingerprint, native = (raw[base + f] for f in ('rustc.d', 'cargo.fingerprint', 'native'))
                    assert (sha(dep), sha(fingerprint)) == (row['dep'], row['proof'])
                    assert fingerprint[5] == 4 and fingerprint[-41:-37] == b'OBS1' and bool(fingerprint[-33]) == row['claim_complete']
                    headers = [v for v in dep.splitlines() if v.startswith(b'# ohm-observer-inputs-v1 ')]
                    assert len(headers) <= 1 and bool(headers) == row['receipt']
                    full = bytes.fromhex(headers[0].split(b' ')[3].decode()) if headers else dep
                    suffix = b'/private-input.txt' if kind == 'tracked-file' else b'/control/libescape_fixture.rlib'
                    assert [s.decode() for s in full.splitlines() if s.startswith(b'# checksum:') and s.endswith(suffix)] == row['input_checksum']
                    observed, = re.findall(rb'^sample=(\d+)$', native, re.M)
                    expected = 17 if kind == 'tracked-file' and (phase == 'initial' or (arm != 'released-sources' and phase in ('repeat', 'again'))) else 29
                    assert int(observed) == row['value'] == expected
                    if arm != 'released-sources' and kind == 'tracked-file':
                        checksum, = row['input_checksum']
                        assert checksum.startswith('# checksum:blake3=26ef00fd9555bd7513a82faef1b56c9d1efd61bc84e311e6ed902c79c40602c4 file_len:2 ') and row['claim_complete']
                        assert row['fresh'] == (phase in ('repeat','again'))
                    if phase in ('again', 'clean'):
                        replay = json.loads(raw[base + 'final-executable-replay.json'])
                        assert (replay['executable'], replay['sha256'], replay['stdout'].encode()) == (caller['executable'], row['exe'], native)
                        assert replay['size'] > 10000
                        counts[2] += 1
                    counts[1] += 1
                assert values[arm][f'{kind}-{stamp}'][phase] == [row['value'],row['fresh'],row['claim_complete']]
assert counts == [6,42,24], counts
print('48 Cargo launches, 42 successful programs, 6 compiler refusals and 24 independent final executable replays verified.')
