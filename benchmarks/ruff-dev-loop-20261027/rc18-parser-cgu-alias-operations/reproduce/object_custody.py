"""Contrast hardlink, descriptor, reopened path and cross-device copy after byte replacement."""
import errno
import hashlib
import json
import os
import shutil
import subprocess as sp
import sys
import tempfile
from pathlib import Path

def h(data):
    return hashlib.sha256(data).hexdigest()

def run(args,**kw):
    return sp.run(args,check=True,stdout=sp.PIPE,stderr=sp.PIPE,**kw)

def test(root):
    local, foreign = root
    code=local/'answer.c'
    obj=local/'work-product.o'
    main=local/'consumer.c'
    main.write_text('#include <stdio.h>\nextern int answer(void); int main(void){printf("%d\\n",answer());return 0;}\n')
    def compile_object(result):
        code.write_text(f'int answer(void){{return {result};}}\n')
        run(['cc','-O2','-c',code,'-o',obj])
        return obj.read_bytes()
    a=compile_object(17);b=compile_object(29)
    assert len(a)==len(b) and a!=b
    def consume(label,p,fd=None):
        exe=local/(label+'.exe')
        args=['cc',main,p,'-o',exe]
        run(args,pass_fds=() if fd is None else (fd,))
        value=int(run([exe]).stdout.strip())
        return {'value':value,'input_sha256':h(Path(p).read_bytes()),'output_sha256':h(exe.read_bytes())}
    def fdname(fd):
        return '/proc/self/fd/'+str(fd)
    obj.write_bytes(a);stamp=obj.stat()
    hard=local/'logical-archive-name.o';os.link(obj,hard)
    observed={}
    with obj.open('rb') as lease:
        new=local/'replacement';new.write_bytes(b);os.utime(new,ns=(stamp.st_atime_ns,stamp.st_mtime_ns));os.replace(new,obj)
        assert obj.stat().st_ino!=stamp.st_ino and obj.stat().st_mtime_ns==stamp.st_mtime_ns
        for lab,p,fd in [('physical-hardlink',hard,None),('borrowed-path',obj,None),('early-fd',fdname(lease.fileno()),lease.fileno())]:
            observed[lab]=consume(lab,p,fd)
    assert [observed[z]['value']for z in ('physical-hardlink','borrowed-path','early-fd')]==[17,29,17]
    obj.write_bytes(a);cross=foreign/'copied-archive-name.o'
    assert obj.stat().st_dev!=foreign.stat().st_dev
    try:
        os.link(obj,cross)
    except OSError as ex:
        assert ex.errno==errno.EXDEV
    else:
        raise AssertionError('cross-device hard link unexpectedly succeeded')
    shutil.copyfile(obj,cross)
    stamp=obj.stat()
    with obj.open('rb') as lease:
        obj.write_bytes(b);os.utime(obj,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert (obj.stat().st_dev,obj.stat().st_ino,obj.stat().st_mtime_ns)==(stamp.st_dev,stamp.st_ino,stamp.st_mtime_ns)
        for lab,p,fd in [('physical-copy',cross,None),('borrowed-path',obj,None),('early-fd',fdname(lease.fileno()),lease.fileno())]:
            observed['cross-'+lab]=consume('cross-'+lab,p,fd)
    assert [observed['cross-'+z]['value']for z in ('physical-copy','borrowed-path','early-fd')]==[17,29,29]
    return {'stock_cc_sha256':h(Path(shutil.which('cc')).read_bytes()),'object_size':len(a),'variant_sha256':[h(a),h(b)],'cross_device_errno':errno.EXDEV,'observed':observed}
if __name__=='__main__':
    with tempfile.TemporaryDirectory(dir=sys.argv[1]) as a,tempfile.TemporaryDirectory(dir=sys.argv[2]) as b:
        print(json.dumps(test([Path(a),Path(b)]),sort_keys=True,indent=2))
