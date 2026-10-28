"""Read the exact typeshed file with a checked fallback for ZIP method 93."""
import struct
import subprocess
import zlib

def read_stub(archive, name):
    info = archive.getinfo(name)
    if info.compress_type != 93:
        return archive.read(info)
    assert archive.fp is not None and not info.flag_bits & 1
    archive.fp.seek(info.header_offset)
    hdr = archive.fp.read(30)
    signature, _, _, method, _, _, _, _, _, name_len, extra_len = struct.unpack('<4s5H3I2H', hdr)
    assert signature == b'PK\x03\x04' and method == 93
    assert archive.fp.read(name_len) == name.encode('ascii')
    archive.fp.read(extra_len)
    assert 0 < info.compress_size < 1_000_000 and 0 < info.file_size < 1_000_000
    data = archive.fp.read(info.compress_size)
    assert len(data) == info.compress_size
    decoded = subprocess.run(['/usr/bin/zstd', '-qdc'], input=data, capture_output=True, check=True).stdout
    assert len(decoded) == info.file_size and zlib.crc32(decoded) == info.CRC
    return decoded
