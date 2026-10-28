from pathlib import Path
import hashlib,json,os,struct,sys,mmap
HERE=Path(__file__).resolve().parent
W=HERE.parent
sys.path.insert(0,str(W))
sys.path.insert(0,str(W/'tree-count'))
from edit_holdout import BEFORE,EDIT_PATH,REVISION
from measure import BENCH,RUST,digest
from identical import audit_native
ROOT=BENCH/'edit-cumulative-wall-test'
SRC=ROOT/'source';TARGET=ROOT/'target';SEED=ROOT/'seed-target';EDIT=SRC/EDIT_PATH
HOME_DIR=Path(json.loads((W/'edit-holdout-cumulative-wall/test/protocol.json').read_text())['cargo_home'])
SLOTS=BENCH/'eight-selected-roles-20261028'
WRAP=W/'tree-count/wrap.py'
COUNTER=W/'edit-link-profile/native-instrument/count.py'
ARMS={'base':(W/'pgo-confirmation-v2/bin/base',W/'bin/wild-baseline'),'candidate':(W/'pgo-confirmation-v2/bin/guard-stack',W/'wild-prefix-v2/v2-wild')}
CMD=['test','--no-run','--locked','--offline','-j8']
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def jread(path):return json.loads(path.read_text())
def edit_bytes(original,letter,n):
    replace=('{\n                component == cellar && (next == formula || next == OsStr::new('
             f'"uv-sum-{letter}{n:02}"))\n            }}')
    assert original.count(BEFORE.encode())==1
    return original.replace(BEFORE.encode(),replace.encode())
def meta(p):
    st=p.lstat();return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns]
def seed_tree():
    h=hashlib.sha256();n=0
    for root,dirs,files in os.walk(SEED):
        dirs.sort();files.sort()
        for name in dirs+files:
            p=Path(root)/name;st=p.lstat()
            h.update(json.dumps([str(p.relative_to(SEED)),st.st_mode,st.st_size,st.st_mtime_ns,os.readlink(p) if p.is_symlink() else None],separators=(',',':')).encode()+b'\n');n+=1
    return {'entries':n,'metadata_sha256':h.hexdigest(),'markers':{n:digest(SEED/n) for n in ['.rustc_info.json','CACHEDIR.TAG','.ohm-built-registry-ready']}}
def input_state():
    return {'edit_sha256':digest(EDIT),'edit_stat':meta(EDIT),'source_dir':meta(SRC),'cargo_home_dir':meta(HOME_DIR),'prior_cargo_slot':meta(ROOT/'bin/cargo'),'prior_cargo_sha256':digest(ROOT/'bin/cargo'),'target_absent':not os.path.lexists(TARGET),'seed':seed_tree()}
def artifacts(paths):
    out={}
    for p in sorted(paths):
        p=Path(p);real=digest(p);canonical=real;masked=None
        if p.name=='uv-23905aefc33b1c4d':
            with p.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as buf:
                assert buf[:6]==b'\x7fELF\x02\x01';tab=struct.unpack_from('<Q',buf,40)[0];w,n,ns=struct.unpack_from('<HHH',buf,58)
                names,ls=struct.unpack_from('<QQ',buf,tab+ns*w+24);strings=buf[names:names+ls];skip=[]
                for i in range(n):
                    off=tab+i*w;ni=struct.unpack_from('<I',buf,off)[0];name=strings[ni:strings.index(0,ni)]
                    if name==b'.rodata':
                        ent=struct.unpack_from('<Q',buf,off+56)[0];assert ent in (0,8);skip.append((off+56,off+57));masked={'rodata_entsize':ent}
                    elif name==b'.note.gnu.build-id':
                        b=struct.unpack_from('<Q',buf,off+24)[0];nsz,dsz,t=struct.unpack_from('<III',buf,b);assert (nsz,dsz,t)==(4,32,3) and buf[b+12:b+16]==b'GNU\0';skip.append((b+16,b+48))
                assert len(skip)==2 and masked
                z=hashlib.sha256();last=0
                for a,b in sorted(skip):z.update(memoryview(buf)[last:a]);last=b
                z.update(memoryview(buf)[last:]);canonical=z.hexdigest()
        out[p.name]={'size':p.stat().st_size,'sha256':real,'canonical_sha256':canonical,'allowed_variable_fields':masked}
    return out
