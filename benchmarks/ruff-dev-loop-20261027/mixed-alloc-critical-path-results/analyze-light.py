"""Bracket native lifetimes and post-compiler artifact emission from a non-ptrace observation."""
import json, os, sys, bisect, gzip, hashlib, re
from pathlib import Path
from collections import Counter, defaultdict
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'; D=X/'mixed-critical-light-v1'
def j(p):return json.loads(p.read_bytes())
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def analyze(d):
    m=j(d/'command.json');assert m['rr']==0
    start=m['started']; end=m['ended']; sec=lambda n:round((n-start)/1e9,6)
    arrival=lambda p: j(d/p)
    def pipe(which,sel):
        ranges=[json.loads(x) for x in (d/(which+'.clock.jsonl')).read_bytes().splitlines()];ends=[off+n for off,n,t in ranges];ret=[];n=0;endp=(d/which).read_bytes()
        for row in endp.splitlines(keepends=True):
            n+=len(row);parts=sel(row)
            if parts is not None:ret.append([sec(ranges[bisect.bisect_left(ends,n)][2]),*parts])
        return ret
    def out(b):
        x=json.loads(b)
        if x.get('reason')=='compiler-artifact' and not x['fresh']:return [x['target']['name'],x['target']['kind']]
    def err(b):
        s=b.decode(errors='replace').rstrip();key='relink-only: cache validation for '
        if key in s:return s.split(key,1)[1].rsplit(' took ',1)
    kinds={int(k):v for k,v in j(d/'sampled-processes.json').items()};times=[];records=defaultdict(list)
    for line in gzip.open(d/'samples.jsonl.gz','rt'):
        t,rows=json.loads(line);idx=len(times);times.append(t)
        for pid,ppid,u,s,rss,n,rc,wc,rb,wb in rows:records[pid].append((idx,(u,s,rss,n,rc,wc,rb,wb)))
    native=[];cpu=os.sysconf('SC_CLK_TCK')
    for pid,seen in records.items():
        a=kinds[pid];name=a['name'];who={'cargo':'cargo','rustc':'rustc','ld.bfd':'wild'}.get(name)
        if not who:continue
        if who=='wild' and max(q[1][0]+q[1][1] for q in seen)==0:
            who='wild-driver'  # Each of the eight outputs also forks a waiting collect2-selected launcher.
        i,z=seen[0][0],seen[-1][0];peak=[max(q[1][k] for q in seen) for k in range(8)]
        lo=max(start,times[i-1]) if i else start;hi=times[i];elo=times[z];ehi=min(end,times[z+1]) if z+1<len(times) else end
        native.append(dict(pid=pid,role=who,target=a['crate'] or a['out'] or name,checked=a['checked'],link_only=a['link_only'],start_s=[sec(lo),sec(hi)],end_s=[sec(elo),sec(ehi)],sampled_peak_ticks_user=peak[0],sampled_peak_ticks_system=peak[1],sampled_peak_rss_pages=peak[2],sampled_peak_threads=peak[3],sampled_peak_rchar=peak[4],sampled_peak_wchar=peak[5],sampled_peak_disk_read_bytes=peak[6],sampled_peak_disk_write_bytes=peak[7],n_samples=len(seen)))
    arts=pipe('stdout',out);valid=pipe('stderr',err);wild=[r for r in native if r['role']=='wild'];rust=[r for r in native if r['role']=='rustc'];rows=[]
    for cr in ['ruff_wasm','ty_wasm']:
        proc,=[r for r in rust if r['target']==cr];art,=[r[0] for r in arts if r[1]==cr]
        mid=proc['end_s'];valid_one,=[r for r in valid if ' '+cr+' ' in r[1] or ' '+cr.replace('_','-')+' ' in r[1] or cr in r[1]]
        va=re.fullmatch(r'([.0-9]+)(s|ms|µs|us|ns)',valid_one[2]);assert va,valid_one
        vsecs=float(va[1])*{'s':1,'ms':.001,'µs':1e-6,'us':1e-6,'ns':1e-9}[va[2]]
        window=[round(valid_one[0]-vsecs,6),valid_one[0]];post=[round(max(0,art-mid[1]),6),round(max(0,art-mid[0]),6)]
        rows.append(dict(target=cr,actual_prevalidation_s=vsecs,prevalidation_arrival_window=window,compiler_end_s=mid,artifact_arrived_s=art,post_exit_to_artifact_s=post,wild_overlapping_validation_definite=[z['target'] for z in wild if z['start_s'][1]<window[1] and z['end_s'][0]>window[0]],wild_overlapping_post_definite=[z['target'] for z in wild if z['start_s'][1]<art and z['end_s'][0]>mid[1]]))
    n=sec(end);lastwa=[max(r['end_s'][i] for r in wild) for i in (0,1)];lastcmp=[max(r['end_s'][i] for r in rust) for i in (0,1)];assert len(rust)==9 and len(wild)==8,(d.name,[(r['role'],r['target']) for r in native],[(v['name'],v['out']) for v in kinds.values() if v['out']])
    cargo_id,=[r['pid'] for r in native if r['role']=='cargo'];c=list(records[cargo_id])
    # TGID /proc/io picks up some waited child IO. Separate Cargo-only syscall proof, and exclude all complex child exits from bandwidth claims.
    metrics=[{'at_s':sec(times[i]),'user_ticks':values[0],'system_ticks':values[1],'rchar':values[4],'wchar':values[5],'read_bytes':values[6],'write_bytes':values[7]} for i,values in c]
    return dict(cargo_sample_series=metrics,command_sha256=h(d/'command.json'),elapsed_s=n,arm=m['arm'],direction=m['direction'],ticks_per_sec=cpu,max_sample_gap_s=round(max(y-x for x,y in zip(times,times[1:]))/1e9,6),median_sample_gap_s=round(sorted(y-x for x,y in zip(times,times[1:]))[len(times)//2]/1e9,6),native=sorted(native,key=lambda r:r['start_s'][1]),last_wild_end=lastwa,last_native_compiler_end=lastcmp,tail_after_last_compiler_s=[round(max(0,n-lastcmp[1]),6),round(max(0,n-lastcmp[0]),6)],artifact_arrival=arts,validations=valid,wasm=rows,return_guard=j(d/'output-comparison.json'),sample_sha=h(d/'samples.jsonl.gz'),descriptive_only=True)
docs={p.name:analyze(p) for p in sorted(D.glob('*-light-*')) if p.is_dir() and (p/'command.json').exists()};assert len(docs)==4
print(json.dumps(docs,sort_keys=True))
