"""Strip non-runtime symbols with LLVM, retaining exact program headers and loader inputs."""
from pathlib import Path
import hashlib,json,os,re,struct,subprocess
SDK=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/frozen-toolchain')
PROGRAM=SDK/'lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-objcopy'
LLVM=SDK/'lib/libLLVM.so.23.1-rust-1.99.0-beta'
E=dict(os.environ,LD_LIBRARY_PATH=str(SDK/'lib'))
FLAGS=['--strip-all','--remove-section=.note.gnu.build-id']
def he(b):return hashlib.sha256(b).hexdigest()
def shape(b):
    assert b[:6]==b'\x7fELF\x02\x01' and b[18:20]==b'\x3e\x00'
    phoff,shoff=struct.unpack_from('<QQ',b,32)
    phents,phnum,shents,shnum,shstr=struct.unpack_from('<HHHHH',b,54)
    headers=[struct.unpack_from('<IIQQQQQQ',b,phoff+i*phents) for i in range(phnum)]
    s=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*shents) for i in range(shnum)]
    names=b[s[shstr][4]:s[shstr][4]+s[shstr][5]]
    sec={names[z[0]:names.index(0,z[0])].decode():z for z in s}
    return headers,sec
def section(b,s):return he(b[s[4]:s[4]+s[5]]) if s[1]!=8 else None
def strip(src,dst):
    assert src.is_file() and not dst.exists()
    args=[str(PROGRAM),*FLAGS,str(src),str(dst)]
    subprocess.run(args,env=E,check=True);dst.chmod(0o555)
    a,b=src.read_bytes(),dst.read_bytes();old,orig=shape(a);new,end=shape(b)
    assert old==new and any(p[0]==0x6474e552 for p in old), 'changed program headers / missing GNU RELRO'
    assert struct.unpack_from('<Q',a,24)==struct.unpack_from('<Q',b,24), 'entry point changed'
    name='.note.gnu.build-id';note=orig[name];assert name not in end and '.symtab' in orig and '.symtab' not in end and '.strtab' not in end
    x={k for k,s in orig.items() if s[2]&2};y={k for k,s in end.items() if s[2]&2}
    assert x-{name}==y and {'.text','.rodata','.dynsym','.dynstr','.dynamic','.gnu.version','.gnu.version_r'}<=y
    kept={}
    for k in sorted(y):
        s,t=orig[k],end[k]
        assert (s[1],s[2],s[3],s[4],s[5],section(a,s))==(t[1],t[2],t[3],t[4],t[5],section(b,t)),k
        kept[k]=[s[3],s[5],section(a,s)]
    allowed=set(range(40,48))|set(range(60,64))|set(range(note[4],note[4]+note[5]))
    loads=[]
    for p in old:
        if p[0]!=1:continue
        off,n=p[2],p[5];ra=a[off:off+n];rb=b[off:off+n]
        ds=[i+off for i,(aa,bb) in enumerate(zip(ra,rb)) if aa!=bb]
        assert set(ds)<=allowed,(p,ds[:60]);loads.append({'virtual':p[3],'file_offset':off,'size':n,'flags':p[1],'raw':he(ra),'packaged':he(rb),'physical_changed_byte_offsets':ds})
    def needed(p):
        cp=subprocess.run(['readelf','--wide','--dynamic',p],check=True,capture_output=True,text=True)
        return [l.split('(',1)[1].strip() for l in cp.stdout.splitlines() if any('('+k+')' in l for k in ('NEEDED','RPATH','RUNPATH','SONAME'))]
    dependencies=needed(src);assert dependencies==needed(dst)
    listings={}
    for label,opts in [('program_headers',['--wide','--program-headers']),('dynamic',['--wide','--dynamic']),('dyn_symbols',['--wide','--dyn-syms']),('versions',['--wide','--version-info']),('relocations',['--wide','--relocs']),('notes',['--wide','--notes'])]:
        raw,packaged=[subprocess.run(['readelf',*opts,p],check=True,capture_output=True) for p in (src,dst)]
        if label=='versions':
            # Following the same named target is what the ELF section-link index represents.
            canonical=lambda text:re.sub(rb'Link: [0-9]+ \(\.(dynsym|dynstr)\)',rb'Link: (.\1)',text)
            assert canonical(raw.stdout)==canonical(packaged.stdout) and raw.stderr==packaged.stderr,label
        elif label in ('dynamic','dyn_symbols','relocations'):assert raw.stdout==packaged.stdout and raw.stderr==packaged.stderr,label
        elif label=='program_headers':assert b'GNU_RELRO' in packaged.stdout and b'GNU_STACK' in packaged.stdout
        listings[label]={'raw_sha256':he(raw.stdout),'packaged_sha256':he(packaged.stdout),'raw_stderr':raw.stderr.decode(),'packaged_stderr':packaged.stderr.decode()}
        if label in ('program_headers','dynamic','notes'):
            listings[label].update(raw=raw.stdout.decode(),packaged=packaged.stdout.decode())
    va=subprocess.check_output([src,'-Vv'],text=True);assert subprocess.check_output([dst,'-Vv'],text=True)==va
    return {'raw_sha256':he(a),'packaged_sha256':he(b),'raw_size':len(a),'packaged_size':len(b),'argv':args,'packager_path':str(PROGRAM.resolve()),'packager_sha256':he(PROGRAM.read_bytes()),'version':subprocess.check_output([PROGRAM,'--version'],env=E,text=True).strip(),'LLVM_shared_library':str(LLVM),'LLVM_sha256':he(LLVM.read_bytes()),'readelf':listings,'cargo_version':va,'all_unchanged_program_headers':old,'GNU_RELRO_present':True,'load_segments':loads,'original_build_id_note':[note[4],note[5],section(a,note)],'unchanged_allocated_sections':kept,'dynamic_dependencies':dependencies,'entry_address':struct.unpack_from('<Q',a,24)[0]}
