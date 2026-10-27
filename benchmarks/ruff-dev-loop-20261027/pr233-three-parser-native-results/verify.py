"""Verify the completed export's byte manifest, schedules, physical job counts, CLI observations and immediate freshness."""
from pathlib import Path
import collections, hashlib, json, sys
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def h(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
seen=set()
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,rel=line.split('  ',1);p=(root/rel).resolve()
    assert root in p.parents and p.is_file() and rel not in seen and h(p)==digest,(rel,'manifest')
    seen.add(rel)
assert seen=={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS'},'file inventory'
plan=read(root/'preregistered-plan.json');assert h(root/'preregistered-plan.json')=='a55a3d97d1f4880a3c516b930b77ca49e337927a1404a4e0dafa23222244d7e4'
pre,done,gate=map(read,(root/'preflight.json',root/'complete.json',root/'test-admission.json'))
assert done['source_index_unchanged']==pre['source_index'] and done['test_admitted']==gate['run_independent_test_arms']==(gate['free_bytes']>=60*2**30)
assert pre['build_entry_free']>=40*2**30 and done['free_bytes']>=25*2**30
ncmd=nchanged=nrestored=nbridge=0
for mode in (['build','test'] if done['test_admitted'] else ['build']):
    units,nelf,nexec=(501,15,6) if mode=='build' else (619,110,102)
    summary=read(root/(mode+'-observations.json'))
    for arm in 'BC':
        d=root/'commands'/mode/arm;rows={q.stem:read(q) for q in d.glob('*.json')};ncmd+=len(rows)
        cold=rows['cold'];assert cold['dirty_targets'] and cold['fresh_units']==0
        for r in rows.values():
            assert r['arm']==arm and r['mode']==mode and r['status']==0 and (r['unit_count'],r['elf_count'],r['executable_count'])==(units,nelf,nexec)
            jobs=r['physical_jobs'];assert dict(collections.Counter(j['kind'] for j in jobs))==r['process_totals']
            assert {n:len(v) for n,v in r['native_process_files'].items()}==r['native_totals']
            assert units-len(r['dirty_targets'])==r['fresh_units']
            traces=r['native_process_trace_sha256']
            for j in jobs:
                assert [j['crate'],j['kind']] in traces[j['file']]['roles'] and len(traces[j['file']]['process_trace_sha256'])==64
                assert j['kind'] in ('full','link-only')
                if j['kind'].startswith('checked-'):
                    b=[(p,z) for p,z in r['recipe_after'].items() if Path(p).name==j['recipe_basename']]
                    assert len(b)==1;path,now=b[0]
                    before=r['recipe_before'].get(path)
                    assert (before is not None and before[:2]==now[:2])==(j['kind']=='checked-native')
            for who,files in r['native_process_files'].items():
                for f in files:assert [who] in traces[f]['roles']
            actual=r['novel_cli'];spec=plan['cli']
            assert len(actual)==3 and not any(x['stderr'] for x in actual)
            for idx,row in enumerate(actual):
                if idx==2 or r['source_view']=='signed-pattern-diagnostic':assert (row['status'],row['diagnostics'])==(0,[])
                else:
                    assert row['status']==1 and len(row['diagnostics'])==1
                    msg=row['diagnostics'][0];e=spec['original_signed']
                    assert (msg['code'],msg['message'],msg['location'],msg['end_location'])==(e['code'],e['message'],{'row':2,'column':11},{'row':2,'column':e['end_columns'][idx]})
            if r['phase'] in ('baseline','fresh'):assert r['fresh_units']==units and not jobs and not any(r['native_totals'].values())
        for case in plan['schedule']:
            for direction in ('edit','restore'):
                name=case+'-'+direction;r=rows[name];after=rows[name+'-fresh']
                assert r['source_view']==(case if direction=='edit' else 'original')
                assert r['physical_jobs'] and any(j['crate']=='ruff_python_parser' and j['kind']=='full' for j in r['physical_jobs'])
                assert {p:data['raw'] for p,data in r['workspace_elf_sha256'].items()}==after['workspace_elf_sha256']
                assert r['novel_cli']==after['novel_cli'] and len(after['workspace_elf_sha256'])==nelf and summary['first_occurrences'][name][arm]['process_totals']==r['process_totals']
                if direction=='edit': nchanged+=1
                else:nrestored+=1
        assert not [a for a in rows if 'condition' in a or 't-string' in a]
    for case in plan['schedule']:
        label=case+'-edit'
        arr=read(root/'bridges'/mode/label/'summary.json')
        assert arr==summary['ordinary_callers'][label]
        assert len(arr)==8 and all(r['exit']==0 for r in arr)
        assert {(r['crate'], r['bridge_from'], r['current_arm']) for r in arr if r['kind']=='caller'}=={(c,a,a) for c in ('ruff_wasm','ty_wasm') for a in 'BC'}
        nbridge+=sum(r['kind']=='caller' for r in arr)
print(f'{ncmd} complete workspace invocations, {nchanged} first edited arm observations, {nrestored} restorations, {nbridge} newly compiled ordinary caller observations and all immediate zero-job checks verified.')

for mode in ('build','test'):
    ob=read(root/(mode+'-observations.json'))
    for name,check in ob['cross_arm'].items():
        both=[read(root/'commands'/mode/a/(name+'.json')) for a in 'BC']
        assert check['same_unit_paths_across_registered_namespaces'] and all(check[k] for k in ('same_compiler_messages','same_old_cli','same_novel_cli'))
        assert check['release_output_rosters']==[q['release_output_roster'] for q in both] and both[0]['release_output_roster']==both[1]['release_output_roster']
        assert both[0]['release_output_roster']['units']==both[0]['unit_count']
    assert all(row['same_unit_paths'] for pair in ob['original_vs_own_restores'].values() for row in pair.values())
linked=read(root/'linked-products.json')
for mode,arms in linked.items():
    for arm,source in arms.items():
        previous='original-baseline'
        for edit in plan['schedule']:
            for direction in ('edit','restore'):
                name=edit+'-'+direction; z=source[name]; cmd=root/'commands'/mode/arm
                old,new=map(read,(cmd/(previous+'.json'),cmd/(name+'.json')))
                assert z['previous_receipt_sha256']==old['complete_private_receipt_sha256'] and z['current_receipt_sha256']==new['complete_private_receipt_sha256']
                assert sorted(j['process'] for j in z['jobs'])==sorted(j['file'] for j in new['physical_jobs'])
                assert sorted(w['process'] for w in z['links'])==sorted(new['native_process_files']['wild'])
                assert len({w['product'] for w in z['links']})==len(z['links'])
                for event in [*z['jobs'],*z['links']]:
                    assert event['trace_sha256']==new['native_process_trace_sha256'][event['process']]['process_trace_sha256']
                for w in z['links']:
                    lo,hi=[r['workspace_elf_sha256'][w['product']] for r in (old,new)]
                    assert [lo['raw'],hi['raw']]==w['raw'] and [lo['content_with_two_wild_fields_masked'],hi['content_with_two_wild_fields_masked']]==w['masked']
                    for field,key in (('text_bytes','.text'),('rodata_bytes','.rodata')):
                        a,b=w[field];assert (a!=b)==('bytes' in w['section_fields_changed'].get(key,[]))
                    assert w['raw'][0]!=w['raw'][1] or not w['section_fields_changed']
                for job in z['jobs']:
                    assert ('ruff_python_parser' in job['extern_crates'])==job['parser_direct']
                previous=name
print('Every edited and restored native job and linked ELF was matched to the command and previous source state.')
