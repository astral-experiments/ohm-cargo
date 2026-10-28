from pathlib import Path
import json,os,struct,subprocess,sys
p=Path(sys.argv[1]);d=p/sys.argv[2];d.mkdir();cand=p/sys.argv[3];sdk=(Path(sys.argv[4]).resolve()/'lib/rustlib/x86_64-unknown-linux-gnu/bin')
f=lambda raw:d/os.fsdecode(raw)
def asm(obj,code):
 q=subprocess.run(['as','--64','-o',obj],input=(code+'\n.section .note.GNU-stack,"",@progbits\n').encode(),capture_output=True);assert not q.returncode
entry=d/'entry.o';asm(entry,'.text\n.globl _start\n_start:call value; mov %eax,%edi;mov $60,%eax;syscall')
correct=f(b'value-\xff.o');decoy=f('value-�.o'.encode())
asm(correct,'.text\n.globl value\nvalue:mov $41,%eax;ret');asm(decoy,'.text\n.globl value\nvalue:mov $99,%eax;ret')
ver=d/'vscript';ver.write_text('VERS_1 { global: value; local: *; };\n')
sdkroot=d/'fake-sdk';sdkroot.mkdir();search=sdkroot/os.fsdecode(b'lib-\xff');decdir=sdkroot/'lib-�';search.mkdir();decdir.mkdir()
for a,o in [(search,correct),(decdir,decoy)]:subprocess.run(['ar','crs',a/'libwhich.a',o],check=True)
rows=[]
for tool,pr in [('stock',[sdk/'wild-ld/ld.bfd']),('tested',[cand]),('lld',[sdk/'rust-lld','-flavor','gnu'])]:
 def call(name,argv,exe=None):
  q=subprocess.run([*pr,'--threads=1',*argv],cwd=d,capture_output=True);row={'tool':tool,'case':name,'rc':q.returncode,'panic':b'panicked at'in q.stderr,'stderr':q.stderr.decode(errors='backslashreplace').replace(str(d),'<work>'),'stdout_native':os.fsencode(correct)in q.stdout,'runtime':subprocess.run([exe]).returncode if exe and q.returncode==0 else None};rows.append(row);return row
 exe=f(b'prog-\xfe');dep=d/'deps.d'; dep.unlink(missing_ok=True)
 row=call('dependency-and-trace',['--dependency-file',dep,'--trace','-o',exe,entry,correct],exe)
 if row['rc']==0:
  data=dep.read_bytes();row.update(dep_native_input=os.fsencode(correct)in data,dep_native_output=os.fsencode(exe)in data,dep_has_decoy=os.fsencode(decoy)in data,dep_complete_hex=data.replace(os.fsencode(d),b'WORK').hex())
 row=call('forced-sysroot',['--sysroot',sdkroot,b'-L=/lib-\xff','-o',exe,entry,'-lwhich'],exe)
 lib=f(b'base-\xf1.so');row=call('version-output',['-shared','--version-script',ver,'-o',lib,correct]); 
 if row['rc']==0:
  data=lib.read_bytes();shoff=struct.unpack_from('<Q',data,40)[0];ents,n=struct.unpack_from('<HH',data,58);secs=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*ents)for i in range(n)];vd=next(ss for ss in secs if ss[1]==0x6ffffffd);st=secs[vd[6]];names=data[st[4]:st[4]+st[5]];verflags=struct.unpack_from('<H',data,vd[4]+2)[0];assert verflags&1;aux=struct.unpack_from('<I',data,vd[4]+12)[0];ix=struct.unpack_from('<I',data,vd[4]+aux)[0];base=names[ix:names.index(b'\0',ix)];row.update(version_base_hex=base.hex(),version_is_raw=base==b'base-\xf1.so',version_is_decoy=base=='base-�.so'.encode())
 (d/'complete.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
print([(r['tool'],r['case'],r['rc'],r.get('runtime'),r.get('dep_native_input'),r.get('version_is_raw'))for r in rows])
