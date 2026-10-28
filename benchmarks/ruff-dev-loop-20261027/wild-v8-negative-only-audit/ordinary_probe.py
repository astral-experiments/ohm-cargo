"""Tiny ordinary-user Linux probe for the released and frozen candidate Wild."""
import hashlib, json, os, re, shutil, stat, subprocess, tempfile
from pathlib import Path

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    baseline=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
    tools={'stock':baseline/'wild-package-v7/shipping-wild','candidate':baseline/'wild-package-v8/candidate-wild'}
    hashes={k:sha(v) for k,v in tools.items()}
    assert hashes==dict(stock='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5',
                        candidate='c813de15da27872ce0a294a321053674fa8e7c08b4443798b831a6da5d37374c')
    assert os.geteuid()!=0 and int(re.search(r'(?m)^CapEff:\s*(\w+)',Path('/proc/self/status').read_text())[1],16)==0
    os.sched_setaffinity(0,{max(os.sched_getaffinity(0))})
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}
    start='.globl _start\n_start: call value@PLT\n mov %eax,%edi\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n'
    value='.globl value\n.type value,@function\nvalue: mov $42,%eax\n ret\n.section .note.GNU-stack,"",@progbits\n'
    old='helper.0123456789abcdef.aaaaaaa.rcgu.o';new='helper.0123456789abcdef.bbbbbbb.rcgu.o'
    result={'tools':hashes,'user_id':os.geteuid(),'capabilities':0,'dynamic':{},'file_updates':{}}
    with tempfile.TemporaryDirectory(prefix='ohm-wild-v8-closure-') as temp:
        root=Path(temp)
        for role,tool in tools.items():
            d=root/role;d.mkdir()
            def cmd(argv,**kw):return subprocess.run(argv,cwd=d,text=True,capture_output=True,env=env,check=True,**kw)
            for name,src in [('main',start),('lib',value)]:
                (d/(name+'.s')).write_text(src);cmd(['as','--64','-o',name+'.o',name+'.s'])
            cmd(['/usr/bin/ld','-shared','-o',old,'lib.o'])
            assert 'SONAME' not in cmd(['readelf','-dW',old]).stdout
            dynsha=sha(d/old);result['dynamic'][role]=[]
            for i,name in enumerate([old,new,new]):
                if i==1:os.rename(d/old,d/new)
                assert sha(d/name)==dynsha
                args=[str(tool),'-pie','-dynamic-linker','/lib64/ld-linux-x86-64.so.2','-o','program','main.o',name]
                trace=d/f'trace{i}'
                rc=subprocess.run(['strace','-f','-yy','-s','40','-e','trace=utimensat,ftruncate,fchmod,fchmodat,write,pwrite64,mmap,openat',
                                   '-o',str(trace),*args],cwd=d,env=env|{'WILD_REUSE_LOG':str(d/f'events{i}')},
                                  capture_output=True,text=True)
                if rc.returncode:raise RuntimeError((role,i,rc.returncode,rc.stderr))
                parsed=cmd(['readelf','-dW','program']).stdout
                needed=re.findall(r'Shared library: \[(.*?)\]',parsed)
                run=subprocess.run(['./program'],cwd=d,env=env|{'LD_LIBRARY_PATH':'.'},text=True,capture_output=True)
                events=(d/f'events{i}').read_text().splitlines() if (d/f'events{i}').exists() else []
                calls=[]
                for line in trace.read_text().splitlines():
                    if '<'+str(d/'program')+'>' not in line:continue
                    m=re.match(r'^\d+\s+([a-zA-Z0-9_]+)\(',line)
                    if m and m[1]!='openat':
                        calls.append({'call':m[1],'writable_mapping':m[1]=='mmap' and 'PROT_WRITE' in line})
                result['dynamic'][role].append({'input':name,'identical_dso_sha256':dynsha,'argc':len(args),'link_exit':rc.returncode,
                         'program_sha256':sha(d/'program'),'needed':needed,'program_exit':run.returncode,
                         'loader_named_old_missing':old in run.stderr,'cache_events':[x.split('\t')[0] for x in events],
                         'calls_on_verified_output_fd':calls})
        for op in ['utime','truncate','pwrite','truncate_and_chmod']:
            path=root/('setid-'+op);path.write_bytes(b'x');os.chmod(path,0o4755)
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
            try:
                before=os.fstat(fd)
                if op=='utime':os.utime(fd)
                elif op=='pwrite':assert os.pwrite(fd,os.pread(fd,1,0),0)==1
                else:
                    os.ftruncate(fd,before.st_size)
                    if op=='truncate_and_chmod':os.fchmod(fd,os.fstat(fd).st_mode|0o111)
                after=os.fstat(fd)
                result['file_updates'][op]=[oct(stat.S_IMODE(before.st_mode)),oct(stat.S_IMODE(after.st_mode)),
                                            before.st_ino==after.st_ino,os.pread(fd,1,0)==b'x']
            finally:os.close(fd)
    return result

if __name__=='__main__':print(json.dumps(main(),indent=2,sort_keys=True))
