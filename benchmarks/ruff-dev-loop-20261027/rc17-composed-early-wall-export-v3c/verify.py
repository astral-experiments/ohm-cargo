"""Independently authenticate a terminal H5 v3c packet without using earlier clock files."""
import argparse, collections, gzip, json, re, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from export import BASE,H5,WALL,WALL_GIT,NATIVE,NATIVE_GIT,QA_GIT,QA_SHA,STOCK_GIT,STOCK_SRC,CONT_GIT,BOOT,canonical,dig,safe,file_sha
from bindings import bind_external,original_native,manifest,model

def loads(p):return json.loads(p.read_bytes())

def old_native(admission,n,r,prior):
    canon=Path(n['canonical'])
    m=admission['native'];assert m['subjects']==prior['subjects'] and m['roster']==prior['typed_roster']
    assert m['listing_sha256']==prior['listing_sha256'] and m['stats']==prior['counts']
    assert m['variants_sha256']==prior['variants_sha256']==r['native_variant_manifest_sha256']
    assert m['source_plan']==prior['native_protocol'] and m['registry_sha256']==prior['registry_sha256']
    observed=collections.defaultdict(set)
    for phase in ('selected-observer','repeat-observer','selected-composed','repeat-composed'):
        step=n['steps'][phase]
        for k,h in step['workspace'].items():observed[k].add(h)
        assert m['registry']=={str(canon/k):h for k,h in step['registry'].items()}
        for key,h in step['receipt_sha256'].items():
            if phase+'/'+key in m['files']:assert h==m['files'][phase+'/'+key]
    for k,t in r['targets'].items():
        if t['future_allowed']:observed[k].update(t['future_allowed'])
    assert m['allowed']=={str(canon/k):sorted(v) for k,v in observed.items()}
    assert len(m['allowed'])==110 and len(m['registry'])==78
    return m


