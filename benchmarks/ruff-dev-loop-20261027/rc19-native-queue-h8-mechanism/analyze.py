"""Reconstruct exactly concurrent positive stock linker invocations; all reported intervals are diagnostic."""
import collections,gzip,itertools,json,math,statistics as st,sys
from pathlib import Path
def parse(f):
    return json.loads(gzip.decompress(Path(f).read_bytes()))
def one(run):
    bins=run['bins']; ranked=sorted(bins,key=lambda n:(-bins[n]['output_bytes'],n)); top=set(ranked[:10])
    def cuts(key):
        edge=sorted(e for n,j in bins.items()for e in [(j[key][0],1,n),(j[key][1],0,n)])
        live=set();out=[];prev=edge[0][0]
        for t,on,n in edge:
            if t>prev:out.append((t-prev,tuple(live),prev))
            (live.add if on else live.remove)(n);prev=t
        return edge,out
    def measure(key):
        events,intervals=cuts(key);first=events[0][0];finish=events[-1][0];last_started=max(x[key][0]for x in bins.values());a=[(dt/1e9,set(names),t)for dt,names,t in intervals]
        highsecs=sum(s for s,live,t in a if len(live&top)>=4)
        tail=(finish-last_started)/1e9;work={n:(bins[n][key][1]-bins[n][key][0])/1e9 for n in bins}
        nearend=[{'target':n,'size_rank':ranked.index(n)+1,'start_s':(bins[n][key][0]-first)/1e9,'duration_s':work[n],'end_s':(bins[n][key][1]-first)/1e9}for n in sorted(bins,key=lambda n:bins[n][key][1],reverse=True)[:5]]
        return {'first_from_cargo_s':first/1e9,'span_s':(finish-first)/1e9,'after_last_start_s':tail,'last_only_s':nearend[0]['end_s']-nearend[1]['end_s'],'shutdown_from_last_s':(run['cargo'][1]-finish)/1e9,'aggregate_job_s':sum(work.values()),'top10_job_s':sum(work[n]for n in top),'top10_median_s':st.median(work[n]for n in top),'other_median_s':st.median(work[n]for n in set(bins)-top),
        'mean_concurrent':sum(s*len(v)for s,v,_ in a)/((finish-first)/1e9),'max_concurrent':max(len(live)for s,live,t in a),'max_top10_simultaneous':max(len(live&top)for s,live,t in a),'max_output_gb':max(sum(bins[n]['output_bytes']for n in live)for _,live,t in a)/1e9,
        'secs_4_or_more_top10':highsecs,'pairwise_top10_overlap_s':sum(s*math.comb(len(live&top),2)for s,live,_ in a),'secs_more_than_1g_live_elf':sum(s for s,live,_ in a if sum(bins[n]['output_bytes']for n in live)>=10**9),'last_five_finished':nearend,'duration_by_target':work,'order':[v[2]for v in events if v[1]],'tailspan_from_last_start':[(s,len(v)) for s,v,t in a if t>=last_started], 'last_start_count':sum(1 for x in bins.values()if x[key][0]<=last_started<x[key][1])}
    return {k:run[k]for k in ('b','p','a')}|{k:measure(k)for k in ('wild','rustc')}|{'peak_PSS_mib':max(x[3]or 0 for x in run['tree_samples']['samples'])/2**20}
if __name__=='__main__':
    v=parse(sys.argv[1]); vals=[one(r)for r in v]; Path(sys.argv[2]).write_text(json.dumps(vals,sort_keys=True)+'\n')
    for a in 'AB':
        rows=[r for r in vals if r['a']==a]; print(a,'N',len(rows),'last',collections.Counter(x['wild']['last_five_finished'][0]['target']for x in rows))
        for key in ['first_from_cargo_s','span_s','after_last_start_s','last_only_s','shutdown_from_last_s','aggregate_job_s','top10_job_s','top10_median_s','other_median_s','mean_concurrent','max_top10_simultaneous','max_output_gb','secs_4_or_more_top10','pairwise_top10_overlap_s','secs_more_than_1g_live_elf']:
            k=[x['wild'][key] for x in rows];print(key,round(st.median(k),3),list(map(lambda v:round(v,2),k)))
        print('PSS',round(st.median(x['peak_PSS_mib']for x in rows),1))
