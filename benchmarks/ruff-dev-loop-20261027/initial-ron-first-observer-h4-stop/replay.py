"""Find the finite natural section-entry widths from independent, stock-only ELF link executions."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,tempfile,sys
S='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
candidate=Path(sys.argv[1]);assert hashlib.sha256(candidate.read_bytes()).hexdigest()==S
def sha(b):return hashlib.sha256(b).hexdigest()
def describe(data):
    p=struct.unpack_from('<Q',data,40)[0];width,n,ss=struct.unpack_from('<HHH',data,58);assert width==64
    hs=[struct.unpack_from('<IIQQQQIIQQ',data,p+i*width) for i in range(n)];lo=hs[ss][4];by={data[lo+r[0]:data.index(0,lo+r[0])]:i for i,r in enumerate(hs)}
    ni=by[b'.note.gnu.build-id'];a=hs[ni][4];nname,nb,ty=struct.unpack_from('<III',data,a);assert nname==4 and ty==3 and data[a+12:a+16]==b'GNU\0';ri=by[b'.rodata'];f=hs[ri];en=p+ri*width+56
    modified=bytearray(data);modified[a+16:a+16+nb]=bytes(nb);modified[en:en+8]=bytes(8)
    return {'size':len(data),'elf_sha256':sha(data),'normalized':sha(modified),'rodata_entsize':f[9],'rodata_flags':f[2],'build_id':data[a+16:a+16+nb].hex(),'build_id_desc':[a+16,nb],'entsize_at':en}
ordinary='.section .rodata.first,"a",@progbits\n.globl ordinary\nordinary: .byte 1\n.section .note.GNU-stack,"",@progbits\n'
start='.text\n.globl _start\n_start:\n movzbl ordinary(%rip),%edi\n movzbl merged(%rip),%eax\n add %eax,%edi\n mov $60,%eax\n syscall\n.section .note.GNU-stack,"",@progbits\n'
out=Path(sys.argv[2]);out.mkdir(mode=0o700);rows={};widths=(1,2,4,8,16,32,64,128,256)
for size in widths:
    root=out/str(size);root.mkdir()
    sources=(start,ordinary,f'.section .rodata.cst{size},"aM",@progbits,{size}\n.globl merged\nmerged: .byte 41\n.zero {size-1}\n.section .note.GNU-stack,"",@progbits\n')
    for i,source in enumerate(sources):
        f=root/str(i);f.with_suffix('.s').write_text(source);subprocess.run(['as','--64','-o',f.with_suffix('.o'),f.with_suffix('.s')],check=True,capture_output=True)
    objs=[root/f'{i}.o' for i in range(3)]
    obs=[]
    for n in (1,4,1,4):
        image=root/('link-'+str(len(obs)));cmd=[candidate,f'--threads={n}','--no-fork','-m','elf_x86_64','--build-id','-e','_start','--gc-sections','-o',image,*objs]
        subprocess.run(cmd,check=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},capture_output=True);b=image.read_bytes();assert subprocess.run([image]).returncode==42
        obs.append(dict(workers=n,**describe(b)))
    assert len({r['normalized'] for r in obs})==1 and obs[0]==obs[2] and obs[1]==obs[3]
    rows[str(size)]={'objects':[sha(f.read_bytes()) for f in objs],'observations':obs,'output_widths':sorted(set(r['rodata_entsize'] for r in obs))};print(size,rows[str(size)]['output_widths'])
(out/'complete.json').write_text(json.dumps({'wild':S,'inputs':rows},indent=2,sort_keys=True)+'\n')
