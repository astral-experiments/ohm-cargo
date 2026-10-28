"""Compare exact archive member positions from the two immutable source-state manifests."""
import collections
import gzip
import json
import sys
from pathlib import Path

def read(path):
    with gzip.open(path) as f:
        return json.load(f)

def compare(original):
    catalog = read(original / 'all-rosters.json.gz')['archives']
    evidence = read(original / 'full-historical.json.gz')
    rows = []
    for side in evidence['local_libraries']['settle-current__warm-reverse']:
        a, b = side['archive']
        if a == b or not side['all_native_payload_multisets_equal']:
            continue
        earlier, later = (catalog[h]['members'] for h in [a, b])
        assert len(earlier) == len(later)
        objects = [(u, v) for u, v in zip(earlier, later)
                   if u['name'].endswith('.rcgu.o') and v['name'].endswith('.rcgu.o')]
        assert len(objects) == len(earlier) - 4 == side['identical_object_payloads']
        assert all((u['bytes'], u['sha256']) == (v['bytes'], v['sha256']) for u, v in objects)
        assert all(u['name'] != v['name'] for u, v in objects)
        deltas = collections.Counter(v['offset'] - u['offset'] for u, v in objects)
        assert all(u['elf'] and v['elf'] for u, v in objects)
        assert len(deltas) == 1
        prev, curr = objects[0]
        # The ar format's single odd-byte pad is outside the acquired member digests.
        # Never infer a raw suffix across uncaptured pad bytes.
        native_tail_checked = all(u['bytes'] % 2 == 0 and
                                  u['header_sha256'] == v['header_sha256'] for u,v in objects)
        op = prev['offset'] - 60
        np = curr['offset'] - 60
        assert op >= 8 and np >= 8
        suffix = catalog[a]['bytes'] - op
        assert suffix == catalog[b]['bytes'] - np
        for members, total in [(earlier, catalog[a]['bytes']), (later, catalog[b]['bytes'])]:
            assert all(r['offset'] + r['bytes'] + r['bytes'] % 2 + 60 == s['offset']
                       for r,s in zip(members, members[1:]))
            last = members[-1]
            assert last['offset'] + last['bytes'] + last['bytes'] % 2 == total
        special = {u['name']:{'length_equal':u['bytes']==v['bytes'],
                               'offset_equal':u['offset']==v['offset'],
                               'bytes_equal':u['sha256']==v['sha256'],
                               'header_equal':u['header_sha256']==v['header_sha256'],
                               'old_size':u['bytes'],'new_size':v['bytes']}
                   for u,v in zip(earlier[:4], later[:4])}
        assert set(special) == {'/','//','lib.rmeta','lib.rmeta-link'}
        rows.append({'crate':side['name'],'old_archive':a,'edited_archive':b,'objects':len(objects),
                     'native_payload_bytes':sum(u['bytes'] for u,v in objects),
                     'all_member_ranges_equal':all((u['offset'],u['bytes'])==(v['offset'],v['bytes'])
                                                   for u,v in zip(earlier,later)),
                     'native_equal_offsets':sum(u['offset']==v['offset'] for u,v in objects),
                     'native_congruent_4096':sum((u['offset']-v['offset'])%4096==0 for u,v in objects),
                     'native_payload_offset_delta':next(iter(deltas)),
                     'native_headers_equal':sum(u['header_sha256']==v['header_sha256'] for u,v in objects),
                     'old_native_header_start':op,'new_native_header_start':np,
                     'equal_native_suffix_bytes_proved':suffix if native_tail_checked else None,
                     'special_members':special})
    assert len(rows)==31
    return {'old_phase':'settle-current','edited_phase':'warm-reverse','products':rows}

if __name__ == '__main__':
    result = compare(Path(sys.argv[1]))
    print(json.dumps(result, sort_keys=True, indent=2))
