"""Check which bytes differ between the timed and fully reconstructed Cargo executables."""
import hashlib
import json
from pathlib import Path
import struct
import sys

sha = lambda data: hashlib.sha256(data).hexdigest()


def sections(data):
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    assert header[0][:6] == b'\x7fELF\x02\x01'
    offset, size, count, names_index = header[6], header[11], header[12], header[13]
    records = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i*size) for i in range(count)]
    names = records[names_index]
    strings = data[names[4]:names[4] + names[5]]
    return {strings[r[0]:strings.index(0, r[0])].decode(): r for r in records}


timed, merged = (Path(p).read_bytes() for p in sys.argv[1:])
before, after = sections(timed), sections(merged)
assert before == after and len(timed) == len(merged)
differing = []
for name, record in before.items():
    _, kind, flags, address, start, size = record[:6]
    if kind == 8:  # SHT_NOBITS has no file payload
        continue
    a, b = timed[start:start+size], merged[start:start+size]
    if a != b:
        differing.append(dict(name=name, offset=start, size=size, address=address, flags=flags,
                              differing_bytes=sum(x != y for x, y in zip(a, b)), timed_sha256=sha(a), merged_sha256=sha(b)))
assert {r['name'] for r in differing} == {'.note.gnu.build-id', '.strtab'}
cursor = 0
for r in sorted(differing, key=lambda r: r['offset']):
    assert timed[cursor:r['offset']] == merged[cursor:r['offset']]
    cursor = r['offset'] + r['size']
assert timed[cursor:] == merged[cursor:]
code = before['.text']
print(json.dumps(dict(total_bytes=len(timed), timed_sha256=sha(timed), full_draft_sha256=sha(merged),
                      sections=len(before), text_size=code[5], text_address=code[3], text_sha256=sha(timed[code[4]:code[4]+code[5]]),
                      all_bytes_outside_differing_sections_identical=True, differing_sections=differing), indent=2))
