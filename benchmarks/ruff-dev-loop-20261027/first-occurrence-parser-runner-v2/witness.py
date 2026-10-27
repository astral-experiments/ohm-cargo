"""Read native ELF identities, a checked Ron observer, and nonblocking native-image open events."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ctypes, hashlib, json, os, re, struct, subprocess
from common import CARGO_HOME, TARGET, SHARED, FROZEN, MODE_COUNTS, need, sha

MARK=b'ohm-foreign-span-bytes'

def stamp(path):
    st=Path(path).stat()
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]

def as_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def audit_json(path,mode):
    rows=[json.loads(line) for line in path.read_bytes().splitlines() if line]
    need(rows[-1]=={'reason':'build-finished','success':True},path)
    arts=[r for r in rows if r['reason']=='compiler-artifact']
    need(len(arts)==MODE_COUNTS[mode][0],(mode,len(arts)))
    executable=sorted({r['executable'] for r in arts if r['executable']})
    paths={p for r in arts if r['package_id'].startswith('path+') for p in r['filenames'] if Path(p).suffix in {'','.so'}}
    elfs=[]
    for n in sorted(paths):
        with open(n,'rb') as f:
            if f.read(4)==b'\x7fELF':elfs.append(n)
    need(set(executable)<=set(elfs) and (len(elfs),len(executable))==((15,6) if mode=='build' else (110,102)),(mode,len(elfs),len(executable)))
    roster=sorted([json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in arts]);messages=sorted([json.dumps([r['package_id'],r['target']['name'],r['message']],sort_keys=True) for r in rows if r['reason']=='compiler-message'])
    return {'units':len(arts),'dirty':sorted(r['target']['name'] for r in arts if not r['fresh']),'elf':elfs,'executables':executable,'roster_sha256':as_digest(roster),'message_sha256':as_digest(messages),'roster':roster,'messages':messages}

def find_observers():
    found=[];count=0
    for d in (TARGET,SHARED):
        for p in d.rglob('*.d'):
            if not p.is_file():continue
            count+=1
            if MARK not in p.read_bytes():continue
            # Normal Ohm `out` is directly beside `fingerprint` for each root.
            n=p.stem.split('-')[0].replace('_','-')
            fpdir=p.parent.parent/'fingerprint'
            c=[f for f in fpdir.glob('dep-*') if f.is_file() and MARK in f.read_bytes()]
            need(len(c)==1,('missing or ambiguous translated observer',str(p),[str(x) for x in c]));found.append({'raw':str(p),'encoded':str(c[0]),'name':n})
    # Some project/cache layouts can expose the identical file by a second alias; require one inode.
    unique={tuple(stamp(o['encoded'])[:2]):o for o in found}
    return count,sorted(unique.values(),key=lambda o:o['encoded'])

def read_proofs(records,helper,require_complete=True):
    checked=[]
    for rec in records:
        raw,encoded=Path(rec['raw']),Path(rec['encoded']);data=encoded.read_bytes()
        need(MARK in data and MARK in raw.read_bytes(),('observer marker',rec))
        tag=data[-41:-37]==b'OBS1';complete=tag and data[-33]==1
        if require_complete:need(complete,('incomplete observer',rec,len(data)))
        if tag:
            digest=subprocess.check_output([str(helper)],input=data[:-32]).decode().strip()
            need(digest==data[-32:].hex(),('invalid BLAKE3 observer',rec))
        checked.append(dict(rec,complete=complete,sha256=hashlib.sha256(data).hexdigest(),raw_sha256=sha(raw),stamp=stamp(encoded),raw_stamp=stamp(raw)))
    return checked

def directory_inventory(path):
    if not path.is_dir():return {'files':0,'digest':as_digest([])}
    rows=[(str(p.relative_to(path)),*stamp(p),sha(p)) for p in sorted(path.rglob('*')) if p.is_file()]
    return {'files':len(rows),'digest':as_digest(rows)}

def trusted_ancestors(path):
    uid=os.geteuid();chain=[]
    for p in (path,*path.parents):
        st=p.lstat();m=st.st_mode
        trusted=p.is_dir() and not p.is_symlink() and st.st_uid in {uid,0} and (m&0o022==0 or (st.st_uid==0 and m&0o1000!=0))
        chain.append({'path':str(p),'uid':st.st_uid,'mode':oct(m&0o7777),'trusted':trusted})
    return chain

class OpenWatch:
    """Linux calls fsnotify_open on a successful exec. Extra opens conservatively reject the sample."""
    def __init__(self,paths):
        self.lib=ctypes.CDLL(None,use_errno=True);self.fd=self.lib.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
        need(self.fd>=0,('inotify_init1',ctypes.get_errno()));self.paths={}
        for p in paths:
            wd=self.lib.inotify_add_watch(self.fd,os.fsencode(p),0x20|0x400|0x800)
            need(wd>=0,('inotify_add_watch',p,ctypes.get_errno()));self.paths[wd]=str(p)
    def take(self):
        events=[]
        while True:
            try:data=os.read(self.fd,65536)
            except BlockingIOError:break
            offset=0
            while offset<len(data):
                wd,mask,_,n=struct.unpack_from('iIII',data,offset);offset+=16+n
                need(wd in self.paths and mask==0x20,('inotify invalidated/overflow',wd,mask));events.append(self.paths[wd])
        return events
    def close(self):os.close(self.fd)

def rustc_open_calibration(rustc,env):
    w=OpenWatch([rustc]);q=subprocess.run([str(rustc),'--version'],env=env,capture_output=True,check=True);events=w.take();w.close()
    need(events==[str(rustc)],('missing native exec-open calibration',events,q.stdout));return events
