import gzip,json
from pathlib import Path
p=Path(__file__).resolve().parent
allr=json.loads(gzip.decompress((p/'raw.json.gz').read_bytes()));n=0;m=0
fixed='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322';matched='50ca47744e09d3ab9cfa320794c1a656935137abc3aaf22b7f74841f7c1be466'
assert set(allr)=={'fresh_cohorts','previous_wrong_state'}
for arm,suite in allr['fresh_cohorts'].items():
    who=suite['tools'];isfixed=arm!='matched-release-rust';assert who['cargo']==(fixed if isfixed else matched)
    assert who['rustc_driver']==('ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99' if arm=='fixed-optional-rust' else '52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955')
    assert len(suite['cases'])==8
    for label,case in suite['cases'].items():
        known=label.startswith('known-');dso=case['case']=='dso';r=case['rows'];assert len(r)==(7 if known else 4);n+=len(r)
        assert case['old']['inode']!=case['replacement']['inode'] and case['old_token_before_replacement']==17
        if dso:
            assert r['initial']['value']==17 and r['clean']['value']==29 and r['clean']['exit']==0
            assert case['sections']['.rustc'][0]==case['sections']['.rustc'][1] and case['sections']['.text'][0]!=case['sections']['.text'][1]
        else:assert case['rmeta_roots']['old']==case['rmeta_roots']['new'] and r['clean']['exit']==101 and r['clean']['diagnostics']==[{'code':'E0308','message':'mismatched types'}]
        assert r['initial']['exit']==0 and len(r['initial']['used_rustc_args'])==1
        for v in r.values():
            assert v['trace_sha256'] and len(v['stdout_sha256'])==len(v['stderr_sha256'])==64
        if isfixed:
            for k,v in r.items():
                assert len(v['used_rustc_args'])==1 and not v['used_rustc_args'][0]['binary_depinfo'] and not v['used_rustc_args'][0]['checksum_blake3']
                assert not v['claims'].get('complete',False)
            for k in ['repeat','again']:
                assert r[k]['exit']==r['clean']['exit'] and r[k]['value']==r['clean']['value'] and r[k]['diagnostics']==r['clean']['diagnostics']
        elif known:
            assert r['train-settled']['all_fresh'] and r['initial']['claims']['complete']
            for k in ['repeat','again']:
                assert r[k]['all_fresh'] and r[k]['unit_fresh'] and r[k]['exit']==0 and not r[k]['used_rustc_args']
                if dso:assert r[k]['value']==17
        else:
            for k in ['repeat','again']:assert r[k]['exit']==r['clean']['exit'] and r[k]['value']==r['clean']['value'] and r[k]['diagnostics']==r['clean']['diagnostics']
assert n==132
for label,v in allr['previous_wrong_state'].items():
    dso=label.startswith('dso-');r=v['rows'];assert v['private_tree_before_and_after']['files']>10 and len(v['genuine_wrong_proof_sha256'])==64
    assert set(r)=={'old-confirm','fixed-one','fixed-two','fixed-clean'};m+=len(r)
    assert v['base_subjects']['fixed']==fixed and r['old-confirm']['exit']==0 and r['old-confirm']['fresh'] and not r['old-confirm']['native']
    if dso:assert r['old-confirm']['value']==17
    for k in ['fixed-one','fixed-two','fixed-clean']:
        x=r[k];z=[i for i in x['native'] if i.get('rustc')=='hold_direct'];assert len(z)==1 and not z[0]['binary_dep_info'] and not z[0]['blake3']
        assert x['exit']==(0 if dso else 101) and x['value']==(29 if dso else None)
        assert x['diagnostics']==([] if dso else [{'code':'E0308','message':'mismatched types'}])
assert m==32
print(json.dumps({'isolated_native_commands':n,'actual_existing_cache_migration_commands':m,'independent_previous_wrong_states':8,'total':n+m,'fixed_stale_results':0,'timings':0},sort_keys=True))
