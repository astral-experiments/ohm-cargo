#!/usr/bin/env python3
"""Publish a closed slot to a different, independently bounded filesystem."""
import errno
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile

MIB = 2**20
GIB = 2**30
MANIFEST = ".closed-receipt.json"
BUFFER = MIB

def check(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    if isinstance(path, HeldBody):
        with os.fdopen(path.open_read(), "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

class HeldBody:
    """An ordinary read-only descriptor from the stopped producer's actual namespace."""
    def __init__(self, fd):
        import fcntl
        check(fcntl.fcntl(fd, fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY,
              "expected a read-only descriptor")
        self.fd=fd
        self.original=identity(os.fstat(fd))
        check(stat.S_ISREG(self.original[2]),"native descriptor is not regular")
    def stat(self):
        value=os.fstat(self.fd)
        check(identity(value)==self.original,"captured native descriptor changed")
        return value
    lstat=stat
    def open_read(self):
        self.stat()
        # A new open file description gives each independent pass offset zero.
        fd=os.open("/proc/self/fd/"+str(self.fd),os.O_RDONLY|os.O_CLOEXEC|os.O_NONBLOCK)
        if identity(os.fstat(fd))!=self.original:
            os.close(fd)
            raise ValueError("native descriptor identity changed")
        return fd

def canonical(data):
    return (json.dumps(data, sort_keys=True, separators=(",",":"))+"\n").encode()

def safe_name(name):
    p = PurePosixPath(name)
    check(not p.is_absolute() and bool(p.parts) and str(p)==name and ".." not in p.parts and
          all(all(c.isascii() and (c.isalnum() or c in "._-") for c in v) for v in p.parts),
          "unsafe archive member")
    return name

def sync_dir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def free(path):
    x = os.statvfs(path)
    return x.f_frsize*x.f_bavail

def reserve_file(path, size):
    fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_RDWR, 0o600)
    try:
        os.posix_fallocate(fd, 0, size)
        os.fsync(fd)
        s = os.fstat(fd)
        check(s.st_size==size and s.st_blocks*512>=size, "kernel did not physically reserve all bytes")
    finally:
        os.close(fd)
    sync_dir(path.parent)

def storage_guards(home, scratch, memory, *, entry, home_floor=140*GIB, scratch_floor=140*GIB,
                   receive_margin=384*MIB, scratch_margin=8*MIB,
                   entry_memory=75*GIB, live_memory=52*GIB):
    check(os.stat(home).st_dev!=os.stat(scratch).st_dev, "two independent backing devices required")
    actual=dict(home=free(home),scratch=free(scratch),memory=memory)
    return actual, (actual["home"]>home_floor+(receive_margin if entry else 0) and
                    actual["scratch"]>scratch_floor+(scratch_margin if entry else 0) and
                    memory>(entry_memory if entry else live_memory))

def check_receiver(receiver, spool, home, scratch, image, *, max_total=384*MIB, image_size=383*MIB):
    devices=[p.stat().st_dev for p in (receiver,spool,home,scratch)]
    check(len(set(devices))==4 and image.stat().st_dev==devices[2], "receipt mounts or backing dev incorrect")
    check(receiver.stat().st_uid==os.geteuid() and not os.statvfs(receiver).f_flag&os.ST_RDONLY,
          "receiver must be an owned private writable filesystem")
    n=image.stat(follow_symlinks=False)
    check(stat.S_ISREG(n.st_mode) and n.st_uid==os.geteuid() and n.st_nlink==1 and
          n.st_size==image_size and image_size<=n.st_blocks*512<max_total,
          "unreserved or oversized durable image")
    fs=os.statvfs(receiver)
    check(fs.f_blocks*fs.f_frsize<=image_size,"wrong-sized receiver filesystem")
    return devices

def sources(root, prefixes, extra=None):
    found = {}
    for prefix in prefixes:
        safe_name(prefix)
        base=root/prefix
        check(base.is_dir() and not base.is_symlink(),"missing closed spool directory")
        for parent, dirs, files in os.walk(base, followlinks=False):
            dirs.sort()
            for name in dirs:
                p=Path(parent)/name
                check(stat.S_ISDIR(p.lstat().st_mode),"symlinked source directory")
            for name in files:
                p=Path(parent)/name
                key=safe_name(p.relative_to(root).as_posix())
                check(key not in found and stat.S_ISREG(p.lstat().st_mode),"nonregular or duplicate source")
                found[key]=p
    for key,path in (extra or {}).items():
        check(key.startswith(("failure-artifacts/","registration/")) and key not in found, "invalid special artifact name")
        found[safe_name(key)]=path if isinstance(path,HeldBody) else Path(path)
    check(found and MANIFEST not in found,"no genuine source files")
    return dict(sorted(found.items()))

class HashedInput:
    def __init__(self, stream):
        self.stream=stream
        self.hash=hashlib.sha256()
    def read(self, size=-1):
        data=self.stream.read(size)
        self.hash.update(data)
        return data

def tar_info(name, size):
    t=tarfile.TarInfo(name)
    t.size=size
    t.uid=t.gid=t.mtime=0
    t.mode=0o400
    return t

def write_archive(out, files, tag, protocol):
    entries={}
    with gzip.GzipFile(fileobj=out,mode="wb",mtime=0,filename="",compresslevel=1) as zipped:
        with tarfile.open(fileobj=zipped,mode="w|",format=tarfile.PAX_FORMAT) as tar:
            for key,path in files.items():
                fd=path.open_read() if isinstance(path,HeldBody) else os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
                with os.fdopen(fd,"rb") as source:
                    before=os.fstat(fd)
                    check(stat.S_ISREG(before.st_mode),"closed source was replaced")
                    reader=HashedInput(source)
                    tar.addfile(tar_info(key,before.st_size),reader)
                    check(not source.read(1) and identity(os.fstat(fd))==identity(before)==identity(path.lstat()),
                          "source changed during capture")
                    entries[key]=[before.st_size,reader.hash.hexdigest()]
            result=dict(schema=1,tag=tag,protocol=protocol,files=entries)
            body=canonical(result)
            tar.addfile(tar_info(MANIFEST,len(body)),io.BytesIO(body))
    return result

def reopen(path, expected=None, *, packed_sha=None):
    members={};ledger=None
    before=path.lstat()
    check(stat.S_ISREG(before.st_mode),"invalid published receipt")
    if packed_sha is not None:
        check(digest(path)==packed_sha, "compressed bytes differ from their commitment")
    with path.open("rb") as packed,gzip.GzipFile(fileobj=packed) as unzipped:
        with tarfile.open(fileobj=unzipped,mode="r|") as tar:
            for member in tar:
                name=safe_name(member.name)
                check(member.isreg() and not member.issym() and name not in members and ledger is None,
                      "unexpected, duplicate or late tar entry")
                with tar.extractfile(member) as f:
                    if name==MANIFEST:
                        check(member.size<4*MIB,"unexpected manifest size")
                        ledger=json.loads(f.read())
                    else:
                        h=hashlib.sha256();size=0
                        for block in iter(lambda:f.read(BUFFER),b""):
                            h.update(block);size+=len(block)
                        check(size==member.size,"short member")
                        members[name]=[size,h.hexdigest()]
        # Read through the gzip trailer and verify its CRC too.
        while unzipped.read(BUFFER):
            pass
    check(ledger is not None and ledger["files"]==members and members,"archive payload/manifest mismatch")
    check(expected is None or expected==ledger,"independent source/receipt mismatch")
    check(identity(before)==identity(path.lstat()),"published receipt changed during readback")
    return ledger

class HashSink:
    def __init__(self):
        self.hash=hashlib.sha256();self.size=0
    def write(self,value):
        self.hash.update(value);self.size+=len(value)
        return len(value)
    def tell(self):
        return self.size
    def flush(self):
        pass

def commit_marker(store, tag, value):
    final=store/(tag+".commit.json")
    fd,name=tempfile.mkstemp(prefix="."+tag+"-commit-",dir=store)
    pending=Path(name)
    with os.fdopen(fd,"wb") as out:
        out.write(canonical(value));out.flush();os.fsync(out.fileno())
    os.link(pending,final,follow_symlinks=False);sync_dir(store)
    check(final.read_bytes()==canonical(value),"commit marker readback")
    pending.unlink();sync_dir(store)

def publish(store, tag, protocol, files, *, emergency=None, hard_payload_bytes=384*MIB):
    """The caller quiesces and keeps all original producers until this returns."""
    check(safe_name(tag)==tag and "/" not in tag and len(protocol)==64,"invalid custody identity")
    check(all(path.stat().st_dev!=store.stat().st_dev for path in files.values()),"spool aliases receiver")
    check(not store.is_symlink() and store.stat().st_uid==os.geteuid(),"untrusted output")
    final=store/(tag+".tar.gz")
    marker=store/(tag+".commit.json")
    check(not marker.exists() or final.is_file(),"commit with no archive")
    if final.exists():
        prior=json.loads(marker.read_bytes()) if marker.exists() else None
        existing=reopen(final,packed_sha=prior["sha256"] if prior else None)
        now={k:[v.lstat().st_size,digest(v)] for k,v in files.items()}
        check((existing["tag"],existing["protocol"],existing["files"])==(tag,protocol,now),
              "conflicting retry would change an accepted slot")
        record=dict(path=final.name,sha256=digest(final),bytes=final.stat().st_size,
                    manifest=hashlib.sha256(canonical(existing)).hexdigest(),files=len(files))
        if prior is None:
            # Recover a complete archive whose process stopped before durable commitment.
            witness=HashSink()
            check(write_archive(witness,files,tag,protocol)==existing and witness.size==record["bytes"]
                  and witness.hash.hexdigest()==record["sha256"],"incomplete uncommitted archive")
            commit_marker(store,tag,record)
        else:
            check(prior==record,"committed file metadata changed")
        return dict(**record,reused=True)
    if emergency is not None:
        reserve,minimum=emergency
        check(reserve.stat().st_size==minimum and reserve.stat().st_blocks*512>=minimum,"emergency space missing")
    fd,name=tempfile.mkstemp(prefix="."+tag+"-pending-",dir=store);pending=Path(name)
    # Keep an incomplete candidate and all sources on any error.
    with os.fdopen(fd,"wb") as out:
        ledger=write_archive(out,files,tag,protocol);out.flush();os.fsync(out.fileno())
    check(pending.stat().st_size<=hard_payload_bytes,"encoded receipt exceeds fixed budget")
    reopen(pending,ledger)
    for key,p in files.items():
        check([p.lstat().st_size,digest(p)]==ledger["files"][key],"original source no longer equals archive")
    committed_hash=digest(pending)
    os.link(pending,final,follow_symlinks=False);sync_dir(store)
    reopen(final,ledger,packed_sha=committed_hash)
    pending.unlink();sync_dir(store)
    record=dict(path=final.name,sha256=committed_hash,bytes=final.stat().st_size,
                manifest=hashlib.sha256(canonical(ledger)).hexdigest(),files=len(files))
    commit_marker(store,tag,record)
    return dict(**record,reused=False)

def release_emergency(reserve, minimum):
    fd=os.open(reserve,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        check(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.geteuid() and
              st.st_size==minimum and st.st_blocks*512>=minimum,"invalid emergency reserve")
        os.ftruncate(fd,0);os.fsync(fd)
    finally:
        os.close(fd)
    sync_dir(reserve.parent)
