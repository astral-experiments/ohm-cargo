"""Inspect a retained native output without weakening metadata, object, symbol, or archive boundaries."""
import ctypes, gzip, hashlib, json, mmap, os, re, shutil, struct, subprocess
from pathlib import Path
import archive_audit
from common import FROZEN, TARGET, RUFF, env, elf, compare_elf, need, sha
from state import WASM, EDITED, ORIGINAL
from witness import as_digest

def inputs_elf_key(path):
    # Standard Cargo aliases end in debug/lib*.so; internal paths end in package/unit/out/filename.
    p=Path(path)
    return '/'.join(p.parts[-4:]) if p.parent.name=='out' else str(p.relative_to(TARGET))

def oracle(ruff, edited):
    from common import DATACLASS
    rows={}
    for name,flags,data in [('parser',['--target-version','py314'],b"t'first' b'second'\n"),('linter',['--preview','--select','RUF008','--stdin-filename','case.py'],DATACLASS)]:
        q=subprocess.run([str(ruff),'check','--isolated','--no-cache','--output-format','json',*flags,'-'],input=data,cwd=RUFF,env=env(),capture_output=True)
        need(q.returncode==1 and not q.stderr,('Ruff runtime',q.stderr));rows[name]=json.loads(q.stdout)
    need([m['message'] for m in rows['parser']]==[EDITED if edited else ORIGINAL],rows)
    need([(m['code'],m['location']['row'],m['location']['column']) for m in rows['linter']]==[('RUF008',4,34),('RUF008',6,20)],rows)
    return rows

def canonical_archive(path, audit):
    names=[name.encode() for name,_,_ in audit['objects']]
    replacements=[]
    for name in names:
        prefix,nonce,rcgu,suffix=name.rsplit(b'.',3)
        need(re.fullmatch(rb'[a-z0-9]+',nonce) and (rcgu,suffix)==(b'rcgu',b'o'),name)
        replacements.append((name,b'.'.join([prefix,b'_'*len(nonce),rcgu,suffix])))
    # Mask only the encoded GNU long-name table and rustc's structurally decoded
    # rust-object list. Every other byte in the archive is retained.
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mem:
        at=8;last=0;h=hashlib.sha256();changed=[]
        while at<len(mem):
            head=mem[at:at+60];size=int(head[48:58]);pos=at+60;end=pos+size;nm=head[:16].strip().rstrip(b'/')
            if head[:16].strip()==b'//':
                start=pos;section=mem[start:end];reason='GNU-name-table'
            elif nm==b'lib.rmeta-link':
                blob=mem[pos:end];sections=archive_audit.elf(blob);payload=sections['.rmeta-link']['data'];where=blob.find(payload)
                need(where>=0 and blob.find(payload,where+1)==-1,'unique rmeta-link payload');start=pos+where;section=payload;reason='checked-rmeta-link-object-list'
            else:
                at=end+end%2;continue
            restored=section
            for orig,repl in replacements:
                need(section.count(orig)==1,('only known CGU names',reason,orig));restored=restored.replace(orig,repl)
            h.update(memoryview(mem)[last:start]);h.update(restored);last=start+len(section);changed.append(reason);at=end+end%2
        need(at==len(mem) and len(changed)==2,('archive constituents',changed));h.update(memoryview(mem)[last:]);return h.hexdigest()

def retain(path, retained):
    retained.mkdir(exist_ok=True);digest=sha(path);dest=retained/(digest+'.gz')
    if not dest.exists():
        with path.open('rb') as source, dest.open('xb') as file, gzip.GzipFile(fileobj=file,mode='wb',mtime=0,compresslevel=1) as zipped:
            shutil.copyfileobj(source,zipped,1024*1024)
        with gzip.open(dest,'rb') as verifier:need(hashlib.file_digest(verifier,'sha256').hexdigest()==digest,'bad retained artifact')
    return digest

