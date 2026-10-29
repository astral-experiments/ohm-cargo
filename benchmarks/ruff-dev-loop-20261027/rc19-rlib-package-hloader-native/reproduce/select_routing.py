"""Read corresponding typed Cargo artifacts without copying absolute source paths."""
from collections import Counter,defaultdict
from pathlib import Path
import hashlib,json,sys
def collect(reports):
    def sha(b):return hashlib.sha256(b).hexdigest()
    def corpus(name):
        p=reports/name/'cargo.jsonl';out={}
        for row in p.read_text().splitlines():
            x=json.loads(row)
            if x.get('reason')!='compiler-artifact':continue
            names=x['filenames']
            key=(x['target']['name'],tuple(x['target']['kind']),tuple(sorted(Path(v).name for v in names)),
                 tuple(sorted(x['features'])),sha(json.dumps(x['profile'],sort_keys=True).encode()),sha(x['package_id'].encode()))
            assert key not in out,(key,name)
            vals=[]
            for path in names:
                s=Path(path);idx=s.parts.index('active')
                logical='/'.join(s.parts[idx+1:]);assert logical.startswith(('target/debug/','shared/debug/'))
                vals.append(logical)
            out[key]=(sorted(vals),x['fresh'])
        return out
    by_phase={k:corpus(k)for k in ['stock-reverse-traced','real-cow-edited','real-observe-edited','real-malformed-edited','real-restored-edited','independent-empty-edited']}
    s=by_phase['stock-reverse-traced'];a=by_phase['real-observe-edited'];c=by_phase['real-cow-edited']
    assert len(s)==len(a)==len(c)==248 and s.keys()==a.keys()==c.keys()
    noroute=0;swap=0;path_count=0;same_tail=0;table={}
    for k in sorted(s):
        sp,st=s[k];ap,at=a[k];cp,ct=c[k];assert ap==cp and at==ct
        if sp==ap:
            noroute+=1;continue
        swap+=1;assert len(sp)==len(ap)
        for x,y in zip(sp,ap):
            assert x.startswith('shared/debug/build/registries/')and y.startswith('target/debug/build/workspaces/')
            same_tail+=(x.split('registries/')[1]==y.split('workspaces/')[1].split('/',1)[1]);path_count+=1
        table[sha(json.dumps(k,separators=(',',':')).encode())]={'target':k[0],'kind':k[1],'stock':sp,'observe_and_cow':ap}
    assert swap>0 and path_count==same_tail
    return {'total':len(s),'unchanged_typed_paths':noroute,'relocated_typed_rows':swap,'relocated_literal_file_paths':path_count,
            'same_unit_suffix_for_each_relative_path':True,'raw_sha256':{k:sha((reports/k/'cargo.jsonl').read_bytes())for k in by_phase},
            'relocated':table,
            'counts':{k:{'rows':len(v),'rebuilt':sum(not f for _,f in v.values()),'truly_fresh':sum(f for _,f in v.values())}for k,v in by_phase.items()},
            'source':{'cargo':'7caf39914da1e28a67744ecbc963a5f26361474d','injection':'src/compiler/mod.rs:183',
                      'presence_check':'src/compiler/build_runner/compilation_files.rs:388','trust_policy':'src/compiler/build_runner/compilation_files.rs:548'}}
if __name__=='__main__':print(json.dumps(collect(Path(sys.argv[1])),indent=2,sort_keys=True))
