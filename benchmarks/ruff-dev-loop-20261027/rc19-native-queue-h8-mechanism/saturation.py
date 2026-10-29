"""Inspect matched per-target service, conditional on the count of other large links already writing at launch."""
import gzip,json,math,statistics as st,sys
from pathlib import Path
def compare(matrix):
    rows=[]
    for left,right in zip(matrix[::2],matrix[1::2]):
        assert (left['b'],left['p'],left['a'])==(right['b'],right['p'],'A')and right['a']=='B'
        bins=left['bins'];large=set(sorted(bins,key=lambda n:(-bins[n]['output_bytes'],n))[:10])
        for n in bins:
            data={}
            for run in (left,right):
                entry=run['bins'][n];s,e=entry['wild']
                start=sum(run['bins'][j]['wild'][0]<=s<run['bins'][j]['wild'][1]for j in large-{n})
                mean=sum(max(0,min(e,run['bins'][j]['wild'][1])-max(s,run['bins'][j]['wild'][0]))for j in large-{n})/(e-s)
                data[run['a']]={'heavy_before':start,'mean_other_heavy':mean,'elapsed_ms':(e-s)/1e6}
            a,b=data['A'],data['B']
            rows.append({'b':left['b'],'p':left['p'],'name':n,'large':n in large,'arms':data,'B_over_A':b['elapsed_ms']/a['elapsed_ms']})
    return rows
def summarize(rows):
    def result(xs):
        val=[r['B_over_A'] for r in xs];return {'count':len(val),'slower':sum(v>1 for v in val),'median_ratio':st.median(val),'geo_ratio':math.exp(st.mean(math.log(v)for v in val))}if val else {}
    fs={'top10':lambda r:r['large'],'other40':lambda r:not r['large'],'top10_entering_at_least_three_vs_two_or_fewer':lambda r:r['large']and r['arms']['B']['heavy_before']>=3>r['arms']['A']['heavy_before'],
        'top10_more_heavy_before':lambda r:r['large']and r['arms']['B']['heavy_before']>r['arms']['A']['heavy_before'],
        'others_more_heavy_before':lambda r:not r['large']and r['arms']['B']['heavy_before']>r['arms']['A']['heavy_before']}
    return {k:result([r for r in rows if f(r)])for k,f in fs.items()}
if __name__=='__main__':
    rows=compare(json.loads(gzip.decompress(Path(sys.argv[1]).read_bytes())));out={'summary':summarize(rows),'grouped':rows}
    Path(sys.argv[2]).write_text(json.dumps(out,sort_keys=True)+'\n');print(out['summary'])
