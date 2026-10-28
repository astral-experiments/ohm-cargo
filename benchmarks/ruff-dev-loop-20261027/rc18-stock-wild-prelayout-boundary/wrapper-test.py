"""Compare private post-GCC wrapper, direct stock invocations and real GNU make tokens."""
import array
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import termios
import time

src=Path(__file__).resolve().parent
wild=Path(sys.argv[1]).resolve()
wrapper=Path(sys.argv[2]).resolve()
root=Path(sys.argv[3]).resolve();root.mkdir(); os.chdir(root)
digest=lambda data:hashlib.sha256(data).hexdigest()
def sha(path): return digest(Path(path).read_bytes())
def ioctl_count(fd):
    n=array.array('i',[0]);fcntl.ioctl(fd,termios.FIONREAD,n,True);return n[0]
def run(argv,**opts):
    return subprocess.run(argv,capture_output=True,timeout=15,**opts)
def mk(obj): run(['as',str(src/(obj+'.s')),'-o',obj+'.o']).check_returncode()
for name in ('start','ordinary','eight'):mk(name)
(root/'private-linker').mkdir()
linker=root/'private-linker/ld.bfd'
widths={}
records=[]
for via in ('plain','guard'):
    if linker.is_symlink():linker.unlink()
    linker.symlink_to(wild if via=='plain' else wrapper)
    for tokens in (b'',b'Xyz'):
        for mode in ('full','save'):
            r,w=os.pipe();assert (r,w)==(3,4)
            os.write(w,tokens)
            env={'PATH':'/usr/bin:/bin','LC_ALL':'C','CARGO_MAKEFLAGS':'-j --jobserver-auth=3,4',
                 'OHM_PROBE_ARGV':str(root/'argv.bin'),'OHM_PROBE_WIDTH':str(root/'width'),
                 'OHM_PROBE_WILD':str(wild),'WILD_LOG':'libwild::args=trace' }
            if mode=='save':
                env |= {'WILD_SAVE_DIR':str(root/'save'),'WILD_SAVE_SKIP_LINKING':'1'}
            # Exact same GCC argv in all eight native runs. Its temporary plugin path is opaque.
            argv=['/usr/bin/cc','-B'+str(linker.parent),'-fuse-ld=bfd','-no-pie','-nostdlib',
                  '-Wl,--gc-sections,--build-id,-e,_start','-o','image','start.o','ordinary.o','eight.o']
            cp=run(argv,env=env,pass_fds=(r,w));cp.check_returncode()
            for _ in range(100):
                if ioctl_count(r)==len(tokens):break
                time.sleep(.001)
            count=ioctl_count(r); returned=os.read(r,count) if count else b'';os.close(r);os.close(w)
            argv_raw=None;raw_hash=None;width=None
            if via=='guard':
                blob=Path('argv.bin').read_bytes();raw_hash=digest(blob)
                argv_raw=[a.decode().replace(str(root),'<case>') for a in blob[:-1].split(b'\0')]
                width=int(Path('width').read_text())
                assert width==len(tokens)+1 and collections.Counter(tokens)==collections.Counter(returned)
                assert '--gc-sections' in argv_raw and '-plugin' in argv_raw
                assert any(a.startswith('-plugin-opt=-fresolution=') for a in argv_raw)
            else: assert b'Acquired jobserver tokens count='+str(len(tokens)).encode() in cp.stdout
            if mode=='full':
                assert run([str(root/'image')]).returncode==42
                if via=='plain':widths[len(tokens)+1]=sha('image')
                else:assert sha('image')==widths[width]
            assert len(tokens)==len(returned) or (via=='plain' and mode=='save')
            records.append(dict(via=via,mode=mode,tokens_in=list(tokens),tokens_out=list(returned),width=width,
                status=cp.returncode,gcc_argv=[a.replace(str(root),'<case>') for a in argv],
                ordinary_width_log=re.sub(rb'^.*?TRACE ',b'TRACE ',cp.stdout).decode().strip(),
                stdout_sha256=digest(cp.stdout),stderr=cp.stderr.decode().replace(str(root),'<case>'),
                final_argv=argv_raw,final_argv_sha256=raw_hash,image_sha256=sha('image')))
assert len(set(widths.values()))==2
data={'records':records,'ordinary_images':widths,'wild_sha256':sha(wild),'wrapper_sha256':sha(wrapper),'gcc_sha256':sha('/usr/bin/cc'),'sources':{n:sha(src/n) for n in ('ordinary.s','start.s','eight.s')}}
(root/'result.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
for row in records:print(row['via'],row['mode'],row['width'],row['tokens_in'],row['tokens_out'],row['image_sha256'][:12])
