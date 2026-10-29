from pathlib import Path
import hashlib
import json
import sys
import tarfile

p = Path(__file__).resolve().parent
def digest(data):
    return hashlib.sha256(data).hexdigest()
def encode(data):
    return (json.dumps(data, indent=2) + '\n').encode()

d = json.loads((p/'verified-native.json').read_bytes())
h = d['release']['tools']
assert d['after']['tools'] == {k: v for k, v in h.items() if k != 'archive'}
assert d['release']['adaptor'] == digest((p/'reproduce.py').read_bytes())
assert min(d['release']['storage_before'],d['after']['storage_after']) > d['release']['host_guard']
assert d['raw_log_files'] == sum(len(q['raw']) for q in d['rows']) == 595
assert d['native_inputs']['cargo_sha256'] == h['cargo'] and d['native_inputs']['rustc_sha256'] == h['rustc']
assert 'ohm-1.99.0-17' in d['native_inputs']['rustc']
assert len(d['rows']) == len(d['exec_verification']) == d['terminal']['visits'] == 17
phases = ['start', 'unchanged', 'switch', 'switch-repeat', 'evict-cargo-fingerprint', 'restore', 'restore-repeat']
expected = [(a,b) for a in ['implicit','explicit'] for b in phases] + [('empty', b) for b in ['no','repeat','recover']]
assert expected == [(q['arm'], q['label']) for q in d['rows']]
assert len({q['elf'] for q in d['rows'] if q['exit'] == 0}) == 1
for q, t in zip(d['rows'], d['exec_verification']):
    phase = q['label']
    assert t['key'] == q['arm'] + '-' + phase
    assert len(t['cargo']) == 1 and t['cargo'][0][0] == h['cargo']
    rust = t['actual_rustc']
    root = [c for c in rust if c['unit'] == 'consumer']
    wild = t['actual_linkers']
    assert len(root) == q['root_rustc']
    assert [c['emit_rlink'] for c in root] == q['root_emit']
    assert all(c['sha256'] == h['rustc'] for c in rust) and all(w['sha256'] == h['wild'] for w in wild)
    if phase in ['no', 'repeat', 'evict-cargo-fingerprint']:
        assert q['exit'] == 101 and q['runtime'] is None and not q['elf'] and q['root_emit'] == [False]
        assert q['errors'] == [['link recipe was not requested', [['consumer/src/main.rs', 1, 28]]]]
    else:
        assert q['exit'] == 0 and q['runtime'] == '17' and not q['errors']
    if phase in ['switch', 'switch-repeat', 'restore-repeat', 'unchanged']:
        assert not rust and not wild and not q['dirty']
    if phase in ['start','restore','recover']:
        assert q['root_emit'] == [True] and sum(w['target']=='consumer' for w in wild) == 1
stopped = json.loads((p/'first-attempt.json').read_bytes())
if len(sys.argv) == 2:
    archive = Path(sys.argv[1]); assert digest(archive.read_bytes()) == stopped['raw_archive_sha256']
    with tarfile.open(archive, 'r:gz') as pack:
        members = {m.name: pack.extractfile(m).read() for m in pack if m.isfile()}
    assert len(members) == stopped['total_original_files']
    assert members['first/exit'].strip() == b'1' and digest(members['first/stderr']) == stopped['stderr_sha256']
    assert b'subprocess.TimeoutExpired' in members['first/stderr'] and not 'first/study/rows.json' in members
    assert members['terminal/exit'].strip() == b'0'
    for n, name in [('inputs','native_inputs'),('rows','rows')]:
        raw = members['terminal/study/'+n+'.json']; assert json.loads(raw) == d[name] and digest(raw) == d['terminal'][n]
    assert digest(members['terminal/study/terminal.json']) == d['terminal_sha256']
    for q in d['rows']:
        base = 'terminal/study/logs/' + q['arm'] + '-' + q['label'] + '/'
        raw = {k[len(base):]:v for k,v in members.items() if k.startswith(base)}
        assert {k:digest(v) for k,v in raw.items()} == q['raw']
        msg = [json.loads(line) for line in raw['stdout'].splitlines()]
        assert msg[-1]['success'] == (q['exit'] == 0) and msg[-1]['reason'] == 'build-finished'
        assert [w['target']['name'] for w in msg if w['reason']=='compiler-artifact' and not w['fresh']] == q['dirty']
        if q['evicted_short_fingerprint']:
            saved = members['terminal/study/escrow/'+q['arm']+'-'+q['label']]
            assert len(saved) == 16 and digest(saved) == q['evicted_short_fingerprint'][1]
    for n,v in d['native_inputs']['sources'].items(): assert digest(members['terminal/study/source/'+n]) == v
print('OK: 17 commands, four stale successes, four matched errors, two restorations and one recovery')
