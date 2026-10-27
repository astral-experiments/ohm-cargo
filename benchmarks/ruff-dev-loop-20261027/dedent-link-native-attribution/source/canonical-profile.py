"""Unscored phase attribution; same real saved inputs, explicit worker widths / separate output."""
import hashlib,json,os,re,statistics,struct,subprocess,time
from pathlib import Path
d=Path(__file__).resolve().parent
p=d/'canonical-profile';p.mkdir()
wild=Path('/mnt/devbox-scratch/dev-user/ohm-packaged-16-macro-20261027/installed-sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(wild.read_bytes())=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
r=json.loads((d/'closure/reversed/receipt.json').read_text())
def on_disk(f):
 data=f.read_bytes();tbl=struct.unpack_from('<Q',data,40)[0];z,l,st=struct.unpack_from('<HHH',data,58);hs=[struct.unpack_from('<IIQQQQIIQQ',data,tbl+i*z) for i in range(l)];q=hs[st][4]
 e=[h[9] for h in hs if data[q+h[0]:data.index(b'\0',q+h[0])]==b'.rodata']
 assert len(e)==1
 return sha(data),e[0]
rows=[]
for n,img in r['commands'].items():
 run=Path(img['saved'])
 assert sha(run.read_bytes())==img['script_sha']
 for t in (1,2,3,4,5,6,7,8):
  f=p/(n+'.bin')
  for i in range(3):
   path=p/(n+f'.{t}.{i}');a=[str(run),str(wild),'--','--time',f'--threads={t}','--dynamic-linker','/lib64/ld-linux-x86-64.so.2']
   before=time.perf_counter_ns();z=subprocess.run(a,capture_output=True,env=dict(os.environ,OUT=str(f)));time_ns=time.perf_counter_ns()-before
   path.write_bytes(z.stdout+z.stderr); assert 'Write' in (z.stdout+z.stderr).decode(), (z.stdout,z.stderr); assert z.returncode==0,(a,z.stderr)
   dig,ent=on_disk(f); assert dig==r['actual'][n]['actual_elf_sha256'] or (n.startswith('ruff_python_parser-') and t==1 and dig=='ff1cdc736d8eaf6dc261d3a8007b2b2fc1c046e875a73bca84eb94a2410b93a2'), (n,t,dig); rows.append({'name':n,'width':t,'iter':i,'elf':dig,'rodata_entsize':ent,'ns':time_ns,'phase':path.name})
  print(n,t,[(a['elf'][:12],a['rodata_entsize']) for a in rows[-3:]],flush=True)
(p/'stage.json').write_text(json.dumps(rows,indent=2)+'\n')
