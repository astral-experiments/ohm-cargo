"""Observe ordinary upstream manifest-cache hits/writes and cross-version union stability."""
import ast, fcntl, hashlib, json, os, re, shutil, stat, subprocess, sys
from pathlib import Path

H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028')
phase=sys.argv[1]
assert phase in ('qualify','score')
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
U=read(H/'union-plan.json')
assert sha(Path(__file__))==U['coordinator']
for key, filename in U['prerequisite_digests'].items():
    assert sha(H/key)==filename,key
W=H/'h8-trust.py'
ns={'__file__':str(W)}
code=W.read_text().split('os.umask(0o077);os.sched_setaffinity(0,range(8))')[0]
exec(compile(code,str(W),'exec'),ns)
g,s,product,old,save=[ns[n] for n in ['g','s','product','old','save']]
Q=H/'union-native-v3'
out=H/'qualified-261-workspace-union'
g['out']=out
names=('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2')
home=H/'cargo-home'
keys={k:(name,arm) for name,pair in read(H/'offline-key-families.json')['each_expected_key'].items() for arm,k in pair.items()}
def inventory():
    r={}
    for n in names:
        d=home/n
        assert d.is_dir() and not d.is_symlink()
        for p in sorted(d.iterdir()):
            st=p.lstat()
            assert stat.S_ISREG(st.st_mode) and not st.st_mode&0o077,p
            r[n+'/'+p.name]=[sha(p),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns]
        assert any(i.startswith(n+'/') for i in r),n
    return r
def previous():
    old()
    assert not (H/'qualified-261-workspace-trusted/qualify.json').exists()
    assert not any((H/u).is_file() for u in ['trusted-ancestor-v2/normal-candidate/record.json','trusted-ancestor-v2/repaired.json'])
    for n in ('qualified-261-workspace','qualified-261-workspace-trusted'):
        assert not any((H/n).glob('*/ir/*/record.json'))
def check_outputs():
    product()
    assert shutil.disk_usage(s.P).free>=60*2**30 and shutil.disk_usage(H).free>=70*2**30
def parse_trace(d):
    # Single-PID files make unfinished/resumed syscall correlation unnecessary for file writes.
    out={'exec':[],'reads':{},'install':[],'writes':[],'trace':{}}
    reads={n:set() for n in names}; tmp_keys={}
    for p in sorted(d.glob('trace.*')):
        out['trace'][p.name]=sha(p)
        for line in p.read_text(errors='strict').splitlines():
            if not re.search(r'\)\s+=\s+\d',line):continue
            if line.startswith('execve("'):
                out['exec'].append(line.split('"',2)[1]);continue
            if not any(str(home/n)+'/' in line for n in names):continue
            syscall=line.partition('(')[0]
            if syscall=='openat' and 'O_RDONLY' in line:
                for n in names:
                    m=re.search(re.escape(str(home/n))+'/([a-f0-9]{3,64})"',line)
                    if m:reads[n].add(m[1])
                continue
            opened=syscall in ('openat','open') and re.search(r'\bO_(?:WRONLY|RDWR|CREAT|TRUNC)\b',line)
            if not opened and syscall not in ('rename','renameat','renameat2','unlink','unlinkat','link','linkat','write','pwrite64','writev','copy_file_range','truncate','ftruncate'):continue
            if syscall in ('write','writev','pwrite64','copy_file_range'):
                # This implementation writes magic, key, digest, payload separately.
                j=re.match(r'write\(\d+<([^>]+)>, "(.*)", 32\)\s+=\s+32$',line)
                if j and j[1] not in tmp_keys:
                    value=ast.literal_eval('b"'+j[2]+'"').hex()
                    assert len(value)==64,value
                    tmp_keys[j[1]]=value
                # Do not export written application data. The original strace is retained under d.
                out['writes'].append([p.name,syscall,line.partition(',')[0],line.rpartition(' = ')[-1]])
            else:
                out['writes'].append([p.name,syscall,line])
                if syscall.startswith('rename') or syscall.startswith('link'):
                    paths=re.findall(r'"([^"]+)"',line)
                    if len(paths)>=2 and any(paths[-1].startswith(str(home/n)+'/') for n in names):
                        k=tmp_keys.get(paths[-2])
                        out['install'].append([p.name,Path(paths[-1]).name,k,keys.get(k)])
    # Only the rustup dispatcher and the admitted real Cargo process may execute.
    assert len(out['exec'])==2 and Path(out['exec'][0]).name=='cargo' and Path(out['exec'][1]).resolve()==g['binary'],out['exec']
    assert all(reads.values()),{n:len(v) for n,v in reads.items()}
    out['reads']={n:sorted(v) for n,v in reads.items()}
    return out
