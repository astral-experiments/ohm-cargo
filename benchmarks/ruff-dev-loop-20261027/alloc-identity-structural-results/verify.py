"""Verify all producer and caller receipts. Requires Python 3.11 and GNU binutils."""
from itertools import product
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile

folder = Path(__file__).resolve().parent
def read(f):
    return json.loads(f.read_bytes())

def digest(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()

def status(d):
    return read(d/'status.json')['returncode']

def checked_wire(d, temp):
    blob = subprocess.check_output(['ar', 'p', str(d/'libprobe.rlib'), 'lib.rmeta'])
    (temp/'member').write_bytes(blob)
    subprocess.run(['objcopy', '--dump-section', '.rmeta='+str(temp/'raw'), str(temp/'member'), str(temp/'copy')], check=True)
    assert (temp/'raw').read_bytes() == (d/'libprobe.rmeta').read_bytes()

def verify(root, temp):
    labels = ('train','warm','empty','second-empty','restore','clean-original')
    edited = ('warm','empty','second-empty')
    valid = failures = callers = 0
    results = {}
    for arm in ('parent','candidate'):
        base = root/(arm+'-evidence')
        subject = read(base/'done.json')
        handoff = read(folder/'matched-images.json')
        assert subject['driver'] == handoff['parent' if arm=='parent' else 'candidate_postbolt']
        assert subject['rustc'] == handoff['frontend'] and subject['timed_observations'] == 0
        rows = read(base/'results.json')
        for case in ('literal','separate','separate-offset'):
            for mode, label in product(('plain','stats'), labels):
                row = rows[case+'/'+mode][label]
                block = base/case/mode/'evidence'/label
                args = read(block/'compile/argv.json')
                assert args[:2] == ['rustc','+ohm'] and '--emit=link,metadata' in args
                assert ('-Zmeta-stats' in args) == (mode == 'stats')
                assert row['source_sha256'] == digest(block/'probe.rs')
                assert row['value'] == (8 if label in edited else 7)
                rc = status(block/'compile')
                assert row['returncode'] == rc
                stderr = (block/'compile/stderr').read_bytes()
                if case=='separate-offset' and label in edited:
                    assert rc == 1 and not (block/'libprobe.rmeta').exists() and not (block/'libprobe.rlib').exists()
                    diagnostics = [json.loads(line) for line in stderr.splitlines() if line.startswith(b'{')]
                    error, = [d for d in diagnostics if (d.get('code') or {}).get('code') == 'E0080']
                    assert error['message'] == row['error_message'] and 'same allocation' in error['message']
                    failures += 1
                    continue
                assert rc == 0 and status(block/'header') == 0
                for name in ('libprobe.rmeta','libprobe.rlib'):
                    assert digest(block/name) == row[name]
                checked_wire(block, temp)
                assert ('private hash '+row['private']).encode() in (block/'header/stdout').read_bytes()
                assert row['libprobe.rmeta'] == rows[case+'/plain'][label]['libprobe.rmeta']
                if mode=='stats' and label in edited:
                    count = int(re.search(rb'meta-stats\s+interpret-alloc-index\s+([0-9]+)', stderr)[1])
                    assert row['stats']['interpret-alloc-index'] == count
                    expected = 104 if arm=='parent' and label=='warm' else 52
                    assert count == (expected if case=='literal' else 17)
                valid += 1
            if case=='separate-offset':
                continue
            positive = rows[case+'/plain']
            assert positive['empty']['libprobe.rmeta'] == positive['second-empty']['libprobe.rmeta']
            both = case != 'literal' or arm == 'candidate'
            assert (positive['warm']['libprobe.rmeta'] == positive['empty']['libprobe.rmeta']) == both
            if case=='literal':
                assert (positive['restore']['libprobe.rmeta'] == positive['clean-original']['libprobe.rmeta']) == both
            readers = base/case/'readers'
            bridge_hash = {}
            for built, offered in product(('warm','empty'), repeat=2):
                assert status(readers/('bridge-'+built)) == 0
                d = readers/(built+'-'+offered)
                bindings = read(d/'bindings.json')
                assert bindings['rlib'] == positive[offered]['libprobe.rlib']
                assert re.fullmatch('[0-9a-f]{64}', bindings['elf']) and re.fullmatch('[0-9a-f]{64}', bindings['bridge'])
                assert bridge_hash.setdefault(built,bindings['bridge']) == bindings['bridge']
                assert status(d/'compile') == 0 and status(d/'native') == 0
                assert (d/'native/stdout').read_bytes() == b'8:8\n' and not (d/'native/stderr').read_bytes()
                callers += 1
        results[arm] = subject['outcomes']
    assert (valid, failures, callers) == (60, 12, 16)
    return dict(successful_producers=valid, expected_E0080=failures, native_callers=callers, timed_commands=0, outcomes=results)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    archive = folder/'native-receipts.tar.gz'
    with tarfile.open(archive,'r:gz') as tf:
        names = set()
        for m in tf:
            path = Path(m.name)
            assert m.isfile() and not path.is_absolute() and '..' not in path.parts and m.name not in names
            assert path.parts[0] in ('parent-evidence','candidate-evidence')
            names.add(m.name)
        tf.extractall(root,filter='data')
    print(json.dumps(verify(root, root), indent=2, sort_keys=True))
