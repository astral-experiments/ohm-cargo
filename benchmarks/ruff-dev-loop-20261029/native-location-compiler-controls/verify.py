"""Verify the compiler patch, matched native inputs and ten completed fixture runs."""
import gzip
import hashlib
import json
from pathlib import Path
here = Path(__file__).resolve().parent
def sha(data):
    return hashlib.sha256(data).hexdigest()
def get(name):
    return json.loads((here / name).read_bytes())
for line in (here / 'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert Path(name).name == name and sha((here / name).read_bytes()) == digest
s = get('source.json')
m = get('matched-sdks.json')
g = get('five-suites.json')
v = get('absolute-location.json')
p = gzip.decompress((here / 'source.patch.gz').read_bytes())
assert s['patch_sha256'] == sha(p)
assert s['commits']['parent']['sha'] == m['parent'] and s['commits']['child']['sha'] == m['child']
blobs = [s['commits'][r]['encoder_blob'].encode() for r in ('parent', 'child')]
assert b'index ' + b'..'.join(blobs) + b' 100644' in p
assert p.count(b'diff --git ') == 1 and b'+        let span = span.data();' in p
assert m['verified_direct_source_changes'] == [s['source_path']]
assert m['old_physical_native_command_count'] == m['new_physical_native_command_count'] == 119
assert m['same_literal_native_argv_multiset'] and m['only_new_native_argv'] == m['only_old_native_argv'] == []
assert m['unchanged_std_entries'] == 53 and len(m['sdk_member_differences']) == 1
assert g['matched_sdk_sha256'] == sha((here / 'matched-sdks.json').read_bytes())
assert len(g['suites']) == 5 and sum(x['full_rustc'] for x in g['suites'].values()) == 63
assert all(x['exit'] == 0 for x in g['suites'].values()) and set(g['arm_receipts']) == {'parent', 'child'}
assert v['same_native_absolute_values'] == {'columns': [1, 257], 'hashes': [
    '8540b008200c27d18555aa6f07e2ebc2', '177cab50a2fdd7467f2bf1a72266a6bf']}
assert all(n == 2 for n in v['verified_native_invocations_per_arm'].values())
print('One compiler file, 119 matched native commands, 53 matching std entries, five suites and both native locations verified.')
