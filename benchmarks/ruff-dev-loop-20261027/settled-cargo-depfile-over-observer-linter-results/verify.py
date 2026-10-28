"""Verify raw per-thread Cargo counts, native outputs, migration behavior and the registered test."""
from collections import Counter
from pathlib import Path
import hashlib, itertools, json, math, re, statistics, sys, tarfile
D=Path(__file__).resolve().parent
sha=lambda b: hashlib.sha256(b).hexdigest()
def load_file(n):return json.loads((D/n).read_bytes())
def unpack(n):
    by=load_file(n+'-files.json')
    with tarfile.open(D/(n+'.tar.gz'),'r:gz') as t:
        assert set(by)==set(t.getnames()) and len(by)==len(t.getnames())
        data={k:t.extractfile(k).read() for k in by}
    assert all(sha(v)==by[k][1] for k,v in data.items())
    return data,by
def roster(bundle,prefix):
    raw=[]
    for n,v in bundle.items():
        if n.startswith(prefix) and '/exec.' in n[len(prefix)-1:]:
            raw.extend(line for line in v.decode().splitlines() if 'execve("' in line and line.endswith('= 0'))
    return [s.split('execve("',1)[1].split('"',1)[0] for s in raw], [m[1] for s in raw if (m:=re.search(r', "--crate-name", "([^"]+)"',s))]
def artifacts(data):
    return [j for line in data.splitlines() if (j:=json.loads(line)).get('reason')=='compiler-artifact']
