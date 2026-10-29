"""Recompute every extent intersection after the common coordinate translation."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
r = json.loads((root / 'extents.json').read_bytes())
assert r['single_data_profile'] and r['read_only_block_device'] and r['fiemap_flags'] == r['sync_requests'] == 0
assert r['raw_receipt_sha256'] == '6b851a281be7eb5b62aeab892875e25d76893b7247cd0f9c4610164faf4598b3'
expected = {'H':'3dc4253060abc0704b18356acd2bb134383b88538a3b0642a1ad97307ffaeaf0',
            'P-A':'41a6e23b656b7fd8cbca59362b643f7f5044b422ed2d6c6158860b9d96ac716a',
            'P-B':'469059d02711c6f78ae0b88e6cf71004a0e0f495cdfd4e0f615c9d8194a28d3e'}
raw = r['inputs']
assert set(raw) == set(expected)
size = 101719820

def interval(ranges, start, end):
    if ranges and sum(ranges[-1]) == start:
        ranges[-1][1] += end - start
    else:
        ranges.append([start,end - start])

for k,s in raw.items():
    assert s['sha256'] == expected[k] and s['size'] == size
    rows=s['relative_extents']
    assert rows[0][0] == 0 and sum(rows[-1][0:3:2]) >= size and rows[-1][3] & 1
    for i,(l,p,n,f) in enumerate(rows):
        assert n > 0 and p >= 0 and not f & ~(1|8192)
        if i:
            assert rows[i-1][0] + rows[i-1][2] == l

for key,comparison in r['comparisons'].items():
    a,b = [raw[n]['relative_extents'] for n in key.split('__')]
    cut = sorted({0,size,*[min(x[0],size) for x in a+b],*[min(x[0]+x[2],size) for x in a+b]})
    rebuilt = {k:[] for k in ('same_physical','same_physical_both_sharedflag','different_physical','opaque_or_hole')}
    for start,end in zip(cut,cut[1:]):
        x,y = [next(o for o in rows if o[0] <= start and o[0]+o[2] >= end) for rows in (a,b)]
        if x[1]-x[0] == y[1]-y[0]:
            interval(rebuilt['same_physical'],start,end)
            if x[3] & y[3] & 8192:
                interval(rebuilt['same_physical_both_sharedflag'],start,end)
        else:
            interval(rebuilt['different_physical'],start,end)
    assert all(v == comparison['intervals'][k] for k,v in rebuilt.items()), key
    for name,ranges in comparison['intervals'].items():
        assert comparison['bytes'][name] == sum(n for _,n in ranges)
    blocks = sorted(comparison['intervals']['equal_64k']+comparison['intervals']['unequal_64k'])
    assert blocks[0][0] == 0 and all(sum(x)==y[0] for x,y in zip(blocks,blocks[1:]))
    assert sum(blocks[-1]) == size and all(s % 65536 == 0 and (n%65536==0 or s+n==size) for s,n in blocks)
    print(key,comparison['bytes']['same_physical'],'same physical bytes,',comparison['bytes']['equal_64k'],'bytes in equal full 64 KiB comparisons')
assert r['comparisons']['H__P-A']['bytes']['same_physical'] == 0
assert r['comparisons']['H__P-B']['bytes']['same_physical_both_sharedflag'] == 100994828
assert r['comparisons']['P-A__P-B']['bytes']['same_physical'] == 0
