"""Publication-stage qualification only. The private supervisor independently supplies the trained image."""
import array,collections,ctypes,errno,fcntl,hashlib,json,os,stat,struct,subprocess,sys,termios,time
from pathlib import Path
src=Path(__file__).resolve().parent;wild=Path(sys.argv[1]).resolve();shim=Path(sys.argv[2]).resolve();d=Path(sys.argv[3]).resolve();d.mkdir();os.chdir(d)
def sha(b):return hashlib.sha256(b).hexdigest()
def fsha(p):return sha(Path(p).read_bytes())
def run(argv,**kw):return subprocess.run(argv,capture_output=True,timeout=15,**kw)
libc=ctypes.CDLL(None,use_errno=True)
def watch(p):
 # The previous visible-output and file-capability qualification records these mutations. Reads are explicitly accounted separately.
 f=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC); assert f>=0; w=libc.inotify_add_watch(f,os.fsencode(p),0x0002|0x0004|0x0008|0x0400);assert w>=0;return f
def read_events(fd):
 try:data=os.read(fd,65536)
 except BlockingIOError:data=b''
 os.close(fd);masks=[];i=0
 while i<len(data):wd,m,c,n=struct.unpack_from('iIII',data,i);masks.append(m);i+=16+n
 return masks
def write_main(n):
 Path('main.c').write_text(f'#include <unistd.h>\n#include <string.h>\nint main(int argc,char**argv){{if(argc>1 && !strcmp(argv[1],"hold"))pause();return {n};}}\n')
 run(['/usr/bin/cc','-c','main.c','-o','main.o']).check_returncode()
write_main(41)
bin=d/'wild-ld';bin.mkdir(); path=bin/'ld.bfd';path.symlink_to(wild)
args=['/usr/bin/cc','-B'+str(bin),'-fuse-ld=bfd','-Wl,--build-id','-Wl,--gc-sections','-o','image','main.o']
env={'LC_ALL':'C','PATH':'/bin:/usr/bin'}
def pick(binary):
 if path.is_symlink():path.unlink()
 path.symlink_to(binary)
def token_count(fd):
 n=array.array('i',[0]);fcntl.ioctl(fd,termios.FIONREAD,n,True);return n[0]
def native(argv,*,t=b'Xyz',image=None,seal=True,worker_env=None):
 pin,w=os.pipe();os.write(w,t)
 extra={ 'CARGO_MAKEFLAGS': f'-j --jobserver-auth={pin},{w}', 'OHM_PROBE_WILD':str(wild),
       'OHM_PROBE_ARGV':str(d/'argv.bin'),'OHM_PROBE_WIDTH':str(d/'width'),'OHM_PROBE_ACTION':str(d/'action')}
 for x in ('argv.bin','width','action'):Path(x).unlink(missing_ok=True)
 held=[pin,w]
 named=None
 if image is not None:
    named=os.memfd_create('trained-elffile',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    os.write(named,image)
    if seal:fcntl.fcntl(named,1033,15)
    held+=[named];extra['OHM_TEST_CERTIFIED_IMAGE_FD']=str(named)
 r=run(argv,env=env|extra|(worker_env or {}),pass_fds=tuple(held))
 for _ in range(100):
    if token_count(pin)==len(t):break
    time.sleep(.001)
 assert token_count(pin)==len(t)
 if t:assert collections.Counter(os.read(pin,len(t)))==collections.Counter(t)
 for fd in held:os.close(fd)
 return r
def cmd(variant):
 return args+(['-Wl,--version-script=missing.map'] if variant=='bad-script' else [])
def statrow():
 try:
    st=Path('image').lstat()
 except FileNotFoundError:return None
 return {'inode':st.st_ino,'dev':st.st_dev,'size':st.st_size,'nlink':st.st_nlink,'mode':oct(st.st_mode),
         'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns,
         'xattrs':os.listxattr('image',follow_symlinks=False),'symlink':os.readlink('image') if stat.S_ISLNK(st.st_mode) else None}
records=[]
for state in ('ordinary','single-worker','hardlink','symlink','user-xattr','changed-bytes','missing','directory','running','bad-script','unsealed','changed-code','readonly','native-sidecar'):
 for kind in ('stock','proof'):
    write_main(41)
    for x in ('image','alias','image.layout'):
        p=Path(x)
        if p.is_dir() and not p.is_symlink():p.rmdir()
        elif p.is_symlink() or p.exists():p.unlink()
    pick(wild)
    tokens=b'' if state=='single-worker' else b'Xyz'
    native(args,t=tokens).check_returncode()
    previous=Path('image').read_bytes(); oldtime=Path('image').stat()
    if state=='hardlink':os.link('image','alias')
    if state=='symlink':os.rename('image','alias');os.symlink('alias','image')
    if state=='user-xattr':os.setxattr('image','user.case',b'present')
    if state=='changed-bytes':
        value=bytearray(previous);value[-1]^=1;Path('image').write_bytes(value);os.utime('image',ns=(oldtime.st_atime_ns,oldtime.st_mtime_ns))
    if state=='missing':Path('image').unlink()
    if state=='directory':Path('image').unlink();Path('image').mkdir()
    held=None
    if state=='running':held=subprocess.Popen([str(d/'image'),'hold'],env=env)
    if state=='changed-code':write_main(83)
    if state=='readonly':os.chmod('image',0o555)
    src_sha=fsha('main.o');inn=statrow()
    fd=watch('image') if inn and Path('image').is_file() else None
    pick(wild if kind=='stock' else shim)
    cp=native(cmd(state),t=tokens,image=previous if kind=='proof' and state!='changed-code' else None,seal=state!='unsealed',worker_env={'WILD_WRITE_LAYOUT':'1'} if state=='native-sidecar' else {})
    masks=read_events(fd) if fd is not None else []
    if held is not None:held.terminate();held.wait(timeout=3)
    out=statrow()
    if Path('image').is_file():now=fsha('image'); runtime=run([str(d/'image')],env=env).returncode
    else:now=runtime=None
    action=Path('action').read_text() if Path('action').exists() else None
    current=(d/'argv.bin').read_bytes() if (d/'argv.bin').is_file() else None
    seen=None if current is None else [s.decode().replace(str(d),'<case>') for s in current.split(b'\0')[:-1]]
    if kind=='proof':
       assert seen is not None and '-plugin' in seen and any(a.endswith('/crti.o') for a in seen) and any(a=='-lc' for a in seen)
    records.append(dict(case=state,arm=kind,status=cp.returncode,expected_before=sha(previous),image_after=now,program_exit=runtime,main_o=src_sha,
      was_same_inode=(inn['inode']==out['inode']) if inn and out else None,ctime_changed=(inn['ctime_ns']!=out['ctime_ns']) if inn and out else None,
      before=inn,after=out,write_events=masks,decision=action,sidecar_sha256=fsha('image.layout') if Path('image.layout').is_file() else None,stdout=cp.stdout.decode('utf8','backslashreplace').replace(str(d),'<case>'),
      stderr=cp.stderr.decode('utf8','backslashreplace').replace(str(d),'<case>'),raw_native_argv_sha=sha(current) if current else None,native_argv=seen))
    print(state,kind,cp.returncode,action,runtime,masks,flush=True)
    (d/'result.json').write_text(json.dumps(records,sort_keys=True,indent=2)+'\n')