def main():
    if (D/'SHA256SUMS').exists():
        manifest={s.split('  ',1)[1]:s.split('  ',1)[0] for s in (D/'SHA256SUMS').read_text().splitlines()}
        assert set(manifest)=={str(p.relative_to(D)) for p in D.rglob('*') if p.is_file() and p!=D/'SHA256SUMS'}
        assert all(sha((D/k).read_bytes())==h for k,h in manifest.items())
    p=load_file('plan.json');assert sha((D/'plan.json').read_bytes())=='0cf121cfe40941fdc892996ce468111038b4fcc2202cf610c8882a3d67ce8cf9'
    native,nb=unpack('native');counters,cb=unpack('counters');migration,mb=unpack('migration');control,xb=unpack('controls');stats=load_file('qualified-pair.json')
    assert sha((D/'qualified-pair.json').read_bytes())==p['matched_pair']==nb['qualified-pair.json'][0]
    for arm in ('parent','candidate'):
        row=stats[arm];assert row['cargo']==p['subjects'][arm] and row['common']==p['common_nonproduct_inputs'] and row['pgo']==p['compiler_build_profile'] and row['source']==p['source']['base'] and row['verified']==3108
        assert row['actual']==sha((D/'pgo'/(arm+'.json')).read_bytes())
    pr=load_file('pgo/parent.json');ca=load_file('pgo/candidate.json')
    for src,v in pr.items():
        x=ca[src];assert v.keys()==x.keys() and v['argv']==x['argv']
        for k in v:
            if k!='externs':assert v[k]==x[k]
        assert v['externs'].keys()==x['externs'].keys()
        for k in v['externs']:
            if k!='cargo':assert v['externs'][k]==x['externs'][k]
    base='qualified-261-linter/library/';a=json.loads(native[base+'qual/anchor.json']);assert a==json.loads(native[base+'qual/parent.json'])==json.loads(native[base+'qual/candidate.json'])
    assert a['units']==268 and len(a['products'])==len(a['product_stamps'])==492 and len(a['dot_d'])==1 and not a['legacy_rewrites'] and all(x[0]>0 for x in a['proofs'].values())
    for arm in ('parent','candidate'):
        n=base+'qual/saved-dotd-'+arm+'/libruff_linter.d';assert set(a['dot_d'].values())=={nb[n][0]}
    for phase in ('qual/trace-parent','qual/trace-candidate','post-ir'):
        n=base+phase+'/';r=json.loads(native[n+'record.json']);u=artifacts(native[n+'stdout']);actual,comps=roster(native,n)
        assert sorted(r['physical'])==sorted(actual) and not comps and len(actual)==2 and all(Path(x).name=='cargo' for x in actual)
        assert r['units']==len(u)==268 and all(x['fresh'] for x in u) and all('ron@' not in x['package_id'] for x in u)
        assert set(r['products'])==set(a['products'])=={f for x in u for f in x['filenames']};assert r['stdout']==nb[n+'stdout'][0]
    mig=json.loads(migration['restored/complete.json']);cases=('tracked-file','include-str','include-bytes')
    for case in cases:
        old=json.loads(migration[f'original/{case}/report.json']);assert old['before']['mtime']==old['after']['mtime'] and old['before']['size']==old['after']['size'] and old['before']['inode']!=old['after']['inode'] and old['rows']['again']['value']==17 and old['rows']['clean']['value']==29
        assert mig['parent/'+case]==mig['candidate/'+case]
        for arm in ('parent','candidate'):
            prefix=f'restored/{arm}/{case}/';v=json.loads(migration[prefix+'stock-same-slot/result.json']);assert v['value']==17 and v['fresh']==4 and v['compiler_calls']==0
            whole,comps=roster(migration,prefix+'stock-same-slot/');assert not comps and len(whole)==2
            assert all(r['fresh'] for r in artifacts(migration[prefix+'stock-same-slot/cargo.jsonl']))
            for phase,s in mig[arm+'/'+case].items():
                n=prefix+phase+'/';assert json.loads(migration[n+'row.json'])==s and v['slot']==s['slot']
                assert s['value']==29 and s['complete']==0 and s['dirty']==s['compiler_calls']==['hold_direct'] and s['units']==4
                assert roster(migration,n)[1]==s['compiler_calls']
                assert [(r['target']['name']) for r in artifacts(migration[n+'cargo.jsonl']) if not r['fresh']]==['hold_direct']
                for k,file in [('program','program'),('encoded','encoded.obs1'),('public','public.d'),('rustc','rustc.d')]:assert s[k]==mb[n+file][0]
                assert b'sample=29' in migration[n+'program'] and b'ohm-foreign-span-bytes' in migration[n+'public.d'] and b'ohm-foreign-span-bytes' in migration[n+'rustc.d']
    tests=json.loads(control['tests/test-results.json'])
    for k,num in [('all-library',406),('dep-info',15),('generated',2)]:assert tests[k]['rc']==0 and f'{num} passed; 0 failed' in tests[k]['result'][0] and tests[k]['log']==xb['tests/'+k+'.log'][0]
    for k in ('output-wire-control','package-controls-v3'):
        result=json.loads(control[k+'/complete.json']);assert result['parent']==result['candidate']
    assert result['parent']['before']==17 and result['parent']['after']==29 and result['parent']['nonutf_rc']==101
    effects=[];seq=[];logdiff=[];medians=[[],[]]
    for i,order in enumerate(p['orders']['library']['ir']):
        pair={}
        for j,arm in enumerate(order):
            n=f'{i:02}-{j}-{arm}/';r=json.loads(counters[n+'record.json']);f,=[k for k in counters if k.startswith(n+'profile-')];arg,=[k for k in counters if k.startswith(n) and k.endswith('-cargo.args')]
            assert cb[f][0]==r['count_sha256'] and sha(counters[n+'stdout'])==r['stdout']==sha(b'') and r['stderr']==cb[n+'stderr'][0] and r['rc']==0
            assert counters[arg]==b'\0'.join(x.encode() for x in r['argv'])+b'\0' and r['argv'][1:]==['build','--lib','--locked','--offline','-j4']
            rows=[v.split() for v in counters[f].decode().splitlines()];assert rows[0][0]=='B' and rows[-1][0]=='P' and len({v[1] for v in rows})==1
            starts=[v[2] for v in rows if v[0]=='T'];ends={v[2]:int(v[3]) for v in rows if v[0]=='F'};assert len(starts)==len(ends)==len(set(starts)) and set(starts)==set(ends) and ends==r['threads'] and sum(ends.values())==r['ir']
            pair[arm]=r['ir']
        b,c=pair['parent'],pair['candidate'];medians[0].append(b);medians[1].append(c);logdiff.append(math.log(b/c));seq.append(math.log(pair[order[0]]/pair[order[1]]));effects.append(100*(b-c)/b)
    assert len(effects)==16 and sum(x[0]=='parent' for x in p['orders']['library']['ir'])==8
    total=sum(seq);observed=sum(logdiff);rands=[2*sum(seq[i] for i in ids)-total for ids in itertools.combinations(range(16),8)]
    assert len(rands)==12870;prob=sum(x>=observed-1e-12 for x in rands)/len(rands);e=statistics.median(effects);lo,hi=sorted(effects)[3],sorted(effects)[12];better=sum(x>0 for x in effects)
    return dict(pairs=16,parent_median=statistics.median(medians[0]),candidate_median=statistics.median(medians[1]),paired_median_percent=e,median_interval_percent=[lo,hi],favorable=better,one_sided_p=prob,qualified=e>=1 and better>=13 and lo>0 and prob<.05,individual_pair_percent=effects)
if __name__=='__main__':
    results=main();dest=D/'results.json'
    if dest.exists():assert results==load_file('results.json')
    print(json.dumps(results,sort_keys=True,indent=2))
