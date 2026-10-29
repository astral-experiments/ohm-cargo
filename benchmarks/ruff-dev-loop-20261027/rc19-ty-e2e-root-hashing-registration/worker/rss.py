from pathlib import Path
import os,time,threading,collections
def sample_tree(root,done,result):
    samples=[];failures=collections.Counter();start=time.monotonic_ns();next_pss=0
    while not done.is_set():
        parents={};usage={}
        for f in Path('/proc').glob('[0-9]*/stat'):
            try:
                raw=f.read_text();pid=int(f.parent.name);v=raw[raw.rfind(')')+2:].split();parents[pid]=int(v[1]);usage[pid]=int(v[21])*os.sysconf('SC_PAGE_SIZE')
            except (OSError,ValueError,IndexError):continue
        family={root}
        while True:
            plus={pid for pid,parent in parents.items()if parent in family}
            if plus<=family:break
            family|=plus
        now=time.monotonic_ns();pvals=None
        if now>=next_pss:
            next_pss=now+350_000_000;pvals=[]
            for pid in family:
                try:
                    parts=(Path('/proc')/str(pid)/'smaps_rollup').read_text().splitlines()
                    pl=next(z for z in parts if z.startswith('Pss:'));pvals.append(int(pl.split()[1])*1024)
                except (OSError,ValueError,StopIteration)as err:failures[type(err).__name__]+=1
        samples.append([now-start,len(family),sum(usage.get(pid,0)for pid in family),sum(pvals) if pvals is not None else None])
        done.wait(.055)
    result.update(samples=samples,sampling_errors=failures,nominal_interval_ms=55,pss_period_ms=350)
