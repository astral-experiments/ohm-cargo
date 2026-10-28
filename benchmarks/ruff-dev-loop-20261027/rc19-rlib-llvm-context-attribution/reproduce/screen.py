"""Count the LLVMContexts actually constructed by the stock archive reader on real Ruff members."""
from collections import Counter
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import statistics
import struct
import subprocess


def sha(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def put(path, result):
    with path.open('x') as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write('\n')


def ar_symbols(archive, roster):
    with archive.open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as buf:
        assert buf[:8] == b'!<arch>\n'
        off = 8
        members = []
        index = None
        width = None
        while off < len(buf):
            header = buf[off:off+60]
            assert len(header) == 60 and header[58:60] == b'`\n'
            name, size = header[:16].rstrip(b' '), int(header[48:58])
            start = off + 60
            if name in (b'/', b'/SYM64/'):
                assert index is None
                index = buf[start:start+size]; width = 4 if name == b'/' else 8
            elif name != b'//':
                assert not name.startswith(b'#1/') and buf[start:start+4] == b'\x7fELF', (name, size, buf[start:start+8])
                members.append((off, start, size))
            off = start + size + size % 2
        assert off == len(buf) and index and members
    roster.write_text(''.join(f'{start} {size}\n' for _, start, size in members))
    ranks = {head: i for i,(head,_,_) in enumerate(members)}
    n = int.from_bytes(index[:width], 'big')
    names = index[(n+1)*width:].split(b'\0')
    assert all(not x for x in names[n:]) and len(names) >= n
    expected = bytearray()
    for i, name in enumerate(names[:n]):
        pos = int.from_bytes(index[(i+1)*width:(i+2)*width], 'big')
        expected.extend(struct.pack('<II', ranks[pos], len(name))); expected.extend(name)
    return len(members), n, hashlib.sha256(expected).hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', required=True, type=Path)
parser.add_argument('--archives', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
sources = Path(__file__).resolve().parent
here = args.output.resolve(); here.mkdir(parents=True)
sdk = args.sdk.resolve()
libs = sdk/'lib'; driver, = libs.glob('librustc_driver*.so'); llvm, = libs.glob('libLLVM.so.23*')
rows = subprocess.check_output(['nm', str(driver)], text=True).splitlines()
sym, = [row.split()[0] for row in rows if row.endswith(' t LLVMRustGetSymbols')]
assert sym == '00000000061c25c0'
env = dict(os.environ, LD_LIBRARY_PATH=str(libs), LD_PRELOAD=str(driver))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
image = {'driver': sha(driver), 'llvm': sha(llvm), 'callback_symbol': sym, 'rustc': sha(sdk/'bin/rustc'), 'cpu': list(os.sched_getaffinity(0))}
assert image['driver'] == 'a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de'
assert image['llvm'] == '43bac9749e539cd5988a4d5452b64582cf07ac9e7c059fde29c7bee76e106c51'
put(here/'stock-images.json', image)
subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-o',here/'released-symbols',sources/'released-symbols.c','-ldl'],check=True)
subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-o',here/'observe-context.so',sources/'observe-context.c','-ldl'],check=True)
root = args.archives.resolve()
summary = {}
for crate in ('ruff_python_ast','ruff_python_parser','ruff_linter','ty_python_semantic'):
    archive = root/f'lib{crate}.rlib'
    if not archive.is_file():
        print('unavailable',crate,flush=True); continue
    output = here/crate; output.mkdir()
    roster = output/'roster'; members, symbols, symbol_digest = ar_symbols(archive, roster)
    cmd = [str(here/'released-symbols'),str(driver),sym,str(archive),str(roster)]
    actual = output/'actual-symbols.bin'
    exact = subprocess.check_output([*cmd,'1',str(actual)],env=env,text=True).strip()
    assert sha(actual) == symbol_digest and list(map(int,exact.split()))[:2]==[members,symbols], (crate,sha(actual),symbol_digest,exact)
    experiment = {}
    for label, injected in [('normal',False),('observed',True)]:
        runenv = dict(env)
        if injected: runenv['LD_PRELOAD']=str(here/'observe-context.so')+':'+str(driver)
        lines = subprocess.check_output([*cmd,'24','-'],env=runenv,text=True).splitlines()
        values = [list(map(int,s.split())) for s in lines]
        assert len(values)==24 and all(r[:2]==[members,symbols] and r[4:6]==([members,members] if injected else [0,0]) for r in values), (crate,label,values[:2])
        put(output/(label+'.json'),values)
        experiment[label]={'total_median_ns':statistics.median(r[3] for r in values[2:]),'constructor_median_ns':statistics.median(r[6] for r in values[2:]),'destructor_median_ns':statistics.median(r[7] for r in values[2:])}
    summary[crate]={'archive':sha(archive),'archive_bytes':archive.stat().st_size,'elf_members':members,'symbols':symbols,'complete_ordered_symbols':symbol_digest,'cost':experiment};print(crate,summary[crate],flush=True)
assert {'ruff_python_ast','ruff_python_parser'} <= summary.keys()
put(here/'result.json',summary)
