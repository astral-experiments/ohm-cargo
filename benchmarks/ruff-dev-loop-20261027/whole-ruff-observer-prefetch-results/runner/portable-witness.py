"""Recreate the retained per-invocation, input, and ELF hashes from the self-contained review data."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()

def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()

def document(name):
    return json.loads((root / name).read_bytes())

anchors = document('anchors.json')
exe = document('execs.json')
details = json.loads(gzip.decompress((root / 'structural-witnesses.json.gz').read_bytes()))
traced = document('command-witnesses.json')
with (root / 'wall.csv').open() as f:
    rows = list(csv.DictReader(f))
assert len(rows) == len(exe) == len(traced) == 64
for mode, a in details.items():
    public = anchors[mode]
    assert len(a['roster']) == public['units'] == (619 if mode == 'test' else 501)
    assert digest(a['roster']) == public['roster']
    assert digest(a['messages']) == public['messages']
    assert digest(a['stamps']) == public['identity_sha256']
    assert digest(a['proofs']) == public['observer_sha256']
    assert digest(a['passive_proofs']) == public['passive_observer_sha256'] and digest(a['reader_metadata']) == public['reader_metadata_sha256'] and digest(a['active_artifact']) == public['active_artifact_sha256']
    if mode=='test':
        m,=[n for n in a['active_artifact']['filenames'] if n.endswith('.rmeta')]; assert any(r['path']==m and r['role']=='active' for r in a['reader_metadata']) and len(a['reader_metadata'])==2 and len(a['passive_proofs'])==1
    assert list(sorted(a['raw_sha256'])) == list(sorted(a['stamps']))
    assert len(a['raw_sha256']) == public['elf_count'] == (110 if mode == 'test' else 15)
    assert len(a['executables']) == public['executable_count'] == (102 if mode == 'test' else 6)
    assert all(len(stat) == 6 and stat[3] > 0 for stat in a['stamps'].values())
    assert a['cache_inventory'] == public['cache']
    assert a['cache_inventory']['.ohm-registry-json-v1']['files'] > 0
    assert all(ancestor['trusted'] for ancestor in a['cargo_home_ancestors'])
    assert len(a['exec_open_calibration']) == 1
    assert (sum('ron@0.12.0' in unit and '"kind": ["lib"]' in unit for unit in a['roster']) > 0) == (mode == 'test')
    quote = a['diagnostics']
    assert [r['message'] for r in quote['mixed']] == ['Cannot mix t-string literals with string or bytes literals']
    assert [(r['code'], r['location']['row'], r['location']['column']) for r in quote['dataclass']] == [('RUF008', 4, 34), ('RUF008', 6, 20)]

for r, e, w in zip(rows, exe, traced):
    key = (int(r['block']), r['mode'], r['arm'])
    assert (e['block'], e['mode'], e['arm']) == (w['block'], w['mode'], w['arm']) == key
    assert int(r['elapsed_ns']) == w['native_ns'] and len(w['watched_images']) >= 3
    assert int(r['native_image_opens']) == len(w['observed_native_opens']) == 0
    assert not w['full_rustc'] and not w['rustc_queries'] and not w['linkers'] and not w['target_processes']
    names = [s for _, s, _ in w['successful_execs']]
    assert all(str(label) in w['raw_exec_files'] and len(path_hash) == 64 for label, _, path_hash in w['successful_execs'])
    assert names == e['images'] and 'cargo-proxy-or-installed' in names
    assert e['raw_exec_rows'] == len(names)
    assert len(w['raw_exec_files']) > 0 and all(len(h) == 64 for h in w['raw_exec_files'].values())
print('Verified 64 actual native runs and separate exec replays against both structural rosters and every anchored workspace ELF.')