def observe(stage,arm):
    if arm=='stock':ns['direct_switch'](s.prepare.old/'release17/sdk/bin/cargo')
    else:g['switch'](arm)
    check_outputs();previous()
    d=Q/(stage+'-'+arm);d.mkdir()
    pre=inventory();save(d/'before.json',pre);paths=g['depfiles']('workspace');stamps=g['stamps'](paths)
    c=['strace','-ff','-qq','-yy','-x','-s','1024','-e','trace=%file,write,writev,pwrite64,copy_file_range,ftruncate','-o',str(d/'trace'),*s.cmds('workspace'),'--message-format=json']
    with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
        p=subprocess.run(c,cwd=s.cwd('workspace'),env=s.env('workspace'),stdout=so,stderr=se)
    assert p.returncode==0,(d,p.returncode)
    stderr=(d/'stderr').read_bytes();assert b'Finished' in stderr and b'Compiling ' not in stderr and b'Checking ' not in stderr
    raw=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()];units=[r for r in raw if r.get('reason')=='compiler-artifact']
    assert len(units)==501 and all(r['fresh'] for r in units) and not any('ron@' in u['package_id'] for u in units)
    assert sorted({n for r in units for n in r['filenames'] if Path(n).is_file()})==sorted(ns['v']['products'])
    assert sorted(Path(n).name for n,v in g['stamps'](paths).items() if stamps[n]!=v)==['libruff_wasm.d','libty_wasm.d']
    check_outputs();after=inventory();save(d/'after.json',after)
    t=parse_trace(d);save(d/'observed.json',t)
    record=dict(stage=stage,arm=arm,argc=len(c),units=len(units),products=len(ns['v']['products']),depfiles=len(paths),source=ns['v']['source'],git_index=ns['v']['index_sha'],cargo=sha(g['binary']),before=sha(d/'before.json'),after=sha(d/'after.json'),observed=sha(d/'observed.json'),stdout=sha(d/'stdout'),stderr=sha(d/'stderr'),exec=t['exec'],reads={n:len(l) for n,l in t['reads'].items()},installs=t['install'],writes=len(t['writes']))
    save(d/'record.json',record)
    return pre,after,record
def qualify():
    assert not Q.exists() and not out.exists() and not any((H/f).exists() for f in ['scoring.grant','trust.scoring.grant','union.scoring.grant'])
    previous();check_outputs()
    current=inventory();expected=read(H/'rejected-union-v2.json')
    assert {k.split('/',1)[1]:v[0] for k,v in current.items() if k.startswith(names[1]+'/')}=={k:r['sha'] for k,r in expected['all_current'].items()}
    assert {k.split('/',1)[1]:v[0] for k,v in current.items() if k.startswith(names[0]+'/')}==expected['git'] and stat.S_IMODE(H.stat().st_mode)==0o700
    Q.mkdir();rows=[];violations=[]
    for arm in ('stock','parent','candidate'):
        _,union,r=observe('prime',arm);rows.append(r)
    save(Q/'primed.json',union)
    for arm in ('stock','parent','candidate'):
        before,after,r=observe('verify',arm);rows.append(r)
        if before!=union or after!=union or r['writes']:violations.append([arm,before==union,after==union,r['writes'],r['installs']])
    decision=dict(eligible=not violations,failures=violations,rows=[sha(Q/(r['stage']+'-'+r['arm'])/'record.json') for r in rows],prime=sha(Q/'primed.json'),zero_scored=True)
    save(Q/'union.json',decision)
    if violations: return
    g['main']();assert inventory()==union;previous();check_outputs()
    save(Q/'terminal.json',dict(union=sha(Q/'union.json'),anchor=sha(out/'workspace/qual/anchor.json'),qual=sha(out/'qualify.json')))
def score():
    assert (H/'union.scoring.grant').read_text().strip()==sha(H/'union-plan.json')
    assert (Q/'terminal.json').is_file() and read(Q/'union.json')['eligible'] and not any(out.glob('*/ir/*/record.json'))
    union=read(Q/'primed.json');orig=g['proofs']
    def immutable():
        assert inventory()==union
        return orig()
    previous();check_outputs();g['proofs']=immutable;g['main']();immutable();previous();check_outputs()
    save(Q/'scored.json',dict(record=sha(out/'score.json'),anchor=sha(Q/'terminal.json')))
os.umask(0o077);os.sched_setaffinity(0,range(8))
with s.LOCK.open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);(qualify if phase=='qualify' else score)()