def check_packet(packet,protocol,priors,public):
    manifest(protocol,WALL);sys.path.insert(0,str(protocol))
    import guards as g, catalog, native_registration as nr
    from runner import top_diagnostics
    from analysis import evaluate
    files=packet['files'];bodies=packet['bodies'];status=packet['status'];plan=g.P
    assert (packet['schema'],packet['host'],packet['wall_git'],packet['native_git'],packet['native_manifest'],packet['qa_git'])==(5,H5,WALL_GIT,NATIVE_GIT,NATIVE,QA_GIT)
    assert {v['sha256'] for v in files.values() if v['capture']=='verbatim'}==set(bodies)
    assert safe(canonical(packet)) is not None
    for k,f in files.items():
        assert not Path(k).is_absolute() and '..' not in Path(k).parts
        assert re.fullmatch('[0-9a-f]{64}',f['sha256']) and type(f['bytes']) is int and f['bytes']>=0
        assert f['capture'] in ('verbatim','private-text','digest-only')
        if 'public_traceback_lines' in f:
            assert f['capture']=='private-text' and (k.endswith('.err') or k.endswith('.failure') or k.endswith('/first-failure.txt'))
            size=0
            for line in f['public_traceback_lines']:
                if set(line)=={'text'}:
                    assert safe(line['text'].encode())==line['text'];size+=len(line['text'].encode())
                else:
                    assert set(line)=={'withheld_sha256','bytes'} and re.fullmatch('[a-f0-9]{64}',line['withheld_sha256']) and line['bytes']>0;size+=line['bytes']
            assert size==f['bytes']
        if f['capture']=='verbatim':
            data=bodies[f['sha256']].encode();assert len(data)==f['bytes'] and dig(data)==f['sha256']
    def sha(k):return files[k]['sha256']
    def raw(k):
        assert files[k]['capture']=='verbatim',(k,'required source was withheld')
        return bodies[sha(k)]
    def obj(k):return json.loads(raw(k))
    assert sha('protocol/SHA256SUMS')==WALL and raw('protocol/SHA256SUMS')==(protocol/'SHA256SUMS').read_text()
    for line in raw('protocol/SHA256SUMS').splitlines():
        h,name=line.split('  ',1);assert sha('protocol/'+name)==h
    assert obj('launcher/binding.json')=={'ref':WALL_GIT,'sha256':WALL}
    assert sha('launcher/job.py')==loads(HERE/'inputs.json')['job_manager_sha256']
    exits={x:int(raw('launcher/'+x+'.exit')) if 'launcher/'+x+'.exit' in files else None for x in ('admit','score','verify')}
    a,b,c=(exits[k] for k in ('admit','score','verify'))
    assert ((a==0 and b==0 and c==0 and status=='complete') or (a==0 and b==0 and c not in (None,0) and status=='verify-failed') or
            (a==0 and b not in (None,0) and c is None and status=='score-failed') or (a not in (None,0) and b is None and c is None and status=='admission-failed'))
    for stage,rc in exits.items():
        if rc is not None:assert all('launcher/'+stage+'.'+s in files for s in ('exit','out','err'))
    schedule=[(i,j,arm,f'{i:02d}-{j}-{arm}') for i,order in enumerate(plan['order'],1) for j,arm in enumerate(order,1)]
    byname=packet['slots'];attempted=[v for v in schedule if v[3] in byname]
    assert len(attempted)==len(byname) and attempted==schedule[:len(attempted)]
    private_text=[k for k,v in files.items() if v['capture']=='private-text']
    # Bind the separately published catalog input even if admission itself fails before signing a model.
    pub=obj('launcher/catalog-publication.json')
    hashes=public['catalog_hashes']
    assert pub==dict(plan_ref=WALL_GIT,plan_manifest=WALL,native_reference=NATIVE_GIT,catalog_protocol_ref=BOOT,
                     catalog_result_ref=public['catalog_ref'],independent_review='accepted',**hashes)
    assert sha('stock/wall-view.json')==hashes['view_sha256'] and sha('stock/terminal.json')==hashes['terminal_sha256']
    assert sha('stock/independent.json')==hashes['verifier_receipt_sha256'] and sha('stock/source/SHA256SUMS')==STOCK_SRC
    stock_reg=obj('stock/registration.json');assert stock_reg['protocol']==STOCK_SRC and stock_reg['commit']==STOCK_GIT
    from lineage import check_lineage
    public=public|{'lineage_model':check_lineage(packet,protocol,public,sha,raw,obj)}
    catalog.check_ci(plan,loads(protocol/'ci-exact-heads.json'));catalog.check_ci(plan,obj('launcher/ci.json'))
    assert 'protocol/ci-exact-heads.json' in files
    assert sha('qa.json')==QA_SHA
    qa=obj('qa.json');assert qa['status']=='pass' and qa['source']==plan['source']
    assert (qa['observer'],qa['composed'])==(plan['subject_images']['B'],plan['subject_images']['C'])
    for rec in [*qa['build'].values(),*qa['tests'].values()]:assert sha('qa/'+rec['evidence'])==rec['receipt_sha256']
    for key,want in [('v2/SHA256SUMS',plan['adopted_seed_v2']['manifest']),('v3/SHA256SUMS',plan['native_manifest'])]:
        assert sha(key)==want
    def failure(reason,clock_count=0):
        return dict(terminal=status,launcher=exits,qualified=False,statistics=None,observed_clocks=clock_count,reason=reason,
                    exceptions={k:sha(k) for k in ('admission.failure','result/first-failure.txt','launcher/admit.err','launcher/score.err','launcher/verify.err') if k in files},
                    commitment_only_text=private_text)
    if a!=0:
        assert 'admission.failure' in files and not attempted and not packet['result_directory_present'] and 'result/complete.json' not in files
        return failure('admission stopped before any scored state')
    assert public['published_proofs']=={k:sha('launcher/provenance/'+n) for k,n in [('witness','root-native-witness.json'),('proof','native-verifier.json'),('bootreg','bootstrap-registration.json'),('completion','bootstrap-completion.json'),('provenance','provenance.json')]}
    assert sha('admission.json')==public['admission_sha'] and sha('launcher/ci.json')==public['ci_sha']
    assert sha('launcher/catalog-publication.json')==public['catalog_publication_sha']
    assert raw('launcher/admit.out')=='zero-clock binding '+sha('admission.json')+'\n'
    adm=obj('admission.json');assert adm['worker_manifest']==WALL and adm['scored_commands']==0 and adm['qa_sha256']==QA_SHA and adm['ci_status']=='pass'
    assert adm['fs']=='ext4' and adm['copy']=='never' and adm['pessimistic_full_copy_bytes_all_48']==48*adm['seed']['unique_file_bytes']
    n,r,prior=priors;old=obj('native/frozen-native-guard.json');old_native({'native':old},n,r,prior)
    assert sha('native/variants.json')==old['variants_sha256'] and sha('native/frozen-native-guard.json')==prior['native_gate_sha256']
    m=model(plan,protocol,adm['native'],old,n,public,pub)
    grant=obj('launcher/grant.json');publication=obj('launcher/admission-publication.json')
    assert grant['published_native']==public['admission_ref'] and publication['admission_ref']==public['admission_ref']
    assert set(grant)=={'go','native_sha256','plan_manifest','published_plan','published_catalog','published_native','ci_sha256','h5_clear','other_host_measurement','ci_review'}
    from lineage import check_release
    check_release(obj('launcher/operator-release.json'),obj('launcher/ci.json'),plan,public,sha('admission.json'))
    nr.publication_grant(grant,publication,m,WALL,sha('admission.json'),plan['stopped_v2'])
    if packet['result_directory_present']:
        for key in ('grant.json','admission-publication.json'):
            if 'result/'+key in files:assert obj('result/'+key)==obj('launcher/'+key)
            else:assert status!='complete' and not attempted
    if status=='complete':
        assert len(attempted)==48 and not packet['projection_errors'] and all(name+'/verified.json' in files for _,_,_,name in attempted)
        assert raw('launcher/score.out')==''.join(f'{i}/24 guarded pairs\n' for i in range(1,25))
        assert all(sha('launcher/'+stage+'.err')==dig(b'') for stage in ('admit','score','verify'))
    elif status=='score-failed':
        assert 'result/first-failure.txt' in files or (not attempted and files['launcher/score.err']['bytes']>0)
    if status=='verify-failed':assert files['launcher/verify.err']['bytes']>0
    def role(arm):return plan['subjects'][arm]
    clocks=[];verified=[];partner={};pairs=[];last=0
    for i,j,arm,name in attempted:
        prefix=name+'/';o=prefix+'ordinary/';f=prefix+'unchanged/';slot=byname[name]
        strict=prefix+'verified.json' in files
        if not strict:
            assert status!='complete' and (i,j,arm,name)==attempted[-1]
            if o+'clock.json' in files:
                try:
                    ct=obj(o+'clock.json')
                    clocks.append([i,j,arm,ct.get('elapsed_ns'),ct.get('returncode')])
                except (TypeError, ValueError, AttributeError):
                    clocks.append([i,j,arm,None,None])
            continue
        if status=='complete':assert strict and not slot['retained_state']
        assert prefix+'start.json' in files and o+'clock.json' in files
        if prefix+'start.json' in files:
            st=obj(prefix+'start.json');assert (st['block'],st['slot'],st['arm'])==(i,j,arm)
            assert st['image']==m['subjects'][arm] and st['native_binding']==sha('admission.json')
            assert st['seed']==adm['seed']['digest'] and st['copy']==adm['copy'] and st['cpu']==plan['cpu']
            assert st['free']>plan['minimum_remaining_bytes']+plan['temporary_product_allowance'] and len(st['loadavg'])==3
        if o+'clock.json' in files:
            clk=obj(o+'clock.json');assert clk['argv']==plan['command'] and last<clk['start']<clk['stop']
            assert clk['stop']-clk['start']==clk['elapsed_ns'];last=clk['stop']
            clocks.append([i,j,arm,clk['elapsed_ns'],clk['returncode']])
        v=obj(prefix+'verified.json');assert (v['block'],v['slot'],v['arm'])==(i,j,arm) and v['image']==m['subjects'][arm]
        assert o+'clock.json' in files and clk['elapsed_ns']==v['elapsed_ns'] and clk['returncode']==0
        assert sha(o+'stdout')==v['stdout']==dig(b'') and sha(o+'stderr')==v['stderr']
        assert raw(o+'stdout')=='' and 'Finished' in raw(o+'stderr') and 'Blocking waiting' not in raw(o+'stderr')
        assert sha(o+'e2e-list')==sha(f+'e2e-list')==m['listing_sha256']==v['e2e_list']
        assert sha(o+'e2e-list.stderr')==dig(b'')
        a1=obj(prefix+'first-110.json');a2=obj(f+'products.json')
        assert sha(prefix+'first-110.json')==v['first_110'] and g.digest(a2['native'])==v['follow_110']
        for data in (a1,a2['native']):g.check_raw(data,m['allowed'])
        assert obj(prefix+'first-78-registry.json')==obj(f+'registry-native.json')==m['registry'] and sha(prefix+'first-78-registry.json')==v['registry_78']
        assert g.digest(m['registry'])==m['registry_sha256'] and g.summary(a2)==m['roster']==v['follow_roster']
        assert v['follow_counts']==a2['counts']==m['stats']['repeat-'+role(arm)] and v['follow_fresh']==a2['fresh']==n['steps']['repeat-'+role(arm)]['fresh']
        assert a2['units']==619 and len(a2['exes'])==102 and a2['ty_server']==m['typed_seed_rlib'] and len(a2['e2e'])==1 and sorted(g.digest(x[1]) for x in a2['diagnostics'])==sorted(x[3] for x in n['steps']['repeat-'+role(arm)]['diagnostics'])
        assert top_diagnostics(raw(o+'stderr'),a2)==v['diagnostics']
        events=slot['events'];reference=n['steps']['repeat-'+role(arm)];rows=events['rows']
        assert set(rows)==set(reference['rows'])
        assert collections.Counter(item[3] for item in rows.values() if item[1] and item[2])=={True:84,False:18}
        assert not events['invalid'] and events['last']=='build-finished' and events['other'][-1]['success'] is True
        assert set(rows)==set(reference['rows']) and len(rows)==619 and sum(x[0] for x in rows.values())==a2['fresh']
        assert set(a2['exes'])=={item[2] for item in rows.values() if item[1] and item[2]}
        for key,item in rows.items():
            prev=reference['rows'][key]
            assert item[1:]==[prev['owner']=='workspace',str(Path(n['canonical'])/prev['executable']) if prev['executable'] else None,prev['test']]
        assert sorted(x['diagnostic'] for x in events['other'] if x['diagnostic'])==sorted(g.digest(x[1]) for x in a2['diagnostics'])
        jobs=slot['jobs'];h=g.digest(sorted(g.row_roster(jobs).items()))
        assert h==m['repeat_roster'] and len({row['pid'] for row in jobs})==len(jobs)
        assert dict(collections.Counter(row['kind'] for row in jobs))==v['follow_counts']
        for proc in jobs:
            assert f+'trace/'+proc['pid'] in files and sha(f+'trace/'+proc['pid'])==proc['trace_sha256'] and all(re.fullmatch('[a-f0-9]{64}',proc[k]) for k in ('raw','argv_sha256','exe_sha256'))
        assert obj(f+'command.json')==dict(arm=role(arm),binary=m['subjects'][arm],code=0,edited=True,traced=True,command=plan['command']+['--message-format=json'])
        verified.append(name);partner[arm]=(a1,clk['elapsed_ns'])
        if j==2:
            bc,cc=partner['B'][0],partner['C'][0];diff={k:[v,cc[k]] for k,v in bc.items() if v!=cc[k]}
            pairs.append(dict(block=i,order=plan['order'][i-1],ns={s:partner[s][1] for s in 'BC'},matching_raw=110-len(diff),raw_differences=diff));partner={}
    checkpoint=obj('result/pairs.json') if 'result/pairs.json' in files else []
    assert checkpoint==pairs[:len(checkpoint)] and (len(checkpoint)==len(pairs) if status=='complete' else len(pairs)-len(checkpoint) in (0,1))
    scores=None
    if status=='complete':
        z=obj('result/complete.json');assert z['pairs']==24 and z['slots']==48 and z['plan']==WALL and z['admission']==sha('admission.json')
        assert z['analysis']==sha('result/result.json') and z['rows']==sha('result/pairs.json')
        assert len(pairs)==24 and len(verified)==48 and 'result/first-failure.txt' not in files
        scores=evaluate(plan,pairs);original=json.loads(raw('launcher/verify.out'))
        assert scores==original['statistics']==obj('result/result.json')
        exact=sum(row['matching_raw'] for row in pairs)
        assert original==dict(verified_pairs=24,verified_clocks=48,only_timed_endpoint='first-selection',
                              raw_crossarm_comparisons=2640,raw_exact=exact,raw_qualified_variants=2640-exact,
                              verified_listings=96,test_bodies_timed=0,statistics=scores)
    # Preserve the exact rejected digest in a failed slot. The accepted product set never expands.
    failed_maps={}
    for i,j,arm,name in attempted:
        if status=='complete' or name in verified:
            continue
        entry={}
        def summarize(observed,admitted):
            return {'reported':len(observed),'missing':sorted(set(admitted)-set(observed)),
                    'unexpected':sorted(set(observed)-set(admitted)),
                    'unadmitted':{k:h for k,h in observed.items() if k in admitted and h not in admitted[k]}}
        registry={k:[h] for k,h in m['registry'].items()}
        for label,path,field,allowed in (
                ('first_workspace','first-110.json',None,m['allowed']),
                ('first_registry','first-78-registry.json',None,registry),
                ('follow_workspace','unchanged/products.json','native',m['allowed']),
                ('follow_registry','unchanged/registry-native.json',None,registry)):
            full=name+'/'+path
            if full not in files:continue
            try:
                body=obj(full);data=body if field is None else body[field];entry[label]=summarize(data,allowed)
            except (AssertionError,AttributeError,TypeError,KeyError,ValueError):
                entry[label]={'undecoded_source_sha256':sha(full)}
        final=byname[name].get('terminal_retained_outputs')
        if final is not None:
            final={str(Path(n['canonical'])/k):v for k,v in final.items()}
            assert set(final)==set(m['allowed'])|set(m['registry'])
            entry['terminal_snapshot']=summarize({k:v['sha256'] for k,v in final.items() if v is not None},m['allowed']|registry)
        failed_maps[name]=entry
    return {'terminal':status,'launcher':exits,'observed_clocks':len(clocks),'verified_slots':len(verified),
            'complete_pair_checkpoints':len(checkpoint),'failed_slot_products':failed_maps,'retained_private_states':[k for k,v in byname.items() if v['retained_state']],
            'raw_clock_records':len(clocks),'exceptions':{k:sha(k) for k in files if k in ('result/first-failure.txt','admission.failure','launcher/score.err','launcher/verify.err')},
            'qualified':scores['qualifies'] if scores else False,'statistics':scores,'commitment_only_text':private_text}


