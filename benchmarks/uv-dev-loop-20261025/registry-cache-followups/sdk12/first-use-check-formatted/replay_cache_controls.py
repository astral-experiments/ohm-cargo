"""Replay public first-use inventory and custody joins; payloads stay private."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
read = lambda p: json.loads((root / p).read_bytes())
cache = read('cache-controls.json')
admission = read('admission-and-restoration.json')
counts = read('counts.json')
assert cache['schema'] == 1 and cache['slot_policy'] == 'key[:3]'
assert cache['max_slots'] == 4096 and cache['max_entry_bytes'] == 65536
assert not cache['keyed_blake3_independently_rechecked_by_observer']
assert not cache['hit_count_or_total_write_claim']
inventory = cache['shared_post_inventory']
assert len(inventory) == len({r['name'] for r in inventory}) == 445
assert sum(r['bytes'] for r in inventory) == 803161
# codec_digest is the per-entry keyed payload digest, not a common parser ID.
assert inventory == sorted(inventory, key=lambda row: row['name'])
for row in inventory:
    assert re.fullmatch('[0-9a-f]{3}', row['name'])
    assert row['name'] == row['key'][:3]
    assert 0 < row['bytes'] <= cache['max_entry_bytes'] and row['mode'] == 0o600
    for name in ('sha256', 'payload_sha256', 'key', 'codec_digest'):
        assert re.fullmatch('[0-9a-f]{64}', row[name])
digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
expected = set()
for block, data in enumerate(counts['blocks'], 1):
    for pair_index, pair in enumerate(data['pairs']):
        for position, letter in enumerate(pair['order']):
            expected.add((block, f"pair-{pair_index}-{position}-{'baseline' if letter == 'A' else 'candidate'}"))
assert len(expected) == len(cache['observations']) == 32
assert {(r['block'], r['label']) for r in cache['observations']} == expected
for row in cache['observations']:
    host = admission['hosts'][row['block'] - 1]
    assert not row['before_present'] and row['before_slots'] == row['before_bytes'] == 0
    assert row['after_present'] and row['after_slots'] == len(inventory)
    assert row['after_bytes'] == sum(r['bytes'] for r in inventory)
    assert row['after_inventory_sha256'] == host['post_cache_inventory_digest'] == digest
    assert row['terminal_sha256'] == host['terminal_sha256']
    assert re.fullmatch('[0-9a-f]{64}', row['cache_reset_sha256'])
    assert row['regular_single_link_owned_entries_and_JSON_shape_passed']
print(json.dumps({'state': 'all-32-first-use-inventory-joins-pass', 'slots': len(inventory),
                  'committed_bytes': 803161, 'payloads_independently_replayed_here': False}))
