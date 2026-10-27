"""Reconstruct eligible historical Rust processes, negative controls and the actually shipped check."""
import collections as c, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parent
def read(n):return json.loads((root/n).read_text())
def check():
    o=read('official16.json')
    assert o['cargo']=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
    assert o['driver']=='c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4'
    stock=read('shipped-workspace-check.json')
    for side in stock.values():
        assert side['change']['fresh']==511 and side['preflight']['fresh']==520
        assert side['change']['processes']=={'cc':3,'collect2':3,'rustc-full':8,'wild':3}
        assert sorted(side['change']['scripts'])==['ruff','ty','ty_wasm']
        assert sorted(side['change']['rustcs'])==sorted(['build_script_build']*3+['ruff']*2+['ty']*2+['ty_wasm'])
        for step in ('change-next','change-next-2'):
            assert side[step]['fresh']==514 and side[step]['rustcs']==['ruff','ty','ty_wasm']
    graph=read('unit-graph.json')
    result={}
    for m,expected,n in [('check',5,571),('build',6,552),('test',20,689)]:
        g=graph[m]; assert g['num_units']==n
        h=read(m+'-selection-historical.json');scripts=[i for i in h if i['crate']=='build_script_build']
        assert {i['src'] for i in scripts}=={'crates/ruff/build.rs','crates/ty/build.rs','crates/ty_wasm/build.rs'} and len(scripts)==3
        consumers=[]
        for r in h:
            if r in scripts:continue
            mode='check' if m=='check' else ('test' if m=='test'and r['types'] is None else 'build')
            candidates=[z for z in g['rows'] if z['mode']==mode and z['crate'].replace('-','_')==r['crate'] and (not r['src'] or z['source']==r['src'])]
            assert len(candidates)==1,(m,mode,r['crate'],r['src'])
            z,=candidates
            assert any(chain[-1]=='ruff_macros' for chain in z['local_macro_chains'])
            assert len(r['passed_native'])>=2
            consumers.append({'crate':r['crate'],'source':z['source'],'mode':mode,'compiler_kind':r['kind'],'shortest_local_macro_chain':z['local_macro_chains'][0],'native_search_path_count':len(r['passed_native'])})
        assert len(consumers)==expected
        result[m]={'historical_consumers':consumers,'without_workspace_macro_in_graph':sum(not r['shortest_local_macro_chain'] for r in consumers)}
    originals=read('stock-controls.json')
    stages={'prime','warm-original','edit','warm-edited','empty-edited','restore'}
    assert set(originals)=={'environment','generator','outside-include','outside-proc','outside-archive','library-order','watch-only'}
    pkg=read('pkg-config.json')
    assert set(pkg)=={'library-order'}
    for name,rec in list(originals.items())+[('real-pkg-config-order',pkg['library-order'])]:
        assert set(rec)==stages
        for stage,r in rec.items():
            expected='41' if name=='watch-only' or stage in ['prime','warm-original','restore']else '83'
            assert r['stdout']==r['expected']==expected and r['correct']
            if stage=='edit':
                assert r['consumer_compilers']==r['native_linkers']==1
            if name=='real-pkg-config-order':
                assert r['pkg_config_executions']==(0 if stage in ['warm-original','warm-edited']else 1)
                order=[t.split('=')[-1]for t in r['stdout_of_script']if 'rustc-link-lib' in t]
                assert order==(['first','second'] if expected=='41' else ['second','first'])
    a=read('witness.json');assert set(a)=={'negative-module-check','negative-module-build','inherited-static-build'}
    for k,r in a.items():
        assert set(r)=={'prime','no-op','edit','empty-edit','restore'}
        for v in r.values():
            assert not v['out_files']and all(not vals for vals in v['script'].values())
            assert v['existing_rust_source']==r['prime']['existing_rust_source']
            assert all(j['compiler_bytes']==o['frontend'] for j in v['jobs'] if j['role']=='rustc')
        deps=r['prime']['deps'];assert deps and all(z['has_expected_main'] and not z['mentions_alternate'] and not z['mentions_archive']for z in deps)
        assert r['prime']['exit']==r['restore']['exit']==0
        if k.startswith('negative-module'):
            assert all(z['has_expected_item'] for z in deps)
            for stage in ['edit','empty-edit']:
                assert r[stage]['exit']==101 and 'E0761' in {msg['code'] for msg in r[stage]['diagnostics']}
                assert r[stage]['present_alternate']
            assert not r['restore']['present_alternate']
        else:
            for stage in ['prime','edit','empty-edit','restore']:
                row=r[stage];want='83' if stage in ['edit','empty-edit']else '41'
                assert row['exit']==0 and row['runtime']==want and row['native']['contains_native_object']
                assert row['native']['archive']==('3b9ebaee2556c513d940c36b458877129397577172225359bff5137139dfae0c' if want=='83' else '5a2a5e60bb45e00ba73db928846dbfaaace1ea3d41b4ba0317fc9f32d1a84441')
                selected=[j for j in row['jobs']if j['role']=='rustc' and j['crate']=='probe_bundle']
                assert len(selected)==1 and selected[0]['native_paths'] and not selected[0]['native_flags'] and not selected[0]['direct_proc_macros']
    return result
if __name__=='__main__':
    result=check()
    assert read('eligibility.json')==result
    for m,r in result.items():print(m,len(r['historical_consumers']),r['without_workspace_macro_in_graph'])
    print('Verified the 42 original, six pkg-config and fifteen missing-input commands.')
