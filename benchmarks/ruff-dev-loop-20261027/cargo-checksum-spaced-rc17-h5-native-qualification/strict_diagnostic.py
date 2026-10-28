"""Explain, but never release, the native gate of a failed H5 trial."""
from pathlib import Path
from itertools import combinations
import collections,fcntl,hashlib,json,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol-v2'))
import worker as w
import namespace as typed
from audit_elf import changed

def canonical_elf_map(result,raw,namespace):
    """Only replace a component in a path actually returned by Cargo in a typed output field."""
    keys=result['guards']['native_paths']
    pairs={}
    files=set()
    for s in raw['units']:
        r=json.loads(s);files.update(r['filenames'])
        if r['executable']is not None:files.add(r['executable'])
    for n in keys:
        value=str(w.logical_target/n);assert value in files
        path=typed.candidate_dirs(w.logical_target,value)
        if path is None:token=n
        else:
            base,fields=path;assert list(fields[:2])==namespace
            actual=str(base/namespace[0]/namespace[1])+'/'
            assert value.startswith(actual) and value.count(actual)==1
            norm=value.replace(actual,str(base/namespace[0]/'<compiler-matched-namespace>')+'/',1)
            token=str(Path(norm).relative_to(w.logical_target))
        assert token not in pairs;pairs[token]=n
    return pairs

def main():
    q=w.q;location=q/'diagnostic-private';assert location.is_dir()
    assert (q/'launch-train/exit').read_text()=='1' and (q/'launch-audit/exit').read_text()=='1'
    assert not(q/'wall').exists()and not(q/'qualified.json').exists()
    with(w.p/'native-measure.lock').open('rb')as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);w.clean();w.guard()
        grants=w.read(q/'protocol-v2/paths-grant.json');entries={};physical={};where={};states={};cache={};transforms={}
        normal_units=set();diagnostics=set();oracle=set()
        for b,a in [(1,'B'),(1,'C'),(2,'C'),(2,'B')]:
            k=w.state_label(b,a);rr=w.regpath(b,a);root=rr.parent;row=w.read(rr);raw=w.read(root/'roster.json')
            cold=w.read(root.parent/'cold/roster.json')
            value,anch=typed.anchor(w.logical_target,cold['units']);assert value==grants[a]
            n,count=typed.canonical(w.logical_target,raw['units'],value);normal_units.add(typed.digest(n));diagnostics.add(typed.digest(raw['diagnostics']));oracle.add(tuple(row['oracle']))
            assert row['guards']['units']==619 and row['guards']['executables']==102 and row['guards']['harness_profile']==84 and row['guards']['nonharness_profile']==18
            mapping=canonical_elf_map(row,raw,value);assert len(mapping)==110
            assert w.products(b,a,row['guards']['native_paths'])==row['products']
            ledger={x:row['products'][v]for x,v in mapping.items()}
            if entries:assert set(ledger)==set(next(iter(entries.values())))
            entries[k]=ledger;physical[k]=mapping;where[k]=w.alias_state(b,a)/'target'
            states[k]={'receipt':w.sha(rr),'roster':w.sha(root/'roster.json'),'raw_units':typed.digest(raw['units']),'normalized_units':typed.digest(n),'normalized_typed_path_fields':count,'typed_native_paths_matched':len(mapping),'namespace':value,'unicode_ident_anchor':anch,'terminal_counts':[row['full'],row['link_only'],row['wild'],row['fresh']],'harness':row['oracle']}
        assert len(normal_units)==len(diagnostics)==len(oracle)==1
        comparisons={}
        for l,r in combinations(entries,2):
            diffs={};exact=0;allowed=0;rejected=0
            for n,v in entries[l].items():
                other=entries[r][n]
                if v==other:exact+=1;continue
                f=where[l]/physical[l][n];g=where[r]/physical[r][n]
                if v not in cache:cache[v]=w.elf.normalize(f)
                if other not in cache:cache[other]=w.elf.normalize(g)
                a=cache[v];b=cache[other]
                allowed_pair=a['normalized']==b['normalized']and a['bytes']==b['bytes']and a['rodata_entsize']!=b['rodata_entsize'] and min(a['rodata_entsize'],b['rodata_entsize'])==0 and a['build_id']!=b['build_id']
                if allowed_pair:allowed+=1
                else:rejected+=1
                pair=v+'..'+other
                if pair not in transforms and not allowed_pair:
                    transforms[pair]=changed(f,g)
                diffs[n]={'raw':[v,other],'strict_normalization':[a,b],'allowed':allowed_pair,'section_detail':None if allowed_pair else pair}
            assert exact+allowed+rejected==110
            comparisons[l+'..'+r]={'raw_equal':exact,'allowed':allowed,'rejected':rejected,'different':diffs}
        result={'states':states,'physical_paths':physical,'all_native_sha256':entries,'comparisons':comparisons,'different_sections':transforms,'wall_files':0,'scope':'Untimed read-only postfailure diagnosis. Original output, qualified.json and score remain unused.'}
        assert not(q/'wall').exists()
        w.put(location/'structural.json',result)
        print(json.dumps({k:[v['raw_equal'],v['allowed'],v['rejected']]for k,v in comparisons.items()}),flush=True)

if __name__=='__main__':main()
