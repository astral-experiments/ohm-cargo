"""Verify each phase of 240 real Cargo runs, including clean outcomes and unchanged admission behavior."""
from pathlib import Path
import collections,gzip,hashlib,json,tarfile
p=Path(__file__).resolve().parent
fixtures=['binary-identity','native-dso','trained-dso','column-rmeta','trained-rmeta'];counts={};cohorts=[]
expected_tools={'candidate':('d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde','ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99'),'explicit-probe':('03c851e44a863bb0d2cb8c9a98df1eef33310c8f3fbc77cdbb48aee516e68400','ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99'),'released-sources':('0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2','52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'),'old-cargo-new-rust':('0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2','ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99')}
for form in fixtures:
    packet=json.loads(gzip.decompress((p/(form+'.json.gz')).read_bytes()));assert packet['variant']==form
    assert set(packet['arm_results'])==set(expected_tools);n=0
    for arm,record in packet['arm_results'].items():
        tool=record['tool_identites'];assert (tool['cargo'],tool['driver'])==expected_tools[arm] and tool['frontend']=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
        for label,case in record['cases'].items():
            r=case['phases'];n+=len(r);kind=case['case'];shared=kind=='dso';trained=form.startswith('trained-')
            sequence=['initial','repeat','again','clean'];entered=sequence[0]
            rg=['train-cold','train-first','train-settled'] if trained else []
            assert set(r)==set(rg+sequence)
            assert case['old_token_before_replacement']==17 and case['old']['inode']!=case['replacement']['inode']
            assert case['old']['sha256']!=case['replacement']['sha256'] and len(set(case['input_blake3']))==2
            assert case['replacement']['mtime_ns']==case['old']['mtime_ns'] if case['timestamp']=='preserved' else case['replacement']['mtime_ns']>case['old']['mtime_ns']
            for ph,v in r.items():
                assert v['counts']==dict(collections.Counter(x['process'] for x in v['native']))
                assert v['exec_file_sha256'] and all(len(h)==64 for h in v['exec_file_sha256'].values())
                if v['selected_fresh']:assert not any(x.get('crate')=='hold_direct' for x in v['native'])
                f=v['claims']
                if f.get('extern_checksums'):
                    row,=f['extern_checksums'];i=['old','replacement'].index(f['authenticated_input']);assert row[1]=='checksum:blake3='+case['input_blake3'][i] and row[2]=='file_len:'+str(case[['old','replacement'][i]]['bytes'])
            if shared:
                assert r['clean']['value']==29 and all(d['exe']=='rustc' and 'r-xp' in d['permissions'] for d in case['observed_old_maps']) and case['observed_old_maps']
            else:
                assert r['clean']['exit']==101 and r['clean']['diagnostics']==[{'code':'E0308','message':'mismatched types'}]
            if form=='binary-identity':
                assert r['initial']['exit']==101 and 'colliding StableCrateId values' in r['initial']['diagnostics'][0]['message']
                assert all((r[j]['value']==29 if shared else r[j]['diagnostics']==r['clean']['diagnostics']) for j in ['repeat','again'])
                continue
            assert r['initial']['exit']==0 and r['initial']['selected_fresh'] is False
            if shared:
                for name,v in case['sections'].items():assert (v[0]==v[1])==(name!='.text')
                assert set(case['sections'])=={'.rustc','.text','.dynsym'} and case['compiled']['17']['source']==case['compiled']['29']['source']
                assert case['old']['bytes']==case['replacement']['bytes'] and r['initial']['value']==17
            else:
                assert case['rmeta_roots']['old']==case['rmeta_roots']['new'] and set(case['rmeta_roots']['old'])=={'stable_id','svh','public_hash'}
            if trained:
                assert all(r[x]['exit']==0 for x in rg)
                assert (r['train-settled']['all_fresh'],r['train-settled']['claims']['complete'],r['train-settled']['native'])==(True,True,[])
            stale=trained or arm in ('candidate','explicit-probe')
            if stale:
                assert r['initial']['claims']['complete'] and r['initial']['claims']['authenticated_input']=='replacement'
                for x in ('repeat','again'):
                    assert r[x]['all_fresh'] and r[x]['selected_fresh'] and not r[x]['native'] and r[x]['exit']==0
                    if shared:assert r[x]['value']==17
            else:
                assert r['initial']['claims']['complete'] is False and any(x.get('crate')=='hold_direct' for x in r['repeat']['native'])
                for x in ('repeat','again'):
                    if shared:assert r[x]['value']==29
                    else:assert r[x]['exit']==101 and r[x]['diagnostics']==r['clean']['diagnostics']
            cohorts.append([form,arm,label,stale])
    assert n==packet['physical_cargo_commands'];counts[form]=n
assert counts=={'binary-identity':64,'native-dso':32,'trained-dso':56,'column-rmeta':32,'trained-rmeta':56}
print(json.dumps({'cargo_commands':sum(counts.values()),'by_cohort':counts,'wrong_fresh_case_histories':sum(r[-1] for r in cohorts),'admission':False,'timings':0},sort_keys=True))
