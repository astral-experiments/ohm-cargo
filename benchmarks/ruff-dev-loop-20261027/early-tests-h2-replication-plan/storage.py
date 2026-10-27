"""Private tar snapshots, full source and timestamp checks, and a live physical-space floor."""
from pathlib import Path
import base64,contextlib,fcntl,gzip,hashlib,json,os,shutil,signal,stat,subprocess,time
from products import sha
G=2**30;root=Path.home()/'.cache/ohm-233-position-qualified-20261027/finished-producer-first-selection-h2-v3';ram=Path('/dev/shm/ohm-finished-producer-selection-h2-v3')
def guard():
    t=shutil.disk_usage('/dev/shm').free;disk=shutil.disk_usage(root).free
    m={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if ':' in s}
    assert t>25*G and disk>25*G and m['MemAvailable']>35*G and m['SwapTotal']==m['SwapFree']==0,(t,disk,m['MemAvailable'],m['SwapTotal'])
    return {'tmpfs_free':t,'home_free':disk,'available_ram':m['MemAvailable'],'swap_total':m['SwapTotal']}
def watch(argv,**opts):
    guard()
    with subprocess.Popen(argv,start_new_session=True,**opts) as pr:
        try:
            while pr.poll() is None:
                try:pr.wait(timeout=1.5)
                except subprocess.TimeoutExpired:guard()
        except BaseException:
            with contextlib.suppress(ProcessLookupError):os.killpg(pr.pid,signal.SIGTERM)
            raise
        assert pr.returncode==0,(argv[:2],pr.returncode)
    guard()
def content(t):
    out=[];groups={};links={}
    for p in [t,*sorted(t.rglob('*'))]:
        st=p.lstat();rel=str(p.relative_to(t));attrs=sorted((k,base64.b64encode(os.getxattr(p,k,follow_symlinks=False)).decode()) for k in os.listxattr(p,follow_symlinks=False))
        q=[rel,stat.S_IFMT(st.st_mode),stat.S_IMODE(st.st_mode),st.st_uid,st.st_gid,st.st_mtime_ns,attrs]
        if p.is_symlink():q.append(os.readlink(p))
        elif p.is_file():
            k=(st.st_dev,st.st_ino)
            if k not in groups:groups[k]=[rel,sha(p),0,st.st_nlink];links[k]=st.st_nlink
            first,h,count,ln=groups[k];groups[k][2]+=1;q.extend([st.st_size,h,first])
        else:assert p.is_dir(),p
        out.append(q)
    assert all(a[2]==a[3] for a in groups.values()),'external hardlink crossed the private snapshot'
    return out
def commitment(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def cleanup(t):
    assert t.parent==ram and (t.name.startswith('work-') or t.name.startswith('snapshot-')) and not t.is_symlink()
    mount=[Path(line.split()[4]) for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    assert all(not m.is_relative_to(t) for m in mount)
    if t.is_dir():shutil.rmtree(t)
    else:t.unlink()
def archive(t,out,records):
    data=content(t);h=commitment(data);records.write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode(),compresslevel=1,mtime=0))
    watch(['tar','--format=posix','--xattrs','--acls','--numeric-owner','--sparse','-I','zstd -T2 -3','-cf',str(out),'-C',str(t),'.'],stdin=subprocess.DEVNULL)
    return h
def restore(out,t,expected):
    assert not t.exists();t.mkdir(mode=0o700)
    watch(['tar','--delay-directory-restore','--xattrs','--acls','--same-permissions','--numeric-owner','-I','zstd -T2','-xf',str(out),'-C',str(t)],stdin=subprocess.DEVNULL)
    actual=commitment(content(t));assert actual==expected,('restored metadata, contents, symlinks or hardlinks',actual,expected)
    return actual
