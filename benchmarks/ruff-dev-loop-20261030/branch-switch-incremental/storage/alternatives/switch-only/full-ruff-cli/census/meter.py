"""Classify physically allocated inodes in a settled, exclusive Linux Cargo target/build volume."""
from pathlib import Path
import collections,gzip,hashlib,json,os,stat,struct,time
D_OPEN=os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME|os.O_CLOEXEC
RAW={'dep-graph.bin','query-cache.bin','ohm-build-dep-graph.bin','ohm-build-query-cache.bin'}
PACKED={'ohm-packed-dep-graph.bin','ohm-packed-query-cache.bin'}
KIND={stat.S_IFDIR:'directory',stat.S_IFLNK:'symlink',stat.S_IFREG:'regular'}
def signature(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_blocks,s.st_mtime_ns,s.st_ctime_ns)
def image(fd):
    hd=os.pread(fd,64,0)
    if hd.startswith(b'BC\xc0\xde') or hd.startswith(b'\xde\xc0\x17\x0b'):return 'bitcode'
    if hd.startswith((b'!<arch>\n',b'!<thin>\n')):return 'ar'
    if hd.startswith(b'rust\x00\x00\x00'):return 'rmeta'
    if len(hd)!=64 or hd[:6]!=b'\x7fELF\x02\x01':return 'other'
    kind=struct.unpack_from('<H',hd,16)[0]
    if kind==1:return 'elf-relocatable'
    if kind==2:return 'elf-executable'
    if kind!=3:return 'other-elf'
    offset=struct.unpack_from('<Q',hd,32)[0];size,count=struct.unpack_from('<HH',hd,54)
    if size!=56 or count>1024:return 'elf-dyn-unresolved'
    buf=os.pread(fd,size*count,offset)
    if len(buf)!=size*count:return 'elf-dyn-unresolved'
    headers=list(struct.iter_unpack('<IIQQQQQQ',buf))
    if any(x[0]==3 for x in headers):return 'elf-executable'
    for hdr in headers:
        if hdr[0]!=2:continue
        if hdr[5]>1024*1024 or hdr[5]%16:return 'elf-dyn-unresolved'
        dyn=os.pread(fd,hdr[5],hdr[2])
        if len(dyn)!=hdr[5]:return 'elf-dyn-unresolved'
        if any(t==0x6ffffffb and flags & 0x08000000 for t,flags in struct.iter_unpack('<QQ',dyn)):
            return 'elf-executable'
    return 'elf-shared-object'
def classify(parts,fmt,typ):
    if typ!='regular':return typ
    nm=parts[-1];inc='incremental' in parts
    if inc and nm in RAW:return 'raw-query-and-dep-tables'
    if inc and nm in PACKED:return 'packed-query-and-dep-tables'
    if fmt=='bitcode' or nm.endswith(('.bc','.bc.z','.bc.gz')):return 'llvm-bitcode'
    if nm.endswith(('.o','.obj')) or fmt=='elf-relocatable':return 'native-object'
    if nm.endswith('.rmeta') or fmt=='rmeta':return 'rust-metadata'
    if nm.endswith('.rlib'):return 'rust-library-archive'
    if nm.endswith('.a') or fmt=='ar':return 'native-library-archive'
    if fmt=='elf-executable':return 'executable'
    if fmt=='elf-shared-object':return 'shared-library'
    if fmt.startswith('elf-') or fmt=='other-elf':return 'other-elf'
    if nm.endswith('.rlink'):return 'rust-link-recipe'
    if inc and 'work-products' in nm:return 'incremental-work-product-index'
    if nm.endswith('.d') or '.fingerprint' in parts:return 'cargo-dep-info-or-fingerprint'
    return 'other-regular'
