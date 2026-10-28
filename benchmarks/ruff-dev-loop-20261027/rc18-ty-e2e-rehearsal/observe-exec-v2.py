"""Observe successful exec stops and preserve the stock linker's transient inputs without a wrapper."""
import ctypes, errno, hashlib, json, os, signal, stat, sys
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()
def sha_file(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
libc=ctypes.CDLL(None,use_errno=True)
libc.ptrace.argtypes=(ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p)
libc.ptrace.restype=ctypes.c_long
def ptr(req,pid,data=0):
    if libc.ptrace(req,pid,None,ctypes.c_void_p(data))==-1:
        n=ctypes.get_errno()
        if n==errno.ESRCH and req==7:return
        raise OSError(n,os.strerror(n),(req,pid))

def observe(out, linker, argv):
    out.mkdir()
    expected=linker.stat()
    jobs=[];counts={'full':0,'link-only':0,'wild':0};statuses={}; symbols=out/'transient';symbols.mkdir()
    def field(path):return path.read_bytes().rstrip(b'\0').split(b'\0')
    def text(v):return os.fsdecode(v)
    def private_file(p):
        obj=p.read_bytes();assert len(obj)<4*1024*1024
        h=sha(obj);dest=symbols/h
        if dest.exists(): assert dest.read_bytes()==obj
        else: dest.write_bytes(obj)
        return {'size':len(obj),'sha256':h}
    def event(pid):
        p=Path('/proc')/str(pid);actual=(p/'exe').stat()
        flags=field(p/'cmdline'); xp=Path(os.readlink(p/'exe'))
        if xp.name=='rustc' and b'--crate-name' in flags:
            kind='link-only' if b'-Zlink-only' in flags or b'link-only' in flags else 'full'
            counts[kind]+=1
            jobs.append({'kind':kind,'pid':pid,'unit':text(flags[flags.index(b'--crate-name')+1]),'cmdline_sha256':sha((p/'cmdline').read_bytes())})
        if (actual.st_dev,actual.st_ino)!=(expected.st_dev,expected.st_ino):return
        opts=list(map(text,flags)); out_name=opts[opts.index('-o')+1]; cwd=Path(os.readlink(p/'cwd')); raw_env=(p/'environ').read_bytes()
        tr={}; dirs={}; ordinary={}
        for opt in opts[1:]:
            f=None
            if opt.endswith('/symbols.o'):f=Path(opt);kind='symbols'
            elif opt.startswith('-plugin-opt=-fresolution='):f=Path(opt.split('=',2)[2]);kind='gcc-resolution'
            elif opt.startswith('-L') and opt.rstrip('/').endswith('/raw-dylibs'):
                d=Path(opt[2:]); dirs[str(d)]=sorted(q.name for q in d.iterdir())
            elif opt.startswith('/') and (opt.endswith('.rlib') or opt.endswith('.o')):
                f1=Path(opt);s=f1.stat()
                assert stat.S_ISREG(s.st_mode)
                ordinary[opt]=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
            if f is not None:
                assert kind not in tr;tr[kind]=dict(path=str(f),**private_file(f))
        assert set(tr)=={'symbols','gcc-resolution'} and len(dirs)==1 and list(dirs.values())==[[]],(out_name,tr,dirs)
        counts['wild']+=1
        # The caller supplies a minimal environment with no registry or GitHub credentials.
        fields={text(s.split(b'=',1)[0]):text(s.split(b'=',1)[1]) for s in raw_env.rstrip(b'\0').split(b'\0')}
        assert not any(any(secret in key.upper() for secret in ['TOKEN','PASSWORD','CREDENTIAL','PRIVATE_KEY']) for key in fields),list(fields)
        out_path=Path(out_name)
        if not out_path.is_absolute():
            out_path=cwd/out_path
        try:
            output_stat=out_path.lstat()
        except FileNotFoundError:
            output_at_exec={'state':'absent'}
        else:
            output_at_exec={'state':'present','dev':output_stat.st_dev,'ino':output_stat.st_ino,
                            'mode':output_stat.st_mode,'nlink':output_stat.st_nlink,'size':output_stat.st_size,
                            'uid':output_stat.st_uid,'gid':output_stat.st_gid,'mtime_ns':output_stat.st_mtime_ns,
                            'ctime_ns':output_stat.st_ctime_ns,'symlink':os.readlink(out_path) if out_path.is_symlink() else None}
            try:
                output_at_exec['xattrs']=sorted(os.listxattr(out_path,follow_symlinks=False))
            except OSError as e:
                output_at_exec['listxattr_errno']=e.errno
        parent_stat=out_path.parent.stat()
        output_at_exec['parent']=[parent_stat.st_dev,parent_stat.st_ino,parent_stat.st_mode]
        entry={'kind':'wild','pid':pid,'argv':opts,'out':out_name,'cwd':str(cwd),'env':fields,'affinity':sorted(os.sched_getaffinity(pid)),
               'output_at_exec':output_at_exec,'transient':tr,'directories':dirs,'persistent_operands':ordinary,
               'exe_device':actual.st_dev,'exe_inode':actual.st_ino}
        (out/(str(pid)+'.json')).write_text(json.dumps(entry,sort_keys=True)+'\n')
        jobs.append({'kind':'wild','pid':pid,'out':out_name,'cmdline_sha256':sha((p/'cmdline').read_bytes())})
    child=os.fork()
    if child==0:
        ptr(0,0);os.kill(os.getpid(),signal.SIGSTOP);os.execvp(argv[0],argv)
    pid,status=os.waitpid(child,0);assert pid==child and os.WIFSTOPPED(status)
    # Follow fork/vfork/clone/exec events. No single-step or syscall emulation.
    ptr(0x4200,child,2|4|8|16|0x100000);ptr(7,child)
    root_status=None;tracked=set()
    while True:
        try:pid,status=os.waitpid(-1,0x40000000)
        except ChildProcessError:break
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            code=os.waitstatus_to_exitcode(status)
            if pid==child:root_status=code
            if pid in tracked:statuses[pid]=code
            continue
        assert os.WIFSTOPPED(status)
        sig=os.WSTOPSIG(status);ev=status>>16
        if ev==4:
            old=len(jobs);event(pid)
            if len(jobs)>old:tracked.add(pid)
        deliver=0 if ev or sig in (signal.SIGTRAP,signal.SIGSTOP) else sig
        ptr(7,pid,deliver)
    assert root_status is not None
    assert tracked==set(statuses) and all(c==0 for c in statuses.values()),statuses
    (out/'summary.json').write_text(json.dumps({'root_exit':root_status,'counts':counts,'jobs':jobs,'statuses':statuses,
         'stock_linker_sha256':sha_file(linker)},sort_keys=True,indent=2)+'\n')
    return root_status
if __name__=='__main__':
    raise SystemExit(observe(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3:]))
