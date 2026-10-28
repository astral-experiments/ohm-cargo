from pathlib import Path
import json,subprocess
here=Path(__file__).resolve().parent
code="""from pathlib import Path
import hashlib,json,socket,struct
assert socket.gethostname()=='charlie-ohm-cargo5-build-1025';p=Path('/mnt/devbox-scratch/dev-user/ohm-composed-early-observer-cargo-20261028');old=p.parent/'ohm-observer-consumption-cargo-v2-20261028';read=lambda f:json.loads(f.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
a=(old/'cargo').read_bytes();b=(p/'observer/cargo').read_bytes();r0=read(old/'receipt.json');r1=read(p/'observer/receipt.json');r2=read(p/'composed/receipt.json')
assert sha(a)==r0['cargo']=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322' and sha(b)==r1['cargo']=='49e68b3427afb4c373dec712c758461255f545f201af5fdab91f8597d37be3fd' and sha((p/'composed/cargo').read_bytes())==r2['cargo']=='813ba8a480bc6047d2effde2edff5fe5990781904ff453815ddc71aeb5e0e754'
assert r0['compiler']==r1['builder']==r2['builder'] and r0['pgo']==r1['pgo']==r2['pgo'] and r0['version']==r1['version']==r2['version'] and read(p/'combined-build-inputs.json')['files']['observer']==r1['changed']
def parse(blob):
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',blob);phoff=h[5];shoff=h[6];phsz,phnum=h[9:11];shsz,shnum,shname=h[11:14];assert (phsz,shsz)==(56,64)
    prog=[struct.unpack_from('<IIQQQQQQ',blob,phoff+i*phsz) for i in range(phnum)];secs=[struct.unpack_from('<IIQQQQIIQQ',blob,shoff+i*shsz) for i in range(shnum)];strings=secs[shname];strtab=blob[strings[4]:strings[4]+strings[5]];byname={strtab[s[0]:strtab.index(bytes([0]),s[0])].decode():s for s in secs}
    return h,prog,byname
x,pa,sa=parse(a);y,pb,sb=parse(b);assert x[:6]+x[7:]==y[:6]+y[7:] and pa==pb and set(sa)==set(sb)
for k in sa:
    u=sa[k];v=sb[k]
    if k not in ('.symtab','.strtab','.note.gnu.build-id'):
        assert u==v and (u[1]==8 or a[u[4]:u[4]+u[5]]==b[v[4]:v[4]+v[5]]),k
    if k in ('.symtab','.strtab'): assert not (u[2]&2 or v[2]&2),k
note=sa['.note.gnu.build-id'];assert note==sb['.note.gnu.build-id'];lo=note[4];n=note[5];assert a[lo:lo+16]==b[lo:lo+16] and struct.unpack_from('<III',a,lo)==(4,32,3) and a[lo+12:lo+16]==b'GNU\\0'
mask=((40,48),(lo+16,lo+n));st=[];proof=[]
for ph in pa:
    if ph[0]!=1:continue
    o,size=ph[2],ph[5];xa=bytearray(a[o:o+size]);xb=bytearray(b[o:o+size]);different=sum(v!=w for v,w in zip(xa,xb));assert len(xa)==len(xb)==size
    for m,e in mask:
        start=max(m,o);end=min(e,o+size)
        if start<end:xa[start-o:end-o]=bytes(end-start);xb[start-o:end-o]=bytes(end-start)
    assert xa==xb,(o,size);proof.append(dict(offset=o,bytes=size,flags=ph[1],mismatched=different,normalized=sha(xa)))
assert sum(x['mismatched'] for x in proof)>0 and any(x['flags']&1 and x['mismatched']==0 for x in proof)
res=dict(control=r0['cargo'],replayed_control=r1['cargo'],composed=r2['cargo'],builder=r1['builder'],pgo=r1['pgo'],stamp=r1['stamp'],elf_size=[len(a),len(b)],program_headers=len(pa),image=proof,exceptions=['e_shoff','GNU build ID descriptor','.symtab','.strtab'],section_count=len(sa))
print(json.dumps(res,sort_keys=True))
"""
r=subprocess.run(['dbox','ssh','charlie-ohm-cargo5-build-1025','--no-tmux','--','/usr/bin/python3','-B','-c',code],capture_output=True);assert r.returncode==0,r.stderr[-1100:];(here/'replayed-control-loads.json').write_bytes(r.stdout);print(json.loads(r.stdout))