def scan(views,prior):
    rootdev=(views/'.allocation').stat().st_dev;out={};check=hashlib.sha256();name_count=0;start=time.monotonic()
    def walk(f,parts):
        nonlocal name_count
        with os.scandir(f) as it:entries=sorted((a.name for a in it),key=os.fsencode)
        for n in ['.']+entries:
            st=os.fstat(f) if n=='.' else os.stat(n,dir_fd=f,follow_symlinks=False)
            path=parts if n=='.' else parts+(n,);assert st.st_dev==rootdev
            if n!='.' and stat.S_ISDIR(st.st_mode):
                assert not n.endswith('-working');fd=os.open(n,D_OPEN,dir_fd=f)
                try:walk(fd,path)
                finally:os.close(fd)
                continue
            sig=signature(st);b='/'.join(path);check.update(os.fsencode(b)+b'\0'+str(sig).encode()+b'\n');name_count+=1
            ident=(st.st_dev,st.st_ino);kind=KIND.get(stat.S_IFMT(st.st_mode),'other-special')
            row=out.get(ident)
            if row is None:
                fmt='structural'
                if kind=='regular':
                    fd=os.open(n,os.O_NOATIME|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_RDONLY,dir_fd=f)
                    try:
                        assert signature(os.fstat(fd))==sig;fmt=image(fd);assert signature(os.fstat(fd))==sig
                    finally:os.close(fd)
                row=out[ident]={'device':st.st_dev,'ino':st.st_ino,'signature':sig,'format':fmt,'names':[],'kind':kind}
            assert row['signature']==sig;row['names'].append([b,classify(path,row['format'],kind)])
            if name_count%500==0:assert time.monotonic()-start<75
    for key in ['products','shared']:
        fd=os.open(views/key,D_OPEN)
        try:walk(fd,(key,))
        finally:os.close(fd)
    assert name_count==prior['path_entries'] and check.hexdigest()==prior['name_plus_inode_ledger_sha256']
    return [out[k] for k in sorted(out)],check.hexdigest()
def summarize(raw):
    bins={};slices=collections.Counter();external=collections.Counter()
    for row in raw:
        sig=row['signature'];size=sig[5]*512
        names=row['names'];b='+'.join(sorted({c for _,c in names}))
        inside=[('incremental' in s.split('/')) for s,c in names];boundary='incremental_only' if all(inside) else 'incremental_and_outside' if any(inside) else 'outside_only'
        roots={s.partition('/')[0] for s,c in names}
        assert roots<= {'products','shared'} and roots
        groups=bins.setdefault(b,{'unique_inodes':0,'bytes':0,'names':0,'incremental_only':0,'incremental_and_outside':0,'outside_only':0,'target_only':0,'build_only':0,'target_and_build':0})
        groups['unique_inodes']+=1;groups['names']+=len(names);groups['bytes']+=size
        groups[boundary]+=size;role='target_and_build' if len(roots)==2 else 'target_only' if 'products' in roots else 'build_only';groups[role]+=size
        slices[boundary]+=size;slices[role]+=size;slices['all']+=size
        if len(set(v for _,v in names))>1:slices['cross_category']+=size
        if row['kind']=='regular' and sig[3]!=len(names):external['inodes']+=1;external['bytes']+=size
    return {'classes':bins,'slices':dict(slices),'regular_with_unseen_nlink':dict(external)}
def observe(views,d):
    prior=json.loads((d/'settled.json').read_bytes())
    rows,digest=scan(views,prior);second,next_hash=scan(views,prior);assert second==rows and next_hash==digest
    sm=summarize(rows);v=sm['slices']
    for got,kind in [('all','all'),('incremental_only','incremental_only'),('incremental_and_outside','incremental_also_named_outside'),('target_and_build','both_roots_same_inode')]:assert v.get(got,0)==prior[kind]['allocated_bytes']
    assert v.get('target_only',0)+v.get('target_and_build',0)==prior['products']['allocated_bytes'] and v.get('build_only',0)+v.get('target_and_build',0)==prior['shared']['allocated_bytes']
    table=json.loads((d/'table-ledger.json').read_bytes())
    for flag,key,label in [(False,'raw','raw-query-and-dep-tables'),(True,'packed','packed-query-and-dep-tables')]:
        unique=[x for x in rows if any(cls==label for _,cls in x['names'])]
        assert sum(x['signature'][5]*512 for x in unique)==table['tables'][key]['allocated']
        assert len(unique)==table['tables'][key]['unique_inodes']
    dest=d/'categories.jsonl.gz';temp=d/'categories.partial';record=hashlib.sha256()
    with temp.open('xb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',compresslevel=2,mtime=0) as z:
            for row in rows:
                line=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode();record.update(line);z.write(line)
        f.flush();os.fsync(f.fileno())
    temp.rename(dest)
    with dest.open('rb') as f:packed=hashlib.file_digest(f,'sha256').hexdigest()
    with gzip.open(dest,'rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record.hexdigest()
    sm.update(raw_sha256=record.hexdigest(),compressed_sha256=packed,physical_ledger_sha256=digest,unique_inodes=len(rows),source_paths=prior['path_entries'],all_checks=True)
    with (d/'categories.json').open('x') as f:json.dump(sm,f,sort_keys=True,indent=2);f.write('\n')
