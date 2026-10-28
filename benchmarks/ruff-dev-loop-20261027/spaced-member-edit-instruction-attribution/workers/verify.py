"""Verify the source-specific native gates and every separately collected process counter."""
from collections import defaultdict
from pathlib import Path
import hashlib,json,os,statistics
d=Path(__file__).resolve().parent;read=lambda f:json.loads(f.read_bytes())
for line in (d/'SHA256SUMS').read_text().splitlines():
    h,n=line.split('  ',1);assert hashlib.sha256((d/n).read_bytes()).hexdigest()==h,n
design=read(d/'native-design.json');subs=design['stub']
assert read(d/'zip-builder.json')['B']==read(d/'zip-builder.json')['C']
summary={}
for root,endpoints in [('ir-children-v2',8),('history-v1',12),('cargo-grind-v2',8)]:
    base=d/root; rr=sorted(base.glob('*/native.json'));assert len(rr)==endpoints
    subjects=defaultdict(list)
    for f in rr:
        arm=f.parent.name.split('-',1)[1];row=read(f);edit=row['edited-products'];fresh=row['settled-products']
        assert edit['stage']==fresh['stage'] and edit['zip']==fresh['zip'] and edit['typed']==fresh['typed']
        assert edit['caller_sha']==fresh['caller_sha']==subs[edit['stage']] and edit['caller_bytes']==fresh['caller_bytes']>2000
        assert len(edit['outputs'])==len(edit['typed'])==5
        if root=='history-v1':
            expect=[[['ty_vendored','full'],['ty_wasm','full']],1] if arm=='forced' else [[],0]
            assert row['repeated_commands']==expect,(f,row['repeated_commands'])
        if (f.parent/'counts.json').is_file():
            scores=read(f.parent/'counts.json');assert sorted(scores)==['build_script_build','rustc:ty_vendored','rustc:ty_wasm']
            seen=set()
            for file in f.parent.glob('*.count'):
                rr_=[x.split() for x in file.read_text().splitlines()];pid=file.stem.split('-')[0];assert rr_[0]==['B',pid,'0','0'] and rr_[-1]==['P',pid,'0','0']
                ts=sorted((a[1],a[2]) for a in rr_ if a[0]=='T');fs=[a for a in rr_ if a[0]=='F']
                assert ts==sorted((a[1],a[2]) for a in fs) and len(ts)==len(set(ts))
                checksum=hashlib.sha256(file.read_bytes()).hexdigest();name,=[n for n,v in scores.items() if v['count_sha']==checksum]
                assert sum(int(a[3]) for a in fs)==scores[name]['total']>0 and len(ts)==scores[name]['threads'];seen.add(name)
            assert seen==set(scores)
            subjects[arm].append({k:v['total'] for k,v in scores.items()})
        elif (f.parent/'supervisor.json').is_file():
            s=read(f.parent/'supervisor.json');assert s['ir']>100000000 and s['argv'][1:]==['build','--locked','--offline','-j4'];subjects[arm].append({'cargo':s['ir']})
    if subjects:
        left,right=('normal','forced') if root=='history-v1' else ('B','C')
        assert [len(subjects[a]) for a in (left,right)]==[4,4]
        data={}
        for k in subjects[left][0]:
            a=[v[k] for v in subjects[left]];b=[v[k] for v in subjects[right]]
            diff=[y-x for x,y in zip(a,b)]
            data[k]={'L_median':statistics.median(a),'R_median':statistics.median(b),'min_delta':min(diff),'median_delta':statistics.median(diff),'max_delta':max(diff)}
        summary[root]=data
plain=read(d/'unspaced.json');assert sorted(plain)==['B','C']
for i,r in enumerate(plain['B']):
    c=plain['C'][i];assert r['zip']==c['zip'] and r['outputs']['debug/libty_wasm.so']==c['outputs']['debug/libty_wasm.so']
    for a in (r,c):
        assert a['units']==304 and a['caller_sha']==subs[a['stage']]
        if a['step'] in ('edit','restore'):assert sorted(a['jobs'])==[['ty_vendored','full'],['ty_wasm','full']] and a['wild']==1
        elif a['step']!='cold':assert a['jobs']==[] and a['wild']==0 and not a['dirty']
assert len(plain['B'])==len(plain['C'])==7
assert len(read(d/'sampled-resources.json'))==16
assert read(d/'rejected-all-process.json')['accepted'] is False and read(d/'rejected-cargo-startup.json')['accepted'] is False
if (d/'isolated-real-zip.json').is_file():
    z=read(d/'isolated-real-zip.json');assert 1400000<z['bytes']<1600000 and len(z['results'])==16
    for r in z['results']:assert bool(r['potential_checksum'])==(r['image']=='C' or r['case']=='equal')
print(json.dumps(summary,sort_keys=True,indent=2))
