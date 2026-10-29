"""Exercise both native archive writers against the independent current archive SHA-256."""
import fcntl
import hashlib
import json
import os
import random
import resource
import shutil
import signal
import socket
import stat
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path

T = Path(__file__).resolve().parent
IMAGE = {'driver':'a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de',
         'llvm':'43bac9749e539cd5988a4d5452b64582cf07ac9e7c059fde29c7bee76e106c51',
         'rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'}
SDK = T.parent/'ohm-script-hash-wall-rc19-v1/current/sdk'
WRITER = T/'target/release/rlib-current-writer'


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def sync(p):
    with p.open('rb') as f:
        os.fsync(f.fileno())


def put(p, value):
    with p.open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2)
        f.write('\n')


def prepare(work):
    assert not list(work.iterdir()) or {x.name for x in work.iterdir()} == {'lost+found'}
    s = work/'seeds'
    s.mkdir()
    shutil.copytree(T/'members',work/'members')
    provenance = json.loads((work/'members/provenance.json').read_text())
    for label,v in provenance.items():
        prior = s/label
        shutil.copyfile(T/'inputs'/v['before'],prior)
        assert sha(prior) == v['before']
        sync(prior)
        for n,d,size in v['members']:
            member = work/'members'/label/n
            assert member.stat().st_size == size and sha(member) == d
    (work/'output').mkdir()


def extents(p):
    # struct fiemap header is 32 bytes, each struct fiemap_extent is 56 bytes.
    with p.open('rb') as f:
        pos, records = 0, []
        while True:
            raw = bytearray(32+512*56)
            struct.pack_into('=QQIIII',raw,0,pos,2**64-1-pos,1,0,512,0)
            fcntl.ioctl(f,0xc020660b,raw,True)
            n = struct.unpack_from('=I',raw,20)[0]
            if not n:
                return records
            for idx in range(n):
                start,phys,size,_,_,flags,_,_,_ = struct.unpack_from('=QQQQQIIII',raw,32+56*idx)
                assert phys and size and start >= pos
                records.append((start,phys,size,flags))
                pos = start+size
            if records[-1][3]&1:
                return records


def shared_bytes(a,b):
    left,right = extents(a),extents(b)
    n, total = min(a.stat().st_size,b.stat().st_size),0
    for x,p,l,f in left:
        for y,q,m,g in right:
            lo,hi = max(x,y),min(x+l,y+m,n)
            if lo < hi and f&g&0x2000 and p+lo-x == q+lo-y:
                total += hi-lo
    return total


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024,1024))
    signal.signal(signal.SIGXFSZ,signal.SIG_IGN)


