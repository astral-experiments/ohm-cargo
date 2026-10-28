"""Observe access events and a wider-than-trained jobserver on a real GCC/collect2 link."""
import array
import collections
import ctypes
import fcntl
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

stock,shim,root = map(lambda s: Path(s).resolve(), sys.argv[1:])
digest = lambda b: hashlib.sha256(b).hexdigest()
assert digest(stock.read_bytes()) == '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
root.mkdir(); os.chdir(root)
Path('main.c').write_text('int main(void) { return 41; }\n')
subprocess.run(['/usr/bin/cc','-c','main.c','-o','main.o'],check=True)
Path('which').mkdir();ld=Path('which/ld.bfd')
def choose(p):
    ld.unlink(missing_ok=True)
    ld.symlink_to(p)
argv=['/usr/bin/cc','-B'+str(root/'which'),'-fuse-ld=bfd','-Wl,--build-id','-Wl,--gc-sections','-o','image','main.o']
libc = ctypes.CDLL(None,use_errno=True)
def observe(kind,count,log=False,follow=True):
    choose(stock)
    subprocess.run(argv,check=True,capture_output=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    original=Path('image').read_bytes()
    held=os.open('image',os.O_PATH|os.O_NOFOLLOW)
    saved=os.memfd_create('immutable-training', os.MFD_ALLOW_SEALING);os.write(saved,original);fcntl.fcntl(saved,1033,15)
    a,b=os.pipe();tokens=bytes(range(1,count+1));os.write(b,tokens)
    mask=0x0001|0x0002|0x0004|0x0008|0x0010|0x0020|0x0200|0x0400
    w=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC); assert w>=0
    assert libc.inotify_add_watch(w,b'image',mask)>=0
    choose(stock if kind=='stock' else shim)
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','CARGO_MAKEFLAGS':f'-j --jobserver-auth={a},{b}',
         'OHM_PROBE_WILD':str(stock),'OHM_PROBE_ARGV':str(root/'argv'),'OHM_PROBE_WIDTH':str(root/'width'),'OHM_PROBE_ACTION':str(root/'action')}
    if kind=='probe':env['OHM_TEST_CERTIFIED_IMAGE_FD']=str(saved)
    if log:env['WILD_LOG']='libwild::args=trace'
    for f in ['argv','action','width']:Path(f).unlink(missing_ok=True)
    cp=subprocess.run(argv, env=env, pass_fds=(saved,a,b), capture_output=True,timeout=20)
    assert cp.returncode==0
    try:data=os.read(w,64000)
    except BlockingIOError:data=b''
    masks=[];i=0
    while i<len(data):
        _,m,_,n=struct.unpack_from('iIII',data,i);masks.append(m);i+=16+n
    for _ in range(300):
        n=array.array('i',[0]);fcntl.ioctl(a,termios.FIONREAD,n,True)
        if n[0]==count:break
        time.sleep(.001)
    assert n[0]==count
    returned=os.read(a,count) if count else b''
    assert collections.Counter(tokens)==collections.Counter(returned)
    held_stat=os.fstat(held);post=Path('image').stat()
    actual=Path('image').read_bytes()
    run=subprocess.run([str(root/'image')]);assert run.returncode==41
    for fd in (a,b,saved,held,w):os.close(fd)
    loglines=[l for l in (cp.stdout+cp.stderr).decode().splitlines() if 'Acquired jobserver' in l]
    if log and kind=='stock':assert len(loglines)==1,cp.stderr
    return {'arm':kind,'tokens':count,'explicit_log':log,'masks':masks,'same_held_inode':(held_stat.st_ino,held_stat.st_dev)==(post.st_ino,post.st_dev),
            'before':digest(original),'after':digest(actual),'program_exit':run.returncode,'status':cp.returncode,
            'stderr':cp.stderr.decode().replace(str(root),'<case>'),'stdout':cp.stdout.decode().replace(str(root),'<case>'),
            'tokens_restored':sorted(returned),'probe_width':int(Path('width').read_text()) if Path('width').exists() else None,
            'decision':Path('action').read_text() if Path('action').exists() else None,'loglines':loglines}
rows=[observe(k,n,l) for n,l in ((3,False),(0,False),(20,False),(20,True)) for k in ('stock','probe')]
(root/'result.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
for r in rows:print(r['arm'],r['tokens'],r['explicit_log'],r['masks'],r['same_held_inode'],r['probe_width'],r['decision'],r['loglines'])
