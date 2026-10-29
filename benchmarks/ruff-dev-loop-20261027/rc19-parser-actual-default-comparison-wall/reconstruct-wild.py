"""Recompute the whole ELF, using the stock Wild 0.11.0 GNU-note algorithm."""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import struct

def blake3(data):
    lib = ctypes.CDLL(ctypes.util.find_library('LLVM-18') or ctypes.util.find_library('LLVM'))
    state = ctypes.create_string_buffer(16 * 1024)
    out = ctypes.create_string_buffer(32)
    src = (ctypes.c_ubyte * len(data)).from_buffer(data)
    lib.llvm_blake3_hasher_init(state)
    lib.llvm_blake3_hasher_update(state, src, ctypes.c_size_t(len(data)))
    lib.llvm_blake3_hasher_finalize(state, out, ctypes.c_size_t(32))
    return out.raw

def variants(file):
    data = bytearray(file.read_bytes())
    assert data[:6] == b'\x7fELF\x02\x01'
    table = struct.unpack_from('<Q', data, 0x28)[0]
    size, count, string_index = struct.unpack_from('<HHH', data, 0x3a)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, table+i*size) for i in range(count)]
    strings = sections[string_index]
    names = data[strings[4]:strings[4]+strings[5]]
    named = {bytes(names[s[0]:names.index(0,s[0])]).decode(): (i,s) for i,s in enumerate(sections)}
    rid,ro = named['.rodata']
    idx,nt = named['.note.gnu.build-id']
    assert nt[1] == 7 and data[nt[4]:nt[4]+16] == struct.pack('<III4s',4,32,3,b'GNU\0') and nt[5] == 48
    assert ro[-1] in (0,1) and ro[2] & 0x30 == 0x30
    notes = slice(nt[4],nt[4]+nt[5])
    header = bytes(data[notes][:16])
    ro_field = table+rid*size+56
    original = hashlib.sha256(data).hexdigest()
    variants = {}
    for value in (0,1):
        struct.pack_into('<Q',data,ro_field,value)
        data[notes] = bytes(48)
        new_id = blake3(data)
        data[notes] = header+new_id
        variants[str(value)] = {'elf_sha256':hashlib.sha256(data).hexdigest(),'build_id':new_id.hex()}
    assert variants[str(ro[-1])]['elf_sha256'] == original
    return {'reference_sha256':original,'reference_entry_size':ro[-1], 'file_bytes':len(data),'rodata_flags':ro[2],
            'entry_size_file_offset':ro_field,'gnu_note_offset':nt[4],'gnu_note_bytes':nt[5],'variants':variants}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('original',type=Path)
    parser.add_argument('edited',type=Path)
    a=parser.parse_args()
    assert blake3(bytearray()).hex() == 'af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262'
    print(json.dumps({'H':variants(a.original),'P':variants(a.edited)},sort_keys=True,indent=2))