def run(work,report,kind):
    assert os.getuid() != 0 and os.geteuid() == os.getuid()
    assert (T/'inputs').is_dir() and not list((T/'inputs').iterdir())
    prov = json.loads((work/'members/provenance.json').read_text())
    labels = sorted(prov)
    assert labels == ['formatter','linter','parser']
    driver, = (SDK/'lib').glob('librustc_driver*.so')
    llvm, = (SDK/'lib').glob('libLLVM.so.23*')
    assert {'driver':sha(driver),'llvm':sha(llvm),'rustc':sha(SDK/'bin/rustc')} == IMAGE
    syms = subprocess.check_output(['nm',str(driver)],text=True).splitlines()
    assert [x.split()[0] for x in syms if x.endswith(' t LLVMRustGetSymbols')] == ['00000000061c25c0']
    env = dict(os.environ,LD_PRELOAD=str(driver.resolve()),LD_LIBRARY_PATH=str((SDK/'lib').resolve()))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    output = work/'output'/'lib.rlib'
    fs = subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',str(work)],text=True).strip()
    assert fs == kind
    def invoke(mode,label,overrides=None,limit=False):
        t = time.perf_counter_ns()
        cp = subprocess.run([WRITER,mode,work/'members'/label,output],env=dict(env,**(overrides or {})),
                             capture_output=True,preexec_fn=limits if limit else None,timeout=45)
        elapsed = time.perf_counter_ns()-t
        if cp.returncode:
            return dict(exit=cp.returncode,stderr=cp.stderr.decode(),ns=elapsed)
        assert not cp.stderr,cp.stderr
        length,retained,cloned,fallback = cp.stdout.decode().split()
        return dict(exit=0,ns=elapsed,length=int(length),retained=int(retained),cloned=cloned=='true',fallback=int(fallback))

    def validate(mode,label,prior,extra=None,check_extents=False):
        assert not os.path.lexists(output)
        if prior is not None: os.link(prior,output)
        f = output.open('rb') if prior is not None else None
        if f is not None:
            original=os.fstat(f.fileno())
        try:
            v = invoke(mode,label,extra)
            assert v['exit']==0,v
            assert v['length']==prov[label]['size'] and sha(output)==prov[label]['after'],(v,sha(output),prov[label]['after'])
            assert stat.S_ISREG(output.lstat().st_mode)
            assert stat.S_IMODE(output.stat().st_mode)==0o644
            if f is not None:
                assert os.fstat(f.fileno()).st_ino==original.st_ino!=output.stat().st_ino
                assert hashlib.file_digest(f,'sha256').hexdigest()==sha(prior)
            # Drain writes after stopping the ordinary buffered process clock.
            sync(output)
            if check_extents:
                v['shared_physical_bytes']=shared_bytes(prior,output)
            return v
        finally:
            if f is not None: f.close()
            if os.path.lexists(output): output.unlink()

    controls={}
    for label in labels:
        prior = work/'seeds'/label
        for mode in ('normal','cow'):
            v=validate(mode,label,prior,check_extents=True)
            expect=kind=='btrfs' and mode=='cow'
            assert v['cloned']==expect and ((v['retained']>0)==expect)
            assert (v['shared_physical_bytes']>0)==expect
            if mode=='cow' and kind=='ext4':
                assert v['fallback'] in (18,22,25,95),v
            controls[label+'-'+mode]=v
    label='parser';prior=work/'seeds'/label;size=prior.stat().st_size
    controls['no-incumbent']=validate('cow',label,None)
    assert controls['no-incumbent']['fallback']==2
    for name in ('wrong-middle','larger','shorter','zero','readonly'):
        modified=work/'seeds'/name
        shutil.copyfile(prior,modified)
        with modified.open('r+b') as m:
            if name=='wrong-middle':
                m.seek(size//2);d=m.read(4);m.seek(-4,1);m.write(bytes(x^0xff for x in d))
            if name=='larger':m.seek(0,2);m.write(b'FOREIGN TRAILER'*5000)
            if name=='shorter':m.truncate(size//3)
            if name=='zero':m.truncate(0)
        if name=='readonly':modified.chmod(0o444)
        os.utime(modified,ns=(prior.stat().st_atime_ns,prior.stat().st_mtime_ns))
        before=sha(modified)
        controls[name]=validate('cow',label,modified)
        assert sha(modified)==before
    sentinel=work/'seeds'/'sentinel';sentinel.write_bytes(b'preserve foreign file\n')
    for kind_of_file in ('symlink','fifo','socket'):
        addr=None
        if kind_of_file=='symlink':output.symlink_to(sentinel)
        if kind_of_file=='fifo':os.mkfifo(output)
        if kind_of_file=='socket':
            addr=socket.socket(socket.AF_UNIX)
            directory=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:addr.bind(f'/proc/self/fd/{directory}/{output.name}')
            finally:os.close(directory)
        try:
            v=invoke('cow',label)
            assert v['exit']==0 and not v['cloned'] and sha(output)==prov[label]['after'],v
            assert stat.S_ISREG(output.lstat().st_mode) and sentinel.read_bytes()==b'preserve foreign file\n'
            controls[kind_of_file]=v
        finally:
            if addr:addr.close()
            output.unlink()
    for failing in ('before-rename','limited-write'):
        os.link(prior,output);before=output.stat()
        result=invoke('cow',label,{'STUDY_ABORT_BEFORE_RENAME':'yes'} if failing=='before-rename' else {},failing=='limited-write')
        assert result['exit']!=0,result
        assert output.stat().st_ino==before.st_ino and sha(output)==prov[label]['before']
        assert len(list(output.parent.iterdir()))==1
        controls[failing]=result;output.unlink()
    put(report/'controls.json',controls)
    if kind=='ext4':
        return
    # The preregistered order includes two untimed warm series followed by twelve pairs per label.
    order=json.loads((T/'order.json').read_text())
    rows=[]
    for warm in ('normal','cow'):
        for label in labels:validate(warm,label,work/'seeds'/label)
    for row in order['rows']:
        label=row['library'];pair={}
        for mode in row['order']:
            v=validate(mode,label,work/'seeds'/label)
            assert v['cloned']==(mode=='cow') and (v['retained']>0)==(mode=='cow')
            pair[mode]=v
        rows.append(dict(pair=row['pair'],library=label,order=row['order'],measurements=pair))
    put(report/'pairs.json',rows)


if __name__=='__main__':
    action, *rest = sys.argv[1:]
    os.umask(0o022)
    if action=='prepare':prepare(Path(rest[0]))
    elif action=='run':run(Path(rest[0]),Path(rest[1]),rest[2])
    else:raise ValueError(action)

