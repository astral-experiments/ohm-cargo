"""Run with only the four required capabilities in a disposable nosuid, networkless container."""
import array,collections,ctypes,fcntl,hashlib,json,os,struct,subprocess,termios,time
from pathlib import Path
sha=lambda b:hashlib.sha256(b).hexdigest()
assert os.geteuid()==0 and os.statvfs('/work').f_flag & os.ST_NOSUID
assert sha(Path('/stock').read_bytes())=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
libc=ctypes.CDLL(None,use_errno=True)
record={}
def run(a,arm,env=None,fds=(),**kw):
 return subprocess.run(a,cwd=arm,env=env,user=1000,group=1000,extra_groups=[],capture_output=True,pass_fds=fds,timeout=12,**kw)
for arm in ['stock','candidate']:
 d=Path('/work')/arm;d.mkdir();os.chown(d,1000,1000)
 c=run(['as','--64','-o','entry.o'],d,input=b'.globl _start\n.text\n_start: xor %edi,%edi; mov $60,%eax; syscall\n.section .note.GNU-stack,"",@progbits\n')
 c.check_returncode()
 base=['-m','elf_x86_64','--build-id','--gc-sections','-o','image','entry.o']
 def launch(tool,extra):
    r,w=os.pipe();os.fchown(r,1000,1000);os.write(w,b'Xyz')
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','CARGO_MAKEFLAGS':f'-j --jobserver-auth={r},{w}',
         'OHM_PROBE_WILD':'/stock','OHM_PROBE_ARGV':str(d/'argv.bin'),'OHM_PROBE_ACTION':str(d/'action'),'OHM_PROBE_WIDTH':str(d/'width')}
    if extra is not None:env['OHM_TEST_CERTIFIED_IMAGE_FD']=str(extra)
    native=run([tool,*base],d,env,(r,w) if extra is None else (r,w,extra))
    for _ in range(100):
        n=array.array('i',[0]);fcntl.ioctl(r,termios.FIONREAD,n,True)
        if n[0]==3: break
        time.sleep(.001)
    assert n[0]==3 and collections.Counter(os.read(r,3))==collections.Counter(b'Xyz')
    os.close(r);os.close(w);native.check_returncode()
 launch('/stock',None)
 p=d/'image';body=p.read_bytes();ino=p.stat().st_ino
 fd=os.memfd_create('old-elf',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING);os.write(fd,body);fcntl.fcntl(fd,1033,15)
 os.setxattr(p,'security.capability',struct.pack('<5I',0x02000000,1,0,0,0));assert 'security.capability' in os.listxattr(p)
 watch=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC);assert watch>=0 and libc.inotify_add_watch(watch,os.fsencode(p),0x2|0x4|0x8|0x400)>=0
 launch('/stock' if arm=='stock' else '/candidate',None if arm=='stock' else fd);os.close(fd)
 b=os.read(watch,65536);os.close(watch);off=0;masks=[]
 while off<len(b):
    _,m,_,n=struct.unpack_from('iIII',b,off);off+=16+n;masks.append(m)
 print('after',arm,os.listxattr(p),ino,p.stat().st_ino,p.read_bytes()==body,masks,(d/'action').read_text() if (d/'action').exists() else None, file=__import__('sys').stderr)
 assert 'security.capability' not in os.listxattr(p) and p.read_bytes()==body and ino==p.stat().st_ino
 act=(d/'action').read_text() if arm=='candidate' else None
 assert not act or act=='output-xattrs'
 record[arm]=dict(capability_was_present=True,capability_after=False,action=act,same_inode=True,mode=oct(p.stat().st_mode),sha256=sha(body),inotify=masks)
assert record['stock']['inotify']==record['candidate']['inotify']==[2,4,8]
print(json.dumps(record,sort_keys=True,indent=2))
