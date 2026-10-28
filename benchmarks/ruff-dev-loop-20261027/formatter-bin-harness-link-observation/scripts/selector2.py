"""Probe an actual compiler-produced Rust archive with a symbol request, an input-member matcher, and whole-archive."""
from pathlib import Path
import hashlib,json,os,re,runpy,shutil,subprocess
p=Path(__file__).resolve().parent;q=p/'selector-v2';q.mkdir()
base=p/'runs-v2';api=runpy.run_path(str(p/'linked-layout.py'))
sha=lambda b:hashlib.sha256(b).hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
attr=json.loads((p/'attribution.json').read_bytes())['phases']
s0='prime';marker,=attr[s0]['archive_marker'];m=marker['raw_name'];sec,=[k[:-2] for k in marker['sections'] if k.startswith('.text.') and k.endswith('#0')];symbol=sec[len('.text.'):]
root=(base/s0/'formatter.rlib').read_bytes();ma,idx=api['archive'](root)
assert (symbol,marker['member']) in idx
s0_expected=api['elf'](ma[marker['member']][3])[0][sec+'#0'][2][2];assert s0_expected>0
probe=q/'reader.s';probe.write_text('.text\n.globl _start\n.type _start,@function\n_start:\n leaq observed_end(%rip),%rax\n leaq observed_begin(%rip),%rdx\n sub %rdx,%rax\n xor %edi,%edi\n test %rax,%rax\n setnz %dil\n add $41,%edi\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n')
ld=q/'layout.ld';ld.write_text(f'ENTRY(_start)\nSECTIONS {{ . = 0x600000; .selected : {{ observed_begin = .; KEEP({m}({sec})) observed_end = .; }} .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} . = ALIGN(4096); .data : {{ *(.data*) }} .bss : {{ *(.bss*) }} }}\n')
obj=q/'reader.o';subprocess.run(['/usr/bin/gcc','-c','-x','assembler',probe,'-o',obj],check=True)
wild=Path('/dev/shm/ohm-published-member-h2-20261028/installed17/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd');assert sha(wild.read_bytes())=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
lib=q/'libruff_formatter.rlib';exe=q/'reader';ans={}
for kind in ('previous-empty','forced-symbol','whole-archive'):
 for st in ('prime','edit','restore','repeat-prime'):
    actual='prime' if st=='repeat-prime' else st;d=q/kind/st;d.mkdir(parents=True)
    shutil.copyfile(base/actual/'formatter.rlib',lib);present=m in [v[0] for v in api['archive'](lib.read_bytes())[0].values()]
    force=['--undefined='+symbol] if kind=='forced-symbol' else []
    ar=[lib] if kind!='whole-archive' else ['--whole-archive',lib,'--no-whole-archive']
    args=[str(x) for x in (wild,'--threads=4','-static','--gc-sections','--unresolved-symbols=ignore-all',*force,'-T',ld,'-o',exe,obj,*ar)]
    cmd=subprocess.run(args,env=dict(os.environ,WILD_WRITE_LAYOUT='1'),cwd=q,capture_output=True)
    (d/'ld.out').write_bytes(cmd.stdout);(d/'ld.err').write_bytes(cmd.stderr);assert cmd.returncode==0,(kind,st,cmd.stderr[-800:])
    run=subprocess.run([exe],capture_output=True);assert not run.stdout and not run.stderr
    sy=subprocess.check_output(['nm','-n',exe]);bounds={name.decode():int(n,16) for n,name in re.findall(rb'^([0-9a-f]+) \w (observed_(?:begin|end))$',sy,re.M)};assert len(bounds)==2
    distance=bounds['observed_end']-bounds['observed_begin'];expected=s0_expected if present and kind!='previous-empty' else 0
    assert (distance>=expected if expected else distance==0) and run.returncode==(42 if expected else 41),(kind,st,run.returncode,distance,expected)
    layout=exe.with_name(exe.name+'.layout');rows,_=api['decode_layout'](layout.read_bytes());sel=[e[-1] for path,e,s,t in rows if path==str(lib) and e]
    if present and kind!='previous-empty':
        target,=[(e,ss) for pp,e,ss,tt in rows if pp==str(lib) and e and e[2]==m]
        si=api['elf'](ma[marker['member']][3])[0][sec+'#0'][0]; retained=target[1][si];assert retained and bounds['observed_begin']<=retained[0]<retained[1]<=bounds['observed_end'] and retained[1]-retained[0]==s0_expected,(kind,retained,bounds,s0_expected)
    answer={'input_section_bytes':s0_expected,'mode':kind,'source_arm':st,'raw_member_name_present':present,'archive_sha':sha(lib.read_bytes()),'symbol':symbol,'member':m,'input_section':sec,'matched_bytes':distance,'status':run.returncode,'elf':sha(exe.read_bytes()),'argv':args,'argv_sha':sha(json.dumps(args,separators=(',',':')).encode()),'stock_wild':sha(wild.read_bytes()),'asm':sha(probe.read_bytes()),'script':sha(ld.read_bytes()),'object':sha(obj.read_bytes()),'layout':sha(layout.read_bytes()),'selected_archive_members':len(sel)}
    dump(d/'row.json',answer);shutil.copyfile(exe,d/'reader.elf')
    ans[f'{kind}:{st}']=answer
 print(kind,[(ans[f'{kind}:{st}']['status'],ans[f'{kind}:{st}']['matched_bytes'],ans[f'{kind}:{st}']['selected_archive_members']) for st in ('prime','edit','restore','repeat-prime')],flush=True)
dump(q/'complete.json',ans)