def inspect_one(files, retained):
    md,=map(Path,[n for n in files if n.endswith('.rmeta')]);library,=map(Path,[n for n in files if n.endswith('.rlib')]); so,=map(Path,[n for n in files if n.endswith('.so')])
    need(md.with_suffix('.rlib').is_file() and sha(md.with_suffix('.rlib'))==sha(library),'aliased library bytes')
    a=archive_audit.inspect(library);embedded=subprocess.check_output(['ar','p',library,'lib.rmeta'])
    root=subprocess.check_output(['rustc','+ohm','--sysroot',str(FROZEN),'-Zls=root',str(md)],env=env(),text=True)
    m=re.search(r'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',root,re.M)
    need(m is not None,('cannot decode actual metadata header',root[:800]))
    dynamic=subprocess.check_output(['nm','-D','--defined-only',so],text=True).splitlines();names=[s.split()[-1] for s in dynamic]
    need(len(names)>=8,'missing exports')
    lib=ctypes.CDLL(str(so))
    for sym in names:getattr(lib,sym)
    malloc=lib.__wbindgen_malloc; free=lib.__wbindgen_free
    malloc.argtypes=[ctypes.c_uint32]*2;malloc.restype=ctypes.c_uint32
    free.argtypes=[ctypes.c_uint32]*3;free.restype=None
    if int(os.sysconf('SC_LONG_BIT'))!=64:raise ValueError('wrong native ABI')
    allocations=[malloc(0,i) for i in (1,2,4,8,16,32)];need(allocations==[1,2,4,8,16,32],allocations)
    for v in allocations:free(v,0,v)
    for p in (md,library,so):retain(p,retained)
    text=retained/(sha(md)+'.root.txt')
    if not text.exists():text.write_text(root)
    need(text.read_text()==root,'unstable decoded metadata header')
    return {'metadata':str(md),'rlib':str(library),'cdylib':str(so),'rmeta_bytes':md.stat().st_size,'rmeta_sha256':sha(md),'private_svh':m[1],'stable_crate_id':m[2],'public_svh':m[3],
            'embedded_object_sha256':hashlib.sha256(embedded).hexdigest(),'root_listing_sha256':hashlib.sha256(root.encode()).hexdigest(),
            'exports':dynamic,'zero_byte_allocations':allocations,'cdylib_elf':elf(so),'archive':a,'normalized_archive_sha256':canonical_archive(library,a)}

def products(j, rows, edited, full, retained):
    normal=[r for r in rows if r.get('reason')=='compiler-artifact' and not r['profile']['test']]
    ruff,={r['executable'] for r in normal if r['target']['name']=='ruff' and r['target']['kind']==['bin'] and r.get('executable')}
    hasws=[r for r in normal if r['target']['name'] in WASM and set(r['target']['crate_types'])=={'cdylib','rlib'}]
    need(len(hasws)==2,'mixed units uniquely selected')
    res={'units':j['units'],'diagnostics':oracle(ruff,edited),'structural_roster':j['roster_sha256'],'messages':j['message_sha256'],
         'dirty':j['dirty'],'mixed_paths':{r['target']['name']:r['filenames'] for r in hasws}}
    if full:
        res['elf']={inputs_elf_key(p):elf(Path(p)) for p in j['elf']};need(len(res['elf'])==len(j['elf']),'artifact key collision')
        res['mixed']={r['target']['name']:inspect_one(r['filenames'],retained) for r in hasws}
    return res

def compare_context(got, ref, mixed=True):
    need(got['units']==ref['units'] and got['diagnostics']==ref['diagnostics'] and got['messages']==ref['messages'],'workspace diagnostics or roster changed')
    differences=compare_elf(got['elf'],ref['elf'])
    name_only={}
    if mixed:
        for cr in WASM:
            x,y=got['mixed'][cr],ref['mixed'][cr]
            need(x['cdylib_elf']['raw']==y['cdylib_elf']['raw'],('raw mixed shared library mismatch',cr,x['cdylib_elf']['raw'],y['cdylib_elf']['raw']))
            for k in ['rmeta_bytes','rmeta_sha256','private_svh','stable_crate_id','public_svh','embedded_object_sha256','root_listing_sha256','exports','zero_byte_allocations','normalized_archive_sha256']:
                need(x[k]==y[k],('mixed mismatch',cr,k,x[k],y[k]))
            z=archive_audit.compare(x['archive'],y['archive'])
            need(z['same_slot_payloads']==z['same_slot_cgu_prefixes']==z['object_count'] and z['identical_ordered_symbol_to_member_index'],('different native objects/index',cr,z))
            name_only[cr]={'object_count':z['object_count'],'names_changed':z['object_count']-z['identical_member_names'],
                           'raw_archive_equal':x['archive']['sha256']==y['archive']['sha256'],'index_entries':z['index_entries']}
    return {'allowed_elf_differences':differences,'raw_equal':len(got['elf'])-len(differences),'mixed':name_only}

