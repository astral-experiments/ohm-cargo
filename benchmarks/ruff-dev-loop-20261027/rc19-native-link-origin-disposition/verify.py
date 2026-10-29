"""Replay the portable native, Cargo JSON and source-history verdicts. No compiler is executed."""
import ast
import gzip
import hashlib
import json
import re
import tarfile
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def events(stream):
    result = []
    for row in stream.decode().splitlines():
        assert '<unfinished ...>' not in row and ' resumed>' not in row
        if not re.search(r'\)\s+= 0$', row):
            continue
        match = re.fullmatch(r'(\d+)\s+execve\(("(?:\\.|[^"\\])*"), (\[.*\]), (.*)\)\s+= 0', row)
        assert match, row[:110]
        image, argv = ast.literal_eval(match[2]), ast.literal_eval(match[3])
        assert all(isinstance(x, str) for x in argv)
        result.append((Path(image).name, argv))
    return result

def field(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None

def main():
    ledger = json.loads(gzip.decompress((root/'ledger.json.gz').read_bytes()))
    assert ledger['schema'] == 1 and ledger['diagnostic_only']
    with tarfile.open(root/'streams.tar.gz','r:gz') as archive:
        data = {}
        for member in archive:
            assert member.isfile() and member.name not in data and not member.name.startswith('/') and '..' not in Path(member.name).parts
            data[member.name] = archive.extractfile(member).read()
    assert data.keys() == ledger['files'].keys()
    for key, raw in data.items():
        length, oldhash, n, sha = ledger['files'][key]
        assert length >= 0 and len(oldhash) == 64 and [len(raw),digest(raw)] == [n,sha]
        assert (str(Path.home()).encode()+b'/') not in raw and b'/mnt/devbox-' not in raw
    refs = json.loads((root/'pr-readback.json').read_bytes())['prs']
    subjects = ledger['subjects']
    assert refs['28']['state'] == 'closed' and not refs['28']['merged']
    assert refs['72']['state'] == 'open' and not refs['72']['draft']
    assert subjects['before-28']['source'] == refs['28']['head']['sha']
    assert subjects['before-72']['source'] == refs['72']['head']['sha']
    assert subjects['parent-72']['source'] == refs['72']['base']['sha'] == refs['71']['head']['sha']
    assert refs['29']['base']['sha'] == refs['28']['head']['sha'] and refs['73']['base']['sha'] == refs['72']['head']['sha']
    candidate = json.loads((root/'optional-source.json').read_bytes())
    assert candidate['parent'] == subjects['before-72']['source'] and candidate['head'] == subjects['after-final-72']['source']
    assert candidate['release_source'] == 'fd872c053bb1e9dcde722cf90a05a7cb8335dd32'
    assert digest((root/'optional-codegen.patch').read_bytes()) == candidate['patch_sha256']
    assert {r['rustc'] for r in subjects.values()} == {'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'}
    allhist = {}
    testjobs = preparation = 0
    product = {k:v['product'] for k,v in subjects.items()}
    for label, hist in ledger['histories'].items():
        mode = hist['mode']; history = []
        for item in hist['rows']:
            phase = item['phase']; prefix=f'{label}/{phase}'
            paths = {}
            for sub in ('test','prepare'):
                path=f'{prefix}/{sub}/'
                if path+'exec.log' not in data:
                    assert sub == 'prepare'
                    continue
                if sub == 'test': testjobs += 1
                else: preparation += 1
                ev = events(data[path+'exec.log'])
                msgs = [json.loads(line) for line in data[path+'stdout'].splitlines() if line.startswith(b'{')]
                assert msgs[-1] == {'reason':'build-finished','success':sub=='prepare' or item['cargo']==0}
                rust = [(field(argv,'--crate-name'),'link-only' if any(x in ('link-only','-Zlink-only') for x in argv) else 'compile')
                        for exe,argv in ev if exe=='rustc' and field(argv,'--crate-name')]
                probe_links = [(exe,field(argv,'-o')) for exe,argv in ev if exe in ('rust-lld','ld','ld.bfd') and field(argv,'-o')
                               and re.match(r'probe-[0-9a-f]{16}$',Path(field(argv,'-o')).name)]
                arts=[(j['target']['name'],j['fresh']) for j in msgs if j['reason']=='compiler-artifact' and j['target']['name']=='probe']
                dirs=[(j['out_dir'],j['linked_paths']) for j in msgs if j['reason']=='build-script-executed']
                if mode in ('staged','staged-upgrade'):
                    assert len(dirs)==1 and len(dirs[0][1])==2
                    out,links=dirs[0]
                    assert links==['native='+out+'/early','native='+out+'/fallback']
                    paths[sub]=(out,tuple(links))
                else: assert not dirs
                if sub=='prepare':
                    assert any(exe == 'ar' for exe,_ in ev)
                    assert any(re.fullmatch(r'build[-_]script[-_]build(?:-[a-f0-9]{16})?',exe) for exe,_ in ev)
                    continue
                if item['cargo']==0:
                    assert len(arts)==1
                    if 'fresh' in item:assert arts[0][1] == item['fresh']
                elif arts:raise AssertionError((label,phase,arts))
                codes={m['message']['code']['code'] for m in msgs if m['reason']=='compiler-message' and m['message'].get('code')}
                if (phase in ('invalid','empty-invalid') and mode=='pure') or (mode=='public' and item['cargo']==101):
                    assert codes.intersection({'E0308','E0412','E0425'}), (label,phase,codes)
                elif item['cargo']==101:
                    assert len(probe_links)==1 and any('linking with' in m['message']['message'] for m in msgs if m['reason']=='compiler-message'),(label,phase)
                if item['cargo']==0:
                    rend = data.get(path+'native.stdout', data.get(path+'runtime.out'))
                    assert rend is not None
                    if mode in ('staged','staged-upgrade','implicit'):
                        matches=re.findall(rb'native-choice=(\d+)',rend)
                        if item['native_exit']==0:
                            assert len(matches)==1 and int(matches[0])==item['value']
                        else:
                            assert item['native_exit']==83 and item['value'] is None and not matches
                        assert len(item['hash'])==64
                    elif mode=='public':
                        assert b'probe-checked\n' in rend and item['test_exit']==0
                        assert int(data[path+'caller.stdout'])==item['caller_value']
                    else:assert re.findall(rb'value=(\d+)',rend)==[str(item['value']).encode()]
                history.append((phase,item['cargo'],item.get('native_exit'),item.get('value'),[how for crate,how in rust if crate=='probe'],[exe for exe,_ in probe_links],item))
            if 'prepare' in paths: assert paths['prepare']==paths['test']
        allhist[label]=history
    # The exact one-commit parent and both disabled switches agree on the exposed actual native outcomes.
    constant=[(0,17),(0,17),(0,17),(0,17),(0,17),(0,17),(0,17)]
    correct=[(0,17),(0,17),(0,29),(0,29),(101,None),(101,None),(0,17)]
    for name in ('origin28-enabled','origin72-enabled','origin28-disabled','origin72-disabled','parent72','optional-declared'):
        rows=allhist[name]
        broken=name.endswith('-enabled')
        assert [(r[1],r[3]) for r in rows]==(constant if broken else correct)
        assert all(bool(rows[i][5]) == (not broken) for i in (2,4,5))
        assert all(not rows[i][5] for i in (1,3))
    for name,ret,val in [('optional-empty-valid',0,29),('optional-empty-malformed',101,None)]:
        r,=allhist[name];assert (r[1],r[3])==(ret,val) and r[5]==['rust-lld']
    for arm in ('origin','optional'):
        for label in ('warm','disabled','pure-external-only','empty-valid','empty-bad'):
            rows=allhist[f'implicit-{arm}-{label}']
            if len(rows)==1:
                assert [(r[1],r[2]) for r in rows]==([(0,83)] if label=='empty-valid' else [(101,None)])
            else:
                expected=[(0,0)]*7 if label=='pure-external-only' or (arm=='origin' and label=='warm') else [(0,0),(0,0),(0,83),(0,83),(101,None),(101,None),(0,0)]
                assert [(r[1],r[2]) for r in rows]==expected
                if label=='pure-external-only':assert all(not r[4] and not r[5] for r in rows[1:])
    for arm in ('parent-72','before-72','after-final-72'):
        unused=allhist['public-'+arm+'-unused'];used=allhist['public-'+arm+'-used']
        assert [r[6]['caller_value'] for r in unused]==[17,17,29,29,29,17]
        assert unused[2][5]==unused[-1][5]==['rust-lld']
        assert unused[2][4]==unused[-1][4]==(['link-only'] if arm=='after-final-72' else ['compile'])
        assert [(r[1],r[5]) for r in used[2:5]]==[(101,[])]*3
        assert all('E0425' in r[6]['diagnostics'] for r in used[2:5])
        assert all(not unused[i][4] and not unused[i][5] for i in (1,3))
    for arm in ('before-72','after-final-72'):
        pure=allhist['pure-'+arm+'-work']
        assert [(r[1],r[3]) for r in pure]==[(0,1),(0,1),(0,2),(0,2),(0,2),(101,None),(101,None),(0,1)]
        assert all(pure[i][6]['diagnostic']=='E0308' for i in (5,6))
    for state in ('valid','malformed'):
        rows=allhist['same-path-upgrade-'+state];assert len(rows)==7
        assert all((r[1],r[3])==(0,17) for r in rows[:3])
        assert (rows[5][1],rows[5][3])==((0,29) if state=='valid' else (101,None))
        assert rows[5][5]==['rust-lld']
    for name,row in ledger['suites'].items():
        stem='suites/'+name+'/';mount=json.loads(data[stem+'mounted.json'])
        assert mount['uid']==1000 and mount['root_uid']==0 and mount['same_inode'] and set(mount['caps'].values())=={'0000000000000000','1'}
        assert mount['sha256']==row['product']==product['before-72' if name.startswith('before') else 'after-final-72']
        assert int(data[stem+'exit'])==row['result']
        children=json.loads(data[stem+'exec.log'])
        assert sum(x['same_compared_cargo'] for x in children)==row['physical_compared_cargo_execs']>0
        stdout=data[stem+'stdout']
        if name.startswith('after'):
            assert row['result']==0 and b'1 passed; 0 failed;' in stdout
        else:assert row['result']==101 and b'0 passed; 1 failed;' in stdout
    print(len(allhist),'histories;',testjobs,'primary Cargo commands;',preparation,'separately staged providers;',len(ledger['suites']),'historical/fixed suite executions;',len(data),'original stream/projection pairs.')
    return allhist

if __name__=='__main__':
    main()
