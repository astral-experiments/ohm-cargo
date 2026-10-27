from pathlib import Path
from collections import Counter,defaultdict
import gzip,hashlib,json,os,re,sys
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
D=X/'mixed-critical-path-v2'
def load(p):return json.loads(p.read_bytes())
inputs=json.loads(gzip.decompress(sys.stdin.buffer.read()))['build']['paths_and_bytes']
paths={}
for cr,ks in inputs.items():paths.update(ks)
def analyze(d):
    desc=load(d/'sampled-processes.json');cargo,=[int(p) for p,v in desc.items() if v['name']=='cargo']
    fs=sorted(d.glob('io.*'));identity={}
    # clone() without CLONE_THREAD starts a real process. It cannot contribute to Cargo's counters.
    clone=re.compile(r'\bclone(?:3)?\(.*\bCLONE_THREAD\b.*\)\s*=\s*(\d+)$')
    for f in fs:
        tid=int(f.name[3:])
        for l in f.open():
            if 'CLONE_THREAD' in l:
                m=clone.search(l.rstrip())
                if m:identity[int(m[1])]=tid
    def tgid(t):
        seen=set()
        while t in identity:
            assert t not in seen;seen.add(t);t=identity[t]
        return t
    sampled={}
    with gzip.open(d/'samples.jsonl.gz','rt') as so:
        for l in so:
            ns,rows=json.loads(l)
            for pid,*_ in rows:
                e=sampled.setdefault(pid,[ns/1e9,ns/1e9]);e[1]=ns/1e9
    wasm={r['crate']:sampled[int(pid)] for pid,r in desc.items() if r['crate'] in ('ruff_wasm','ty_wasm')}
    pat=re.compile(r'^(\d+\.\d+)\s+(read|pread64|readv|preadv)\(\d+<([^>]+)>.*\)\s*=\s*(\d+)$')
    mmap=re.compile(r'^\d+\.\d+\s+mmap\([^,]+,\s*(\d+).*?,\s*\d+<([^>]+)>,.*\)\s*=\s*0x[0-9a-f]+$')
    send=re.compile(r'^\d+\.\d+\s+(sendfile|copy_file_range)\(.*\)\s*=\s*(\d+)$')
    groups=defaultdict(Counter);facts=defaultdict(Counter);timefacts=defaultdict(list);bytid=defaultdict(Counter);markers=defaultdict(set);epochs=defaultdict(Counter);records=Counter();thread_observed=set()
    for f in fs:
        tid=int(f.name[3:]);tg=tgid(tid);role='cargo' if tg==cargo else (desc.get(str(tg)) or {}).get('name','other')
        for l in f.open(errors='replace'):
            line=l.rstrip();m=pat.match(line)
            if m:
                at=float(m[1]);op=m[2];p=m[3];n=int(m[4]);groups[role]['read_bytes_all']+=n
                if p.endswith('/native-library-v5.json') and role=='cargo':markers[tid].update(c for c in inputs if '/'+c+'/' in p)
                if p in paths:
                    groups[role]['transitive_reads']+=n;groups[role]['transitive_read_syscalls']+=bool(n)
                    if role=='cargo' and n:
                        bytid[tid][p]+=n;facts[p]['bytes']+=n;facts[p]['calls']+=1;thread_observed.add(tid)
                        timefacts[tid].append((at,n))
                elif role=='cargo' and ('.rlink' in p or p.endswith(('.bc','.rcgu.o'))):groups[role]['recipe_object_read_bytes']+=n
                elif role=='cargo' and p.endswith(('.rlib','.rmeta','.so')):groups[role]['other_native_read_bytes']+=n
                continue
            m=mmap.match(line)
            if m and m[2] in paths:groups[role]['mapped_lengths_transitive']+=int(m[1]);continue
            m=send.match(line)
            if m:
                groups[role][m[1]+'_returned_bytes_all']+=int(m[2]);continue
    allsets={c:set(s) for c,s in inputs.items()};both=set.intersection(*allsets.values());agg=defaultdict(Counter);perthread={}
    for tid,ks in bytid.items():
        unique={c:sum(v for k,v in ks.items() if k in keys-both) for c,keys in allsets.items()};matches=sorted(markers[tid])
        wal=None
        if len(matches)==1 and matches[0] in wasm:
            s,e=wasm[matches[0]];ch=Counter()
            for t,n in timefacts[tid]:
                ch['before_first_sample']+=n if t<s else 0;ch['inside_sampled_compiler']+=n if s<=t<=e else 0;ch['after_last_sample']+=n if t>e else 0
            wal=dict(ch)
        times=timefacts[tid];perthread[tid]=dict(markers=matches,paths=len(ks),sum_bytes=sum(ks.values()),unique_per_closure=unique,conditional_relative_to_own_sampled_compiler=wal,first_read_epoch_s=min(t for t,n in times),last_read_epoch_s=max(t for t,n in times))
    hist=Counter();factsout={}
    for p,size in sorted(paths.items()):
        total=facts[p]['bytes']
        if size:
            category=str(total//size) if total%size==0 else str(total//size)+'+partial';hist[category]+=1
        factsout[hashlib.sha256(os.fsencode(p)).hexdigest()]={'size':size,'bytes':total,'calls':facts[p]['calls'],'closures':[c for c,ss in inputs.items() if p in ss]}
    assert len(wasm)==2 and cargo>0 and len(fs)>100
    content_hashes=hashlib.sha256()
    for f in fs:content_hashes.update((str(f.name)+'\0'+hashlib.sha256(f.read_bytes()).hexdigest()+'\n').encode())
    return {'direction':load(d/'command.json')['direction'],'arm':load(d/'command.json')['arm'],'scope':'Actual successful read/pread/readv/preadv fd bytes with complete paths. Mapped lengths are separate and are not read counts. TGIDs are reconstructed from Linux CLONE_THREAD. Clock spans use external process samples and include instrumentation.','native_receipt_comparison':load(d/'output-comparison.json') if (d/'output-comparison.json').exists() else None,'complete_trace_shards_sha256':content_hashes.hexdigest(),'shards':len(fs),'trace_bytes':sum(f.stat().st_size for f in fs),'cargo_tgid':cargo,'groups':groups,'cargo_threads':perthread,'cargo_returned_file_fraction_histogram':dict(hist),'paths':factsout,'sampled_compiler_epoch_s':wasm}
docs={f.name:analyze(f) for f in sorted(D.glob('*-io-*')) if (f/'command.json').is_file()}
print(json.dumps(docs,sort_keys=True))
