"""Verify the matrix, independent compiler-reader replay, and real native Ruff receipts."""
from pathlib import Path
import hashlib, gzip, json

p = Path(__file__).resolve().parent
def sha(b):
    return hashlib.sha256(b).hexdigest()
def data(n):
    return json.loads(gzip.decompress((p/(n+'.json.gz')).read_bytes()))
matrix, scope, ruff, ordinary = (data(n) for n in ('matrix','scope','ruff','ordinary'))
old = '52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'
new = '748e5862ece9b0e3098cdae472e1b0d94c50da724b8438f2e267c9007aee8737'
stock = '618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
three = ['before','edit','clean']
crashes = {'mixed-forced-check','release-dylib-check','release-dylib-rlib','release-mixed','release-position-only','release-pure-dylib','release-rlib-dylib','release-staticlib-rlib','rlib-forced-check'}
for arm,driver in [('shipped',stock),('parent',old),('fixed',new)]:
    part=matrix['suites'][arm]
    assert part['identities']['driver']==driver
    assert len(part['cases']) == 22
    assert {k for k,v in part['cases'].items() if v['edit']['ice']} == (set() if arm=='fixed' else crashes)
    for n,v in part['cases'].items():
        for phase in three:
            assert all(len(c['raw'])==64 for c in v[phase]['rustc'])
        if n in ('release-cdylib-only','release-private-before-staticlib'):
            assert all(v[x]['status']==101 and 'E0433' in v[x]['stderr'] and not v[x]['ice'] for x in three)
        elif n=='release-dylib':
            assert all(v[x]['status']==101 and not v[x]['ice'] for x in three)
        elif arm=='fixed':
            assert all(v[x]['status']==0 for x in three)
            if v['edit']['exe_output'] is not None:
                assert [v[x]['exe_output'] for x in three]==['17','29','29']
                assert v['edit']['executable_sha']==v['clean']['executable_sha'],n
    for name,r in part['run_make'].items():
        assert r['status']==0 or (arm!='fixed' and name=='runmake-module-child')
    assert ('module_children(input[' in part['cases']['release-mixed']['edit']['stderr']) == (arm!='fixed')
assert [matrix['upstream'][x]['row']['exe_output'] for x in three]==['17','29','29']
assert len(scope['fixed2']['column'])==6
for v in scope['fixed2']['column'].values():
    a,b,c,d=v['rows']
    assert [x['prefix_reused_message'] for x in (a,b,c,d)]==[False,True,False,True]
    assert (a['public_hash']==c['public_hash']) == (v['emit']=='metadata')
    if a.get('column') is not None:
        assert c['column']==a['column']+256
for arm,v in scope.items():
    for k,rs in v['direct'].items():
        phases=['base','warm','fresh-reader-only','fresh-producer-and-reader']
        assert [rs[x]['value'] for x in phases]==['1','1','257','257']
        assert all(rs[x]['return']==0 for x in phases)
        assert rs['warm']['producer']==rs['fresh-reader-only']['producer']
    if 'cargo' in v:
        assert all(r['baseline']['runtime']=='1' and r['move']['runtime']=='1' and r['empty']['runtime']=='257' for r in v['cargo'].values())
for name in ('parent','fixed','fixed2'):
    rs=scope[name]['direct']['rdr-rlib-cdylib']
    assert (rs['base']['cratehash']!=rs['warm']['cratehash']) == (name=='fixed2')
for k,v in ordinary.items():
    assert all(row[-2:]==[0,False] for rows in v['results'].values() for row in rows)
ignore=scope['fixed2']['opt_in_ignore_spans']
assert ignore['ignore-producer-only'][1][-2:]==[101,True]
assert all(r[-2:]==[0,False] for k in ['normal','ignore-both'] for r in ignore[k])
assert scope['fixed2']['final_runmake']['status']==0
for arm,driver in [('parent',old),('fixed',new)]:
    w=ruff[arm]
    assert w['inputs']['driver']==driver
    assert w['inputs']['git']=='93526150df078af7dd8fc4226cdcc469539d2001'
    assert w['inputs']['patches']=={'parser':'e98e3786c9911e16a5c515d7100bff55851c0e0b78a4acb5ed0053251080264c','doc':'3f1869c672cf721af6ff04f0b84fe437212f0c7718bf96473caaf61d51bec1d1'}
    m=w['phases']; orig=m['settled']
    assert len(orig['units'])==373 and all(v['fresh'] for v in orig['units'])
    assert not orig['decoded']
    for step,producer,fresh in [('parser','ruff_python_parser',357),('doc','ruff_linter',366)]:
        for change in ('edit','restore'):
            key=step+'-'+change
            r=m[key]
            assert r['status']==0 and len(r['units'])==373 and sum(v['fresh'] for v in r['units'])==fresh
            rust=[(v['crate'],v['mode'],v['primary']) for v in r['decoded'] if v['program']=='rustc']
            assert sorted(rust)==sorted([(producer,'full','lib.rs'),('ruff','link-only','ruff.rlink')])
            assert len([v for v in r['decoded'] if v['program']=='wild'])==1
            assert r['public']==orig['public']
            assert (r['exe']!=orig['exe']) == (step=='parser' and change=='edit')
            repeat=m[key+'-noop']
            assert repeat['status']==0 and len(repeat['units'])==373 and all(v['fresh'] for v in repeat['units']) and not repeat['decoded']
            assert repeat['exe']==r['exe']
            assert r['cli']['doc']==orig['cli']['doc'] and not r['diagnostics']
            if step=='parser':
                cli=(m['extended-'+key] if arm=='parent' else r)['cli']
                for name,col in [('signed-pow',15),('signed-call',14)]:
                    status,stdout,stderr=cli[name];dx=json.loads(stdout)
                    if change=='edit':assert status==0 and dx==[]
                    else:assert status==1 and dx[0]['location']=={'row':2,'column':11} and dx[0]['end_location']=={'row':2,'column':col}
assert sha((p/'compiler.patch').read_bytes())=='ffc964f5118a2c7e7a69fbfe5a9ed05f69601fca9f85a5b0d1a3e163b0261c01'
if (p/'SHA256SUMS').exists():
    for line in (p/'SHA256SUMS').read_text().splitlines():
        h,fn=line.split('  ',1)
        assert sha((p/fn).read_bytes())==h,fn
print('PASS: 66 variant triples, 9 warm baseline crashes repaired, four fixed run-make tests, 2 differential Ruff edits and next fresh checks, independent matched/upstream scope controls')
