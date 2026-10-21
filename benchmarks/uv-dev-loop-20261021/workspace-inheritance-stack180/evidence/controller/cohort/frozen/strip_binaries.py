#!/usr/bin/env python3
"""Strip debug sections without modifying the linked executable input."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allocated_sections(data):
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected a little-endian ELF64 executable")
    table = struct.unpack_from("<Q", data, 40)[0]
    stride, count, names_index = struct.unpack_from("<HHH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, table + i * stride) for i in range(count)]
    names_section = sections[names_index]
    names = data[names_section[4]:names_section[4] + names_section[5]]
    result = []
    for section in sections:
        name, kind, flags, address, offset, size, _, _, alignment, _ = section
        if flags & 2:
            end = names.index(b"\0", name)
            result.append({
                "name": names[name:end].decode(), "kind": kind, "flags": flags,
                "address": address, "size": size, "alignment": alignment,
                "sha256": None if kind == 8 else sha(data[offset:offset + size]),
            })
    return result


def main():
    root = Path(__file__).resolve().parents[1] / "binaries"
    output = root / "stripped"
    output.mkdir(exist_ok=True)
    linked_manifest = json.loads((root / "manifest.json").read_text())
    for name in sys.argv[1:]:
        source, destination = root / name, output / name
        before = source.read_bytes()
        subprocess.run(["objcopy", "--strip-debug", str(source), str(destination)], check=True)
        after = destination.read_bytes()
        if source.read_bytes() != before:
            raise RuntimeError("Input executable changed")
        loaded = allocated_sections(before)
        if allocated_sections(after) != loaded:
            raise RuntimeError("An allocated runtime section changed")
        manifest = {
            "source_sha256": sha(before), "stripped_sha256": sha(after),
            "original_linker_output_sha256": linked_manifest[name].get("original_linker_output_sha256", sha(before)),
            "source_bytes": len(before), "stripped_bytes": len(after),
            "command": ["objcopy", "--strip-debug", str(source), str(destination)],
            "allocated_sections": loaded,
        }
        (output / f"{name}.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(name, len(after), sha(after), flush=True)


if __name__ == "__main__":
    main()
