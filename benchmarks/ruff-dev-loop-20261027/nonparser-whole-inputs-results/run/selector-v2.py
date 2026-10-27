"""Do two genuine Ty test codegen object names carry externally observable information even when their contents match?"""
from pathlib import Path
import hashlib,json,os,re,shutil,struct,subprocess
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';S=Path('/dev/shm/ohm-nonparser-whole-inputs-20261027/state/test');P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');T=P/'native-target';sdk=P/'frozen-toolchain/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld';Xout=Q/'genuine-cgu-name-selector-v2';Xout.mkdir();J=lambda x:json.loads(x.read_bytes());sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest();save=lambda p,x:p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n');m=J(Q/'input-attribution/residual-boundaries/ty-diagnostic.json');res=[];wild=sdk/'ld.bfd';
def eligible(b):
 if b[:6]!=b'\x7fELF\x02\x01':return []
 shoff=struct.unpack_from('<Q',b,40)[0];ents,n,si=struct.unpack_from('<HHH',b,58);sh=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*ents) for i in range(n)];st=sh[si][4];bad={s[7] for s in sh if s[1] in (4,9)};result=[]
 for i,s in enumerate(sh):
  pos=st+s[0];name=b[pos:b.index(b'\0',pos)].decode();
  if i not in bad and s[1]==1 and s[2]&2 and not s[2]&0x200 and 1<=s[5]<=126 and name.startswith('.rodata') and re.fullmatch(r'[a-zA-Z0-9._-]+',name):result.append((name,s[5]))
 return sorted(result,key=lambda k:(abs(42-k[1]),k[0]))
for w in m:
 if not w['output'].startswith(('cli-','self_environment-')):continue
 d=Xout/w['output'];d.mkdir();pids=w['physical_summary']['wild_pids'];l=[J(Q/'native-live'/(str(v)+'.json')) for v in pids];pick=None
 for a,b in zip(l[0]['argv'],l[1]['argv']):
  if a==b or not a.endswith('.rcgu.o') or not b.endswith('.rcgu.o') or Path(a).name==Path(b).name:continue
  if l[0]['captures'].get(a,{}).get('sha256')!=l[1]['captures'].get(b,{}).get('sha256'):continue
  if not Path(b).is_relative_to(T):continue
  src=S/'target'/Path(b).relative_to(T);
  if not src.is_file() or sha(src)!=l[1]['captures'][b]['sha256']:continue
  sections=eligible(src.read_bytes());
  if sections:pick=(a,b,src,sections[0]);break
 if pick is None:res.append({'target':w['output'],'ineligible':'no retained genuine matching .rcgu.o with a bounded relocation-free read-only section'});continue
 a,b,src,(section,n)=pick;ob=[]
 for raw in (a,b):
  x=d/Path(raw).name; shutil.copyfile(src,x);ob.append(x)
 assert sha(ob[0])==sha(ob[1])==l[0]['captures'][a]['sha256'];asm=d/'start.s';asm.write_text('.section .text._start,"ax",@progbits\n.global _start\n_start:\n  leaq picked_end(%rip), %rdi\n  leaq picked_start(%rip), %rax\n  subq %rax, %rdi\n  movl $60, %eax\n  syscall\n.section .note.GNU-stack,"",@progbits\n');undefined=[v.strip() for v in subprocess.check_output(['nm','-j','--undefined-only',str(ob[0])]).decode().splitlines() if re.fullmatch(r'[A-Za-z_.$][A-Za-z0-9_.$]*',v.strip()) and v not in ('_GLOBAL_OFFSET_TABLE_','_DYNAMIC')];t=asm.read_text();t+='\n.section .text._start,\"ax\",@progbits\nprivate_unused_stub:\n ret\n'+''.join('.weak '+u+'\n.set '+u+', private_unused_stub\n' for u in undefined);asm.write_text(t);subprocess.run(['cc','-c',str(asm),'-o',str(d/'entry.o')],check=True);script=d/'selector.ld';script.write_text('ENTRY(_start)\nSECTIONS {\n . = 0x600000;\n .text : { *(.text._start) }\n .selected : { picked_start = .; KEEP(*'+ob[0].name+'('+section+')) picked_end = .; }\n .rest : { KEEP(*('+section+')) }\n /DISCARD/ : { *(*) }\n}\n');rows=[]
 libdir=d/'shadow';libdir.mkdir();(libdir/'libutil.so').write_bytes(script.read_bytes());
 for mode in ('explicit-script','earlier-search-library'):
  for i,obj in enumerate(ob):
   case=d/(mode+'-'+str(i));case.mkdir();target=d/'selector-program';cmd=['gcc','-B'+str(sdk)+'/', '-fuse-ld=bfd','-nostdlib','-static','-no-pie','-Wl,--gc-sections','-Wl,--build-id=none','-o',str(target),str(d/'entry.o'),str(obj),*(['-Wl,-T,'+str(script)] if mode=='explicit-script' else ['-L'+str(libdir),'-Wl,-Bdynamic','-lutil'])];q=subprocess.run(['strace','-f','-qq','-s','65536','-e','trace=execve','-o',str(case/'exec'),*cmd],cwd=d,capture_output=True);(case/'stderr').write_bytes(q.stderr);events=[line for line in (case/'exec').read_text().splitlines() if 'execve("'+str(wild)+'"' in line and re.search(r'= 0$',line)];
   if q.returncode==0:
    exe_sha=sha(target);run=subprocess.run([str(target)],cwd=d,capture_output=True,timeout=2);symbols=subprocess.check_output(['nm','-n',str(target)]).decode();bound={line.split()[-1]:line.split()[0] for line in symbols.splitlines() if line.split() and line.split()[-1] in ('picked_start','picked_end')};
   else:exe_sha=None;run=None;bound={}
   row={'mode':mode,'filename':obj.name,'input_sha256':sha(obj),'actual_gcc_argv':cmd,'gcc_status':q.returncode,'gcc_stderr':q.stderr.decode(errors='replace'),'program_sha256':exe_sha,'program_return':run.returncode if run else None,'symbol_addresses':bound,'successful_wild_exec_sha256':[hashlib.sha256(s.encode()).hexdigest() for s in events],'sha256_executed_wild':sha(wild)};save(case/'result.json',row);rows.append(row);print(w['output'],mode,i,q.returncode,row['program_return'],len(events),q.stderr.decode(errors='replace')[:140],flush=True)
 result={'target':w['output'],'actual_source_argv_paths':[a,b],'actual_source_wild_pids':pids,'source_object_sha':sha(src),'source_object_bytes':src.stat().st_size,'section':section,'section_size':n,'private_unused_stub_symbols':undefined,'object_selector_script':script.read_text(),'selector_sha256':sha(script),'rows':rows};res.append(result);save(d/'complete.json',result)
save(Xout/'complete.json',res)
