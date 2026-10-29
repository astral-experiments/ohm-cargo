"""Prepare a public record from the original saved read-only FIEMAP and data observations."""
import hashlib
import json
from pathlib import Path
import sys

raw = Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(raw).hexdigest() == '6b851a281be7eb5b62aeab892875e25d76893b7247cd0f9c4610164faf4598b3'
record = json.loads(raw)
inputs = {}
# A common coordinate shift preserves all equal/unequal comparisons on the one filesystem.
origin = min(row[1] for s in record['inputs'].values() for row in s['raw_extents'])
for key, spec in record['inputs'].items():
    inputs[key] = {'sha256':spec['sha256'],'size':spec['file_stat'][2], 'read_only_subvolume_id':spec['subvol'],
                   'relative_extents':[[l,p-origin,n,f] for l,p,n,f in spec['raw_extents']],
                   'original_extent_table_sha256':spec['raw_extents_sha256']}
result = {
    'raw_receipt_sha256':hashlib.sha256(raw).hexdigest(),
    'acquisition_program_sha256':'9e398b63dd256f0dd6474195f79ca4daacde1ede1684d8a40592ac41194eb9e8',
    'source':'a644772c28607282fc06bb7c72f08225ea04f0a6',
    'single_data_profile':record['data_profile'].startswith('Data, single:'),
    'read_only_block_device':record['block_device_readonly'], 'sync_requests':record['sync_requests'],
    'fiemap_flags':record['fiemap_flags_supplied'], 'inputs':inputs,'comparisons':record['pairs']}
with Path(sys.argv[2]).open('x') as dst:
    json.dump(result,dst,sort_keys=True,indent=2)
    dst.write('\n')
