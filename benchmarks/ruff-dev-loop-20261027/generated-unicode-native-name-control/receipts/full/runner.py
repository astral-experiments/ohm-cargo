"""Run a custom immutable native selector on two real Ruff archives already retained in the study."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
z=q/'unicode-lifetime-v1';o=q/'unicode-native-member-selector-v2';o.mkdir();raw=z/'raw';inputlib=o/'libunicode_names2.rlib';obj=o/'observer.o';exe=o/'observer'
H=lambda b:hashlib.sha256(b).hexdigest()
roots={t:json.loads((z/t/'unicode-native.json').read_bytes())['unicode_names2'] for t in ('original','edited','restored')}
nm='_RNvCs6tuOZN82rAq_14unicode_names24name';sec='.text.'+nm;oldlib=raw/roots['original']['rlib']['sha']
def run(args,stage,key,required=True):
    p=subprocess.run(list(map(str,args)),capture_output=True,cwd=o,env=env);(stage/(key+'.out')).write_bytes(p.stdout);(stage/(key+'.err')).write_bytes(p.stderr)
    put(stage/(key+'.json'),{'args':list(map(str,args)),'status':p.returncode,'stdout':H(p.stdout),'stderr':H(p.stderr)})
    if required:assert p.returncode==0,(key,p.stdout[-350:],p.stderr[-600:])
    return p
out=subprocess.check_output(['nm','--print-armap',oldlib],stderr=subprocess.DEVNULL)
m,=[x.decode() for x in re.findall(rb'^'+re.escape(nm.encode())+rb' in (.*)$',out,re.M)];assert m in [n for n,_,_ in roots['original']['members']]
dl='SECTIONS {\n . = 0x600000;\n .selected : { picked_start = .; KEEP('+m+'('+sec+')) picked_end = .; }\n .text : { *(.text*) }\n .rodata : { *(.rodata*) }\n . = ALIGN(4096);\n .data : { *(.data*) }\n .bss : { *(.bss*) }\n}\n'
(o/'layout.ld').write_text('ENTRY(_start)\n'+dl)
(o/'observer.s').write_text('.text\n.global _start\n.type _start,@function\n_start:\n  leaq picked_end(%rip),%rax\n  leaq picked_start(%rip),%rdx\n  subq %rdx,%rax\n  xor %edi,%edi\n  test %rax,%rax\n  setnz %dil\n  addl $41,%edi\n  mov $60,%eax\n  syscall\n.section .note.GNU-stack,"",@progbits\n')
run(['/usr/bin/gcc','-c','-x','assembler',o/'observer.s','-o',obj],o,'assemble')
wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';assert sha(wild)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
command=[wild,'-static','--gc-sections','--unresolved-symbols=ignore-all','--undefined='+nm,'-T',o/'layout.ld','-o',exe,obj,inputlib]
put(o/'design.json',{'experiment':'Unscored custom-script native witness on already authenticated outputs; two logical names, true same canonical archive/command each time. The ordinary Ruff CLI did not use this custom script.','sources':{k:v['rlib']['sha']for k,v in roots.items()},'symbol':nm,'section':sec,'selector':m,'object':sha(obj),'assembly':sha(o/'observer.s'),'script':sha(o/'layout.ld'),'linker':sha(wild),'command':list(map(str,command)),'expected':{'original':'484-byte function padded to 496 bytes at 16-byte output section alignment and exit 42, established in separate failed original framing and readelf','edited':'0 bytes and exit 41','restored':'the compiler emitted a new archive member name after restore; result follows physical member-name membership, not source identity'}})
for t in ('original','edited','restored'):
    cand=raw/roots[t]['rlib']['sha'];shutil.copyfile(cand,inputlib);assert sha(inputlib)==roots[t]['rlib']['sha']
    stage=o/t;stage.mkdir();lc=run(command,stage,'wild');sr=run(['nm','-n',exe],stage,'symbols')
    syms={k.decode():int(v,16)for v,k in re.findall(rb'^([0-9a-f]+) \w (picked_(?:start|end))$',sr.stdout,re.M)};assert len(syms)==2
    diff=syms['picked_end']-syms['picked_start'];hit=m in [n for n,size,h in roots[t]['members']];assert diff==(496 if hit else 0),(t,hit,diff)
    sy=run(['readelf','-sW',exe],stage,'readelf-symbols');ss=run(['readelf','-SW',exe],stage,'readelf-sections');assert re.search(rb'\b484 FUNC .*'+re.escape(nm.encode())+rb'$',sy.stdout,re.M)
    ex=run([exe],stage,'execute',False);assert ex.returncode==(42 if hit else 41)and not ex.stdout and not ex.stderr
    put(stage/'result.json',{'source':t,'subject':sha(inputlib),'script':sha(o/'layout.ld'),'object':sha(obj),'linker':sha(wild),'output':sha(exe),'size':exe.stat().st_size,'bounds':syms,'distance':diff,'name_exists':hit,'exit':ex.returncode});shutil.copyfile(exe,stage/'observed.elf');print(t,hit,diff,ex.returncode,sha(exe),flush=True)
put(o/'complete.json',{'rows':3,'stage':'custom native static link; no Ruff Cargo times','status':0})
