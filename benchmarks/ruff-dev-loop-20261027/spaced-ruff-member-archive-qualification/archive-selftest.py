"""Mutate actual retained archive structures to prove each ordinary-build comparison rejects them."""
from pathlib import Path
import hashlib,json,os,struct,sys,tempfile
h=Path(__file__).resolve().parent;sys.path.insert(0,str(h))
from member_archive import witness
p=h.parent;source=p/'member-build-matched-native-v1/Bwasm-ty_wasm'
pr=json.loads((source/'restore-repeat-two/product.json').read_bytes())
key,=[n for n in pr['outputs'] if n.endswith('libty_wasm.rlib')]
path=source/'state/target'/key;b=path.read_bytes();ref=witness(path);assert ref['raw']==pr['outputs'][key]
found={};long=b'';pos=8
while pos<len(b):
    label=b[pos:pos+16].strip();z=int(b[pos+48:pos+58]);start=pos+60;end=start+z
    if label==b'//':long=b[start:end]
    if label.startswith(b'/') and label[1:].isdigit():name=long[int(label[1:]):].split(b'/\n',1)[0]
    else:name=label.removesuffix(b'/')
    found[name]=(pos,start,end);pos=end+end%2
results={};root=p/'member-archive-mutation-controls-v1';root.mkdir(mode=0o700)
def check(tag,at,new):
    v=bytearray(b);v[at:at+len(new)]=new;assert len(v)==len(b) and v!=b
    with tempfile.NamedTemporaryFile(dir=root) as f:
        f.write(v);f.flush()
        try:acc=witness(Path(f.name))
        except (AssertionError,ValueError,IndexError,UnicodeError):outcome='rejected'
        else:assert acc['typed']!=ref['typed'];outcome='changed fingerprint'
    results[tag]=dict(offset=at,before_sha256=hashlib.sha256(b).hexdigest(),after_sha256=hashlib.sha256(v).hexdigest(),outcome=outcome)
o1,o2=[n.encode() for n in ref['original_names'][:2]]
check('object-content',found[o1][1]+70,bytes([b[found[o1][1]+70]^1]))
# The first ar member is the big-endian GNU symbol index.
index=68;cnt=struct.unpack_from('>I',b,index)[0];oldpos=struct.unpack_from('>I',b,index+4)[0]
replacement=found[o1][0] if found[o1][0]!=oldpos else found[o2][0]
check('symbol-provider',index+4,struct.pack('>I',replacement))
def section(raw,section):
    sht=struct.unpack_from('<Q',raw,40)[0];stride,num,names=struct.unpack_from('<HHH',raw,58);fields=[struct.unpack_from('<IIQQQQIIQQ',raw,sht+i*stride) for i in range(num)]
    st=fields[names];text=raw[st[4]:st[4]+st[5]];return next(f for f in fields if text[f[0]:].split(b'\0',1)[0]==section)
start,end=found[b'lib.rmeta'][1:];sec=section(b[start:end],b'.rmeta');at=start+sec[4]+25
check('metadata-payload',at,bytes([b[at]^1]))
start,end=found[b'lib.rmeta-link'][1:];sec=section(b[start:end],b'.rmeta-link');q=b.index(o1,start+sec[4],start+sec[4]+sec[5]);check('inconsistent-link-name',q,b'x')
assert len(results)==4 and cnt==ref['projection']['symbol_count']
(root/'results.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n');print(json.dumps(results,sort_keys=True))
