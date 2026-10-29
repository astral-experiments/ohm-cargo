"""Verify the matched Ruff native commands, active compiler lints, diagnostics, and final products."""
from pathlib import Path
import argparse, gzip, hashlib, json, runpy

HERE=Path(__file__).resolve().parent
CAPTURES=HERE
native=runpy.run_path(str(HERE/'native_detail.py'))
FULL='resolve_with_registry:resolve_with_previous:register_patch_entries:'
HIT='reusing the cached workspace resolution'
NAMES=['invalid_range_deserialization','range_serialization','size_serialization']

def sha(data):return hashlib.sha256(data).hexdigest()
def load(name):
    raw=((HERE if name=='source.json' else CAPTURES)/name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith('.gz') else raw)

def check():
    complete=load('complete.json');source=load('source.json');data=load('streams.json.gz');index=load('raw-file-index.json.gz')
    assert complete['source']==source['ruff'] and complete['workspace_lint_edit']==source['edit']
    assert set(data)=={'A','B'} and len(index)==56
    reports={}
    def verify_streams(arm,name,rec,tag):
        row=rec['row']; streams=rec['streams']; raw=index[arm+'/'+name]; mode,kind=name.split('-',1)
        assert sha((json.dumps(row,indent=2,sort_keys=True)+'\n').encode())==tag
        assert set(raw)==set(streams) and all(sha(v.encode())==raw[f]['projection'] for f,v in streams.items())
        assert all(raw[s]['sha256']==row[k] for s,k in [('stdout','stdout'),('stderr','stderr'),('exec','trace')]); ev=native['native_execs'](streams['exec']); original=row['events']
        assert len(ev)==len(original) and all({k:v for k,v in n.items() if k not in ['argv_sha256','argv']}=={k:v for k,v in o.items() if k!='argv_sha256'} for n,o in zip(ev,original,strict=True))
        comp=sorted(e['crate'] for e in ev if native['is_compile'](e)); links=sorted(e['program'] for e in ev if native['is_link'](e)); assert comp==row['compiles'] and links==row['links'] and all(l=='ld.bfd' for l in links)
        lints=[]
        for e,o in zip(ev,original,strict=True):
            if native['is_compile'](e) and (e['crate']=='ruff_text_size' or any(s.endswith('crates/ruff_text_size/tests/serde.rs') for s in e['argv'])):
                flag='--allow=clippy::large_stack_arrays' in e['argv']; assert flag==(row['manifest']==source['reverse_manifest']);lints.append([e['crate'],flag,o['argv_sha256']]);
                if kind in ('11-denied','12-clean-denied'): assert '--deny=unreachable_pub' in e['argv']
                if kind in ('10-reachable-warning','13-allowed'): assert '--warn=unreachable_pub' in e['argv']
        assert lints==row['observed_lint_argv']
        msgs=[json.loads(s) for s in streams['stdout'].splitlines()];assert msgs[-1]=={'reason':'build-finished','success':row['exit']==0}
        raw_arts=[x for x in msgs if x['reason']=='compiler-artifact']; assert sorted([a['target']['name'],a['fresh']] for a in raw_arts)==row['artifacts']
        assert {f.removeprefix('<arena>/') for a in raw_arts for f in a['filenames']}==set(row['products'])
        errors=[m['message'] for m in msgs if m['reason']=='compiler-message' and m['message']['level']=='error']; assert [[e['code']['code'],e['message'],e['spans'][0]['file_name'],e['spans'][0]['line_start']] for e in errors if e['code']]==row['errors']
        hits=streams['stderr'].count(HIT);full=streams['stderr'].count(FULL);assert (full,hits,hits>0 and full==0)==(row['full_workspace_resolutions'],row['cache_hits'],row['hit']) and (full or hits)
        if kind in ('06-invalid','07-clean-invalid','11-denied','12-clean-denied'):
            assert row['exit']==101 and comp==['ruff_text_size'] and not links and len(errors)==1
            assert errors[0]['code']['code']==('E0308' if 'invalid' in kind else 'unreachable_pub')
        else: assert row['exit']==0 and not errors
        if kind in ('02-repeat','04-repeat','09-final'): assert not comp and not links and hits and not full and all(f for _,f in row['artifacts'])
        if kind in ('03-reverse','08-restored','11-denied','13-allowed'):
            assert (full==0)==(arm=='B') and (hits or arm=='A')
            assert (comp,links)==((['ruff_text_size','serde'],['ld.bfd']) if mode=='test' else (['ruff_text_size'],[]))
        if mode=='test':
            executable,=[a['executable'].removeprefix('<arena>/') for a in raw_arts if a['target']['name']=='serde' and a['executable']]; assert row['exe']==row['products'][executable]
            assert row['names']==NAMES==sorted(s[:-6] for s in streams['test-list'].splitlines() if s.endswith(': test'))
            assert '3 passed; 0 failed' in streams['test-verdict'] and all('test '+n+' ... ok' in streams['test-verdict'] for n in NAMES)
        if mode=='build': assert row['consumer_stdout']=='17 29 12\n'
        return row
    for arm,terminal in zip('AB',complete['arms'],strict=True):
        assert terminal['cargo']==source[arm] and set(terminal['rows'])==set(data[arm]) and len(data[arm])==28
        table={name:verify_streams(arm,name,row,terminal['rows'][name]) for name,row in data[arm].items()}
        for m,f in [('build','consumer_sha256'),('check','consumer_sha256'),('test','exe')]:
            assert table[m+'-03-reverse'][f]==table[m+'-05-clean-edited'][f]
            assert table[m+'-08-restored'][f]==table[m+'-01-original'][f]
        assert table['check-11-denied']['errors']==table['check-12-clean-denied']['errors'] and table['check-06-invalid']['errors']==table['check-07-clean-invalid']['errors']
        reports[arm]=table
    for name,a in reports['A'].items():
        b=reports['B'][name]
        for key in ('manifest','lock','lib','exit','errors','compiles','links','artifacts','exe','names','verdict','consumer_stdout'):
            assert a.get(key)==b.get(key),(name,key)
    repeats=sum(name.split('-',1)[1] in ('02-repeat','04-repeat','09-final') for arm in reports.values() for name in arm)
    tests=sum(len(row.get('names',[])) for arm in reports.values() for row in arm.values())
    assert repeats==18 and tests==42
    return f'Verified 56 Cargo commands, {repeats} fully fresh repeats, all {tests} serde test cases, both failing diagnostics and their independent clean controls.'
if __name__=='__main__':
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument('--captures',type=Path,default=HERE);CAPTURES=arg.parse_args().captures
    print(check())
