"""Count default scheduling opportunities from original typed queue events; these are observed opportunities only."""
from pathlib import Path
import json,gzip,collections,sys
def one(d,index,automatic=False):
    def read(name):return json.loads(gzip.decompress((d/name).read_bytes()))
    stem=f'instrumented{index}';v=read(stem+'.json.gz');ls={r['unit']:r for r in read(stem+'-links.json.gz')['links']}
    ordered=sorted(ls,key=lambda i:(-ls[i]['old_len'],ls[i]['target']))
    cutoff=({i for i,r in ls.items() if r['old_len']>=128*2**20} if automatic else set(ordered[:10])); short={i for i,r in ls.items()if r['old_len']<=(32*2**20 if automatic else 50_000_000)}
    pend=[];running=set();rows=[]
    for t,e in v['events']:
        if e[0]=='edge' and e[2]=='All': running.discard(e[1])
        if e[0]=='dequeue':_,i,pr,index_now,*_=e;pend.insert(index_now,(i,pr))
        if e[0]=='service':
            _,i,pr,active,cap,*_=e;assert pend.pop()==(i,pr)
            if i not in ls:continue
            assert active<cap
            options={j for j,p in pend if p==pr and j in ls}
            rows.append({'ns':t,'selected':ls[i]['target'],'large':i in cutoff,'active_large':len(running&cutoff),'eligible_short':sum(j in short for j in options),'eligible_large':len(options&cutoff),'slots':cap-active,'active':active,'ready_alternatives':len(options)})
            running.add(i)
    assert len(rows)==50
    return {'run':index,'large_count':len(cutoff),'short_count':len(short),'rank10_bytes':ls[ordered[9]]['old_len'],'rows':rows,
        'largest_resume':{str(k):[r['selected']for r in rows if not r['large'] and r['eligible_large']and r['active_large']<k]for k in (2,3,4)},
        'short_filler':{str(k):[r['selected']for r in rows if r['large'] and r['active_large']>=k and r['eligible_short']]for k in (2,3,4)}}
if __name__=='__main__':
    v=[one(Path(sys.argv[1]),i, len(sys.argv)>3)for i in (1,2,3)]; Path(sys.argv[2]).write_text(json.dumps(v,sort_keys=True)+'\n')
    for r in v:print(r['run'],r['short_count'],r['rank10_bytes'],{k:len(l)for k,l in r['short_filler'].items()},{k:len(l)for k,l in r['largest_resume'].items()})
