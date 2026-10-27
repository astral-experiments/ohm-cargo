"""A private-symbol change in a completely unselected archive object, with fixed thread count."""
from pathlib import Path
import hashlib,json,os,shutil,struct,subprocess
from runpy import run_path
p=Path(__file__).resolve().parent;d=p.parent;q=p/'dormant-symbol-groups';q.mkdir()
wild=Path('/mnt/devbox-scratch/dev-user/ohm-packaged-16-macro-20261027/installed-sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')
assert hashlib.sha256(wild.read_bytes()).hexdigest()=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
probe=p/'target/release/wild';api=run_path(str(d/'audit.py'));gold=q/'gold';gold.mkdir();log=q/'log';log.mkdir()
def run(cmd,env=None):
 r=subprocess.run(cmd,cwd=q,env=env,capture_output=True);assert r.returncode==0,(cmd,r.stderr,r.stdout);return r.stdout
sha=lambda b:hashlib.sha256(b).hexdigest()
def dump(b):
 off=struct.unpack_from('<Q',b,40)[0];sz,n,nm=struct.unpack_from('<HHH',b,58);hs=[struct.unpack_from('<IIQQQQIIQQ',b,off+i*sz) for i in range(n)];q=hs[nm][4];s={b[q+h[0]:b.index(0,q+h[0])].decode():(i,h) for i,h in enumerate(hs)}
 k,ro=s['.rodata'];_,note=s['.note.gnu.build-id'];z=note[4]+16;nn=int.from_bytes(b[note[4]+4:note[4]+8],'little');en=off+k*sz+56
 a=bytearray(b);a[z:z+nn]=bytes(nn);a[en:en+8]=bytes(8)
 return {'raw':sha(b),'bytes':len(b),'normalized':sha(a),'rodata_entsize':ro[9],'build_id':b[z:z+nn].hex()}
stack='.section .note.GNU-stack,"",@progbits\n'
fixed={
 'main':'.text\n.globl _start\n_start:\n movzbl ordinary(%rip),%edi\n movzbl merged(%rip),%eax\n add %eax,%edi\n mov $60,%eax\n syscall\n'+stack,
 'one':'.section .rodata.first,"a",@progbits\n.globl ordinary\nordinary: .byte 1\n'+stack,
 'two':'.section .rodata.cst8,"aM",@progbits,8\n.globl merged\nmerged: .byte 41\n .zero 7\n'+stack}
for k,v in fixed.items():
 (q/(k+'.s')).write_text(v);run(['as','--64','-o',k+'.o',k+'.s'])
name='fixtures-579109038f0f72c0';args=['--threads=4','--build-id','-o',name,'main.o','one.o','two.o','libdormant.a']
ans={}
for label,count in [('small',0),('large',8000),('restored',0)]:
 row=q/label;row.mkdir()
 (q/'unused.s').write_text('.text\n.globl dormant\ndormant: .byte 0\n'+''.join(f'.local pad_{i}\n.set pad_{i},dormant\n' for i in range(count))+stack)
 run(['as','--64','-o','unused.o','unused.s']);run(['ar','rcs','libdormant.a','unused.o'])
 archive=(q/'libdormant.a').read_bytes();members,indices=api['archive'](archive);assert indices==[('dormant','unused.o')]
 z=run([str(wild),*args],dict(os.environ,WILD_WRITE_LAYOUT='1'));assert not z
 actual=(q/name).read_bytes();f=shutil.copyfile(q/name,row/'stock.elf');shutil.copyfile(q/(name+'.layout'),row/'layout')
 sel=api['decode_layout']((row/'layout').read_bytes())[0]
 sn=[Path(path).name for path,ent,sections,tmp in sel];assert set(sn)=={'main.o','one.o','two.o'} and len(sn)==3,sn
 native=subprocess.run([q/name],capture_output=True);assert native.returncode==42 and not native.stdout and not native.stderr
 initial='train' if label=='small' else 'selected'
 run([str(probe),*args],dict(os.environ,OHM_DEDENT_PILOT_ROOT=str(gold),OHM_DEDENT_PILOT_MODE=initial,OHM_DEDENT_PILOT_TRACE=str(log)))
 ps,=log.iterdir();report=ps.read_text().split();ps.rename(row/'probe-marker')
 got=(q/name).read_bytes();shutil.copyfile(q/name,row/'diagnostic.elf')
 if label=='small':
  assert got==actual;blob=gold/(name+'.multi');blob.write_bytes(got);(gold/(blob.name+'.blake3')).write_bytes(run([str(p/'gold-b3'),str(blob)]))
 ans[label]={'symbol_count':len(run(['nm','unused.o']).splitlines()),'index':indices,'archive':sha(archive),'stock':dump(actual),'diagnostic':dump(got),'marker':report,'selected':sn,'program_exit':native.returncode}
 print(label,count,ans[label]['stock'],report,flush=True)
(q/'result.json').write_text(json.dumps(ans,indent=2)+'\n')
assert ans['small']['stock']==ans['restored']['stock'] and ans['small']['stock']['normalized']==ans['large']['stock']['normalized']
assert ans['small']['stock']['rodata_entsize']!=ans['large']['stock']['rodata_entsize'] and ans['large']['marker'][2]=='true' and ans['large']['diagnostic']['raw']!=ans['large']['stock']['raw']
