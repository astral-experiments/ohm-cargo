import collections,hashlib,json,re,sys
from pathlib import Path
d=Path(sys.argv[1]);p=d/'syscalls.raw';target=Path(json.loads((d/'product.json').read_bytes())['unit'])
prefix=str(target.parent)+'/.tmp';events=collections.Counter();mode=[];writes=[];positions=[];samples={};pending={};unattributed=[]; tids=set();srcs=set();reads={}
for line in p.open(errors='surrogateescape'):
    head,rest=line.strip().split(' ',1);k=int(head);rest=rest.lstrip()
    if rest.endswith('<unfinished ...>'):
        assert k not in pending
        pending[k]=rest[:-len('<unfinished ...>')];continue
    if rest.startswith('<... ') and ' resumed>'in rest:
        old=pending.pop(k)
        rest=old+rest.split(' resumed>',1)[1]
    if prefix not in rest or '.temp-archive/tmp.a' not in rest:continue
    op=rest.partition('(')[0]
    if op not in {'open','openat','openat2','close','write','writev','pwrite64','pwritev','pwritev2','lseek','ftruncate','rename','renameat','renameat2','fsync','fdatasync','mmap','msync','fcntl','newfstatat','fstat','statx','dup','dup2','dup3','fallocate','copy_file_range','splice','sendfile','unlink','unlinkat'}:continue
    rc=re.search(r'\)\s+= (-?\d+)',rest);assert rc,(op,rest[:200]);ret=int(rc[1]);events[op]+=1;tids.add(k)
    h=hashlib.sha256(rest.encode()).hexdigest()
    s=rest.replace(str(target.parent),'$OUT');samples.setdefault(op,[s[:300],h])
    if op.startswith('open'):mode.append(s)
    if op in ('write','pwrite64','writev','pwritev','pwritev2'):writes.append(ret)
    if op=='lseek':positions.append(s)
    if op=='rename':assert s.endswith('= 0') and str(target).replace(str(target.parent),'$OUT') in s
    if op in ('write','close'):
        m=re.search(r'\d+<([^>]+/tmp\.a)>',rest)
        if m:srcs.add(m[1])
assert len(srcs)==1 and not pending
res={'syscall_counts':dict(events),'write_bytes':sum(writes),'write_calls':len(writes),'write_min':min(writes)if writes else 0,'write_max':max(writes)if writes else 0,'open':mode,'seeks':positions[:12],'seek_count':len(positions),'tids':sorted(tids),'first_raw_examples':samples,'raw_trace_sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'output_name':target.name}
print(json.dumps(res,sort_keys=True,indent=2))
