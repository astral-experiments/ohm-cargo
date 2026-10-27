"""Exact ELF, witness of two known Wild fields and per-section payloads."""
import mmap,struct,hashlib
from shared import need

def elf(path):
    """Keep the exact file hash. Separately attest the two known Wild bytes classes, including all padding/header bytes outside them."""
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        need(data[:6] == b"\x7fELF\x02\x01", path)
        (shoff,) = struct.unpack_from("<Q", data, 40)
        size, count, names_idx = struct.unpack_from("<HHH", data, 58)
        need(size == 64 and 0 < names_idx < count, path)
        headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * size) for i in range(count)]
        strings = headers[names_idx]
        spans, witness, section_hashes = [], {}, {}
        for i, head in enumerate(headers):
            start = strings[4] + head[0]
            end = data.find(b"\0", start, strings[4] + strings[5])
            need(end >= start, path)
            name = data[start:end]
            section_hashes[name.decode('utf-8','backslashreplace')] = {
                'size': head[5], 'type': head[1], 'flags': head[2], 'entsize': head[9],
                'bytes': None if head[1] == 8 else hashlib.sha256(memoryview(data)[head[4]:head[4]+head[5]]).hexdigest(),
            }
            if name == b".note.gnu.build-id":
                offset, length = head[4:6]
                namesz, descsz, kind = struct.unpack_from("<III", data, offset)
                need(
                    head[1] == 7
                    and namesz == 4
                    and kind == 3
                    and length == 16 + (descsz + 3) // 4 * 4
                    and data[offset + 12 : offset + 16] == b"GNU\0",
                    path,
                )
                spans.append((offset + 16, descsz))
                witness["gnu_build_id"] = data[offset + 16 : offset + 16 + descsz].hex()
            if name == b".rodata":
                spans.append((shoff + i * size + 56, 8))
                witness["rodata_entsize"] = head[9]
        h = hashlib.sha256()
        at = 0
        for offset, length in sorted(spans):
            need(at <= offset <= len(data) - length, path)
            h.update(memoryview(data)[at:offset])
            h.update(b"\0" * length)
            at = offset + length
        h.update(memoryview(data)[at:])
        witness.update(
            raw=hashlib.sha256(data).hexdigest(),
            content_with_two_wild_fields_masked=h.hexdigest(),
            size=len(data),
            section_hashes=section_hashes,
        )
        return witness


