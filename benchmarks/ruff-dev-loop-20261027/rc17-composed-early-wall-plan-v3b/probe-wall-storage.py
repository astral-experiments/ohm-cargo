from pathlib import Path
import errno, fcntl, hashlib, json, os, shutil, subprocess, tempfile
p=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
fs=lambda path:subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',path],text=True).strip()
seeds={x:fs(p/x) for x in ('ruff-evaluation-v2/seed','wall-launch-v1','wall-qa-v1')}; assert set(seeds.values())=={fs(p)}=={'ext4'}
with tempfile.TemporaryDirectory(prefix='wall-storage-probe-',dir=p) as d:
    a,b,c=(Path(d)/x for x in ('original','clone','full-copy'))
    a.write_bytes(bytes(range(128))*8192);base=sha(a);flag=None
    with a.open('rb') as af,b.open('w+b') as bf:
        try:fcntl.ioctl(bf.fileno(),0x40049409,af.fileno())
        except OSError as e:
            assert e.errno in (errno.EOPNOTSUPP,errno.EXDEV,errno.ENOTTY,errno.EINVAL);flag=e.errno
        else:
            assert sha(b)==base and a.stat().st_ino!=b.stat().st_ino;bf.write(b'Z');bf.flush();assert sha(a)==base and sha(b)!=base
    subprocess.run(['cp','-a','--reflink=never','--',a,c],check=True);assert sha(c)==base and a.stat().st_dev==c.stat().st_dev and a.stat().st_ino!=c.stat().st_ino and c.stat().st_mtime_ns==a.stat().st_mtime_ns
    with c.open('r+b') as cf:cf.write(b'Z');cf.flush();os.fsync(cf.fileno())
    assert sha(c)!=base==sha(a);stats=os.statvfs(p)
    print(json.dumps(dict(filesystems=seeds,host_fs=fs(p),ficlone_errno=flag,ficlone_supported=flag is None,full_copy_isolated=True,same_device=True,source=base,modified_copy=sha(c),file_bytes=a.stat().st_size,free_bytes=shutil.disk_usage(p).free,block_bytes=stats.f_frsize,first_failure=sha(p/'early-scheduler-wall-admission-v1.failure'),scored_commands=0,result_root_exists=(p/'early-scheduler-wall-rc17-v1').exists()),sort_keys=True,indent=2))
