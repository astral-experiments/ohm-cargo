"""Locate both original rejected-slot ELF byte streams; inspect actual differing bytes and run callers."""
from pathlib import Path
import json,hashlib,struct,subprocess,sys
r=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027/ron-first-shipping-20261027');out=Path(sys.argv[1])
def h(b):return hashlib.sha256(b).hexdigest()
def inspect(buf):
    p=struct.unpack_from('<Q',buf,40)[0];w,n,si=struct.unpack_from('<HHH',buf,58);assert w==64
    hs=[struct.unpack_from('<IIQQQQIIQQ',buf,p+i*w) for i in range(n)];lo=hs[si][4];ids={buf[lo+s[0]:buf.index(0,lo+s[0])].decode():i for i,s in enumerate(hs)}
    ix=ids['.rodata'];m=hs[ids['.note.gnu.build-id']];at=m[4];ln,d,t=struct.unpack_from('<III',buf,at);assert ln==4 and t==3 and buf[at+12:at+16]==b'GNU\0'
    return {'entsize':hs[ix][9],'entsize_offset':p+ix*w+56,'build_id_desc_offset':at+16,'build_id_desc_size':d,'rodata_flags':hs[ix][2],'rodata_type':hs[ix][1],'rodata_payload':h(buf[hs[ix][4]:hs[ix][4]+hs[ix][5]])}
def product(name):
    d=r/'results'/name/'settled';data=json.loads((d/'native.json').read_bytes());k,=[k for k in data if '/ruff_python_formatter/' in k and Path(k).name.startswith('fixtures-')];f=r/'states'/name/'target'/Path(k).relative_to('$RUN/native-target');a=f.read_bytes();assert h(a)==data[k]['raw'];return a,f
a,fa=product('qualify-A');b,fb=product('score-03-1-A');A,B=inspect(a),inspect(b)
assert {A['entsize'],B['entsize']}=={0,1} and len(a)==len(b)
delta=[i for i in range(len(a)) if a[i]!=b[i]]
assert set(delta)<=(set(range(A['entsize_offset'],A['entsize_offset']+8)) | set(range(A['build_id_desc_offset'],A['build_id_desc_offset']+A['build_id_desc_size']))) and len(delta)>1
assert A['rodata_payload']==B['rodata_payload'] and A['rodata_flags']==B['rodata_flags']
wt='/home/dev-user/code/oss/ruff-ohm-empty-test-h4-20261027/crates/ruff_python_formatter';outs=[]
for exe in (fa,fb):
    prefix=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--chdir',wt,'--setenv','CARGO_MANIFEST_DIR',wt,'--setenv','INSTA_WORKSPACE_ROOT',str(Path(wt).parents[1]),'--setenv','INSTA_UPDATE','no','--',exe];ls=subprocess.run([*prefix,'--list'],capture_output=True,check=True)
    names=[s.removesuffix(': test') for s in ls.stdout.decode().splitlines() if s.endswith(': test')]
    # The datatest harness can format its list differently; require a real selectable case.
    assert names,(ls.stdout[:250],ls.stderr[:250]);one=subprocess.run([*prefix,'--exact',names[0]],capture_output=True,check=True)
    assert names[0].encode() in one.stdout and b'1 passed' in one.stdout,(names[0],one.stdout[-150:])
    outs.append({'listed':len(names),'list_sha256':h(ls.stdout),'test':names[0],'passed':True,'status':one.returncode})
assert outs[0]==outs[1]
out.write_text(json.dumps({'from':{'sha256':h(a),'size':len(a),**A},'to':{'sha256':h(b),'size':len(b),**B},'differing_raw_byte_offsets':delta,'ordinary_callers':outs},indent=2,sort_keys=True)+'\n')
