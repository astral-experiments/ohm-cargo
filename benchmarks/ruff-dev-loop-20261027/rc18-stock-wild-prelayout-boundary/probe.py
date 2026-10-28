"""Qualify stock Wild's pre-layout reproducer on native inputs and a pipe jobserver."""
import array
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import termios
import time

WILD = Path(sys.argv[1]).resolve()
DIR = Path(sys.argv[2]).resolve()
DIR.mkdir()
os.chdir(DIR)
BASE = Path(__file__).resolve().parent
STOCK = '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
H = lambda b: hashlib.sha256(b).hexdigest()
assert H(WILD.read_bytes()) == STOCK
def file_sha(p): return H(Path(p).read_bytes())
def run(argv, **kw):
    return subprocess.run(list(map(str, argv)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, **kw)
def build(src, out):
    cp = run(['as',src,'-o',out]); cp.check_returncode()
def available(fd):
    a = array.array('i',[0]); fcntl.ioctl(fd,termios.FIONREAD,a,True); return a[0]
def ro_entsize(b):
    header = struct.unpack_from('<Q',b,40)[0]
    stride,n,strings = struct.unpack_from('<HHH',b,58)
    names = struct.unpack_from('<Q',b,header+strings*stride+24)[0]
    for i in range(n):
        sec = header+stride*i
        off = names+struct.unpack_from('<I',b,sec)[0]
        if b[off:b.index(b'\0',off)] == b'.rodata': return struct.unpack_from('<Q',b,sec+56)[0]
def inventory():
    root = Path('save')
    return {str(p.relative_to(root)):file_sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
records = {}
def phase(label,args,*,save=False,tokens=0,output='img'):
    # The same kernel pipe and descriptor numbers are presented in each Wild child.
    r,w = os.pipe()
    assert (r,w) == (3,4), (r,w)
    os.write(w,b'+'*tokens)
    env = {'PATH':'/usr/bin:/bin','LC_ALL':'C', 'CARGO_MAKEFLAGS':f'-j --jobserver-auth={r},{w}'}
    if save: env |= {'WILD_SAVE_DIR':str(DIR/'save'),'WILD_SAVE_SKIP_LINKING':'1'}
    if Path('save').exists():
        assert Path('save').resolve() == DIR/'save'; shutil.rmtree('save')
    out = Path(output)
    old = file_sha(out) if out.is_file() else None
    cp = run([WILD,*args],env=env,pass_fds=(r,w))
    # In forking mode regular success can notify parent just before returning workers.
    for _ in range(100):
        if available(r)==tokens: break
        time.sleep(.001)
    leftover = available(r)
    os.close(r); os.close(w)
    row = dict(argv=args,status=cp.returncode,stdout=cp.stdout.decode(errors='backslashreplace'),
        stderr=cp.stderr.decode(errors='backslashreplace'),tokens_before=tokens,tokens_after=leftover,
        before=old,after=file_sha(out) if out.is_file() else None)
    if save:
        row['saved']=inventory() if Path('save').is_dir() else {}
        if Path('save/run-with').exists():
            row['run_with']=Path('save/run-with').read_text().replace(str(DIR),'<case>')
    elif cp.returncode == 0:
        data=out.read_bytes()
        row['return']=run([out.resolve()]).returncode
        row['rodata_entsize']=ro_entsize(data)
    records[label]=row
    return row
for name in ['start','ordinary','eight']:
    build(BASE/(name+'.s'),name+'.o')
args=['-m','elf_x86_64','--build-id','-e','_start','--gc-sections','-o','img','start.o','ordinary.o','eight.o']
for fork in ['default','no-fork']:
    argv=args if fork=='default' else ['--no-fork',*args]
    for n in (0,3):
        for mode in ['full','save']:
            phase(f'job-{fork}-{n}-{mode}',argv,save=mode=='save',tokens=n)
Path('shadow.s').write_text('.text\n.global _start\n_start: call selected\n mov %eax,%edi\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n')
build('shadow.s','shadow.o')
for d in ['earlier','later']:Path(d).mkdir()
def archive(name,value):
    Path('selected.s').write_text(f'.text\n.global selected\nselected: mov ${value},%eax\n ret\n.section .note.GNU-stack,"",@progbits\n')
    build('selected.s','selected.o')
    cp=run(['ar','rcsD',name,'selected.o']);cp.check_returncode()
archive('later/libnative.a',41)
args=['-m','elf_x86_64','--build-id','-e','_start','-o','shadow','shadow.o','-Learlier','-Llater','-lnative']
for label in ['lower','earlier','malformed','missing']:
    if label=='earlier':archive('earlier/libnative.a',83)
    if label=='malformed':Path('earlier/libnative.a').write_bytes(b'not a valid linker script\n')
    if label=='missing':
        Path('earlier/libnative.a').unlink();Path('later/libnative.a').unlink()
    for mode in ['full','save']:
        phase(f'shadow-{label}-{mode}',args,save=mode=='save',output='shadow')
# A simple --version-script named only via -L is resolved by AuxiliaryFiles after save finishes.
script=Path('later/exports.map')
args=['-m','elf_x86_64','--build-id','-e','_start','-o','img','start.o','ordinary.o','eight.o','-Llater','--version-script=exports.map']
for label,body in [('valid','ONE { global: _start; local: *; };\n'),('malformed','ONE { this-is-not-a-version-list\n'),('absent',None)]:
    if body is None:script.unlink()
    else:script.write_text(body)
    for mode in ['full','save']:phase(f'version-{label}-{mode}',args,save=mode=='save')
def alias(key):return key.replace(str(DIR).lstrip('/'),'<case>').replace(str(DIR),'<case>')
def normalize(row):
    if 'saved' in row:
        raw=row['saved']
        row['saved_path_bytes_sha256']=H(json.dumps(raw,sort_keys=True).encode())
        row['saved']={alias(k):v for k,v in raw.items()}
for row in records.values():normalize(row)
result={'wild':STOCK,'version':run([WILD,'--version']).stdout.decode().strip(),
        'inputs':{f'{n}.o':file_sha(f'{n}.o') for n in ['start','ordinary','eight','shadow']},
        'records':records}
data=json.dumps(result,indent=2,sort_keys=True)+'\n';(DIR/'result.json').write_text(data)
for label,row in records.items():
    print(label,row['status'],row['tokens_after'],row.get('return'),row.get('rodata_entsize'),str(row.get('saved_path_bytes_sha256',row.get('after')))[:12],row['stderr'].splitlines()[-1:] )
