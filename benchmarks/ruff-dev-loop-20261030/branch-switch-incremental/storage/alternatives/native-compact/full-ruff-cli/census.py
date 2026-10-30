#!/usr/bin/env python3
"""Count allocated storage of the two settled, owned Cargo build directories."""
import hashlib,json,os,stat,sys,time
def tree(fds,start):
    expected_dev=os.fstat(fds[0]).st_dev;found={};other_device=[];running=0;digest=hashlib.sha256();working=[]
    def check():
        assert time.monotonic()-start<45,'census deadline exceeded'
    def enter(f,parts,bucket):
        nonlocal running
        os.lseek(f,0,os.SEEK_SET)
        with os.scandir(f) as it:items=sorted(it,key=lambda z:os.fsencode(z.name))
        for name in ['.']+[e.name for e in items]:
            st=os.fstat(f) if name=='.' else os.stat(name,dir_fd=f,follow_symlinks=False)
            path=parts if name=='.' else parts+(name,)
            if st.st_dev!=expected_dev:
                other_device.append(path);continue
            if name!='.' and stat.S_ISDIR(st.st_mode):
                if name.endswith('-working'):working.append('/'.join(path))
                fd=os.open(name,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME|os.O_CLOEXEC,dir_fd=f)
                try:enter(fd,path,bucket)
                finally:os.close(fd)
                continue
            key=(st.st_dev,st.st_ino);inc='incremental' in path
            prev=found.setdefault(key,[st.st_blocks*512,st.st_size,0,0,stat.S_IFMT(st.st_mode),False])
            assert prev[0]==st.st_blocks*512 and prev[1]==st.st_size
            prev[2]|=bucket
            if inc:prev[3]|=bucket
            else:prev[5]=True
            digest.update(os.fsencode('/'.join(path))+b'\0'+str((st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_blocks,st.st_mtime_ns,st.st_ctime_ns)).encode()+b'\n')
            running+=1
            if running%350==0:check()
    check()
    for i,n in enumerate(['products','shared']):enter(fds[i],(n,),1<<i)
    check();assert not other_device and not working,(other_device[:2],working[:5])
    def val(pred):
        vv=[v for v in found.values() if pred(v)]
        return {'allocated_bytes':sum(v[0] for v in vv),'logical_bytes_unique_inodes':sum(v[1] for v in vv),'inodes':len(vv)}
    return {'name_plus_inode_ledger_sha256':digest.hexdigest(),'path_entries':running,'all':val(lambda v:True),'products':val(lambda v:v[2]&1),'shared':val(lambda v:v[2]&2),'both_roots_same_inode':val(lambda v:v[2]==3),'all_incremental':val(lambda v:v[3]),'incremental_also_named_outside':val(lambda v:v[3] and v[5]),'incremental_only':val(lambda v:v[3] and not v[5]),'working_directories':working}

def census(products, shared):
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOATIME|os.O_CLOEXEC
    files=[]
    try:
        for path in (products,shared):
            files.append(os.open(path,flags))
        states=[os.fstat(fd) for fd in files]
        assert all(st.st_uid==os.getuid() for st in states)
        assert states[0].st_dev==states[1].st_dev and states[0].st_ino!=states[1].st_ino
        start=time.monotonic()
        first=tree(files,start)
        assert first==tree(files,start),'directory or inode state changed after the first complete census'
        return first
    finally:
        for fd in files:os.close(fd)
if __name__=='__main__':
    assert len(sys.argv)==3,'usage: python3 -IB census.py TARGET_DIR SHARED_BUILD_DIR'
    print(json.dumps(census(*sys.argv[1:]),indent=2,sort_keys=True))