def terminal_report(packet,protocol,priors,public):
    # Never turn a nonzero physical terminal exit into an estimate, even when the independent
    # reader itself encounters malformed evidence that was recorded by that failed experiment.
    if packet['status']=='complete':return check_packet(packet,protocol,priors,public)
    try:return check_packet(packet,protocol,priors,public)
    except (KeyError,ValueError,AssertionError,TypeError,IndexError) as err:
        files=packet['files']
        assert safe(canonical(packet)) is not None
        for key in ('admit','score','verify'):
            rc='launcher/'+key+'.exit'
            if rc in files:
                value=files[rc];s=packet['bodies'][value['sha256']];assert dig(s.encode())==value['sha256']
        proof={k:v['sha256'] for k,v in files.items() if k in ('result/first-failure.txt','admission.failure') or k.startswith('launcher/') and k.endswith(('.err','.exit'))}
        assert any(packet['bodies'].get(files[k]['sha256'],'0')!='0' for k in proof if k.endswith('.exit'))
        return {'terminal':packet['status'],'qualified':False,'statistics':None,'independent_evidence_valid':False,
                'observed_clocks':sum(k.endswith('/ordinary/clock.json') for k in files),'first_failure_and_exits':proof,
                'reader_error_type':type(err).__name__,'reader_error_sha256':dig(str(err).encode())}

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for arg in ('packet','wall_plan','original_native','published_pins','stock_results'):cli.add_argument(arg,type=Path)
    cli.add_argument('--admission-results',type=Path);cli.add_argument('--h2-results',type=Path)
    arg=cli.parse_args();packet=json.loads(gzip.decompress(arg.packet.read_bytes()))
    public=bind_external(loads(arg.published_pins),arg.stock_results,arg.admission_results,arg.h2_results)
    print(json.dumps(terminal_report(packet,arg.wall_plan,original_native(arg.original_native),public),indent=2,sort_keys=True))
