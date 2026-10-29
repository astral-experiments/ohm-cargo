import collections,decimal,hashlib,json,re,sys
from pathlib import Path
D=decimal.Decimal
p=Path(sys.argv[1]);src=p/'syscalls.raw';unit=Path(json.loads((p/'product.json').read_bytes())['unit']);prefix=str(unit.parent)+'/.tmp'
pending={};events=[]
for li in src.open():
    head,when,text=li.strip().split(None,2);tid=int(head);stamp=D(when)
    if text.endswith('<unfinished ...>'):
        assert tid not in pending;pending[tid]=(stamp,text[:-len('<unfinished ...>')]);continue
    if text.startswith('<... ')and'resumed>'in text:
        stamp,start=pending.pop(tid);text=start+text.split(' resumed>',1)[1]
    if prefix not in text or '.temp-archive/tmp.a' not in text:continue
    op=text.partition('(')[0]
    if op not in ('open','openat','openat2','close','write','writev','pwrite64','rename','renameat','renameat2','lseek','ftruncate','fstat','newfstatat','mmap','splice','copy_file_range','fcntl'):continue
    m=re.search(r'\)\s+= ([0-9]+).* <([0-9.]+)>$',text);assert m,(op,text)
    events.append({'tid':tid,'op':op,'start_us':int(stamp*1000000),'duration_us':int(D(m[2])*1000000),'return':int(m[1]),'raw_sha256':hashlib.sha256(text.encode()).hexdigest()})
assert not pending
counts=collections.Counter(v['op']for v in events);o,=[v for v in events if v['op']=='openat'];c,=[v for v in events if v['op']=='close'];ren,=[v for v in events if v['op']=='rename'];writes=[v for v in events if v['op']=='write']
end=lambda v:v['start_us']+v['duration_us']
res={'counts':counts,'source_sha256':hashlib.file_digest(src.open('rb'),'sha256').hexdigest(),'open':o,'close':c,'rename':ren,'write_bytes':sum(z['return']for z in writes),'write_syscall_us_sum':sum(z['duration_us']for z in writes),'open_return_to_close_return_us':end(c)-end(o),'open_return_to_rename_return_us':end(ren)-end(o),'write_min':min(z['return']for z in writes),'write_max':max(z['return']for z in writes),'all_tids':sorted({r['tid']for r in events})}
print(json.dumps(res,sort_keys=True,indent=2))
