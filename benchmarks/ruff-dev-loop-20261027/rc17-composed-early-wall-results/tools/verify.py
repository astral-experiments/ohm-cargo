"""Verify a complete or failed exported wall trial without exposing private Cargo paths."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from export import NATIVE, NATIVE_GIT, WALL, WALL_GIT, QA_GIT, QA_SHA, ADMISSION_GIT, ADMISSION_SHA, V1_GIT, V1_WALL, V1_FAILURE, canonical, dig


def load_json(path):
    return json.loads(path.read_bytes())


def manifest(path,expected):
    assert dig((path/'SHA256SUMS').read_bytes())==expected,(path,expected)
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=path,check=True)


def prior_native(path):
    manifest(path,NATIVE)
    n=json.loads(gzip.decompress((path/'native.json.gz').read_bytes()))
    r=json.loads(gzip.decompress((path/'replay.json.gz').read_bytes()))
    g=load_json(path/'h5-frozen-native-guard.json')
    return n,r,g


def bind_published_admission(packet):
    assert packet['admission_git']==ADMISSION_GIT
    if packet['status']=='admission-failed':
        return
    assert packet['files']['admission.json']['sha256']==ADMISSION_SHA
    for name in ('result/grant.json','launcher/grant.json'):
        if name in packet['files']:
            raw=packet['bodies'][packet['files'][name]['sha256']]
            grant=json.loads(raw)
            assert grant['native_sha256']==ADMISSION_SHA and grant['published_native']==ADMISSION_GIT


def native_check(admission,n,r,prior):
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


def check_packet(packet,protocol,priors):
    from export import safe
    manifest(protocol,WALL)
    sys.path.insert(0,str(protocol))
    import guards as g
    from runner import top_diagnostics
    from analysis import evaluate
    files=packet['files'];bodies=packet['bodies'];status=packet['status']
    assert (packet['schema'],packet['wall_git'],packet['native_git'],packet['native_manifest'])==(2,WALL_GIT,NATIVE_GIT,NATIVE)
    assert {v['sha256'] for v in files.values() if v['capture']=='verbatim'}==set(bodies)
    assert safe(canonical(packet)) is not None
    for k,f in files.items():
        assert not Path(k).is_absolute() and '..' not in Path(k).parts
        assert re.fullmatch('[0-9a-f]{64}',f['sha256']) and f['bytes']>=0
        assert f['capture'] in ('verbatim','private-text','digest-only')
        if f['capture']=='verbatim':
            raw=bodies[f['sha256']].encode();assert len(raw)==f['bytes'] and dig(raw)==f['sha256']
    def sha(k):return files[k]['sha256']
    def raw(k):
        assert files[k]['capture']=='verbatim',(k,'requires local review before using this text')
        return bodies[sha(k)]
    def obj(k):return json.loads(raw(k))
    assert packet['qa_git']==QA_GIT and packet['first_wall_git']==V1_GIT
    assert sha('v1/SHA256SUMS')==V1_WALL and obj('v1/binding.json')=={'ref':V1_GIT,'sha256':V1_WALL}
    assert raw('v1/admit.exit')=='1' and sha('v1/admission.failure')==V1_FAILURE and 'AssertionError: ext4' in raw('v1/admission.failure')
    assert sha('qa.json')==QA_SHA
    old=obj('protocol/wall-v1-failure-receipt.json');assert old['qa']==QA_SHA and old['clocks']==0 and not old['result_exists']
    for source,key in (('early-scheduler-wall-admission-v1.failure','v1/admission.failure'),('binding.json','v1/binding.json'),('admit.stdout','v1/admit.stdout'),('admit.stderr','v1/admit.stderr'),('admit.exit','v1/admit.exit')):
        assert sha(key)==old['remote'][source]
    storage=obj('protocol/wall-storage-preflight.json');rules=g.P['storage_after_unscored_v1']
    assert sha('protocol/wall-storage-preflight.json')==rules['preflight']
    assert storage['ficlone_errno']==rules['errno']==95 and not storage['ficlone_supported']
    assert storage['full_copy_isolated'] and storage['same_device'] and not storage['result_root_exists'] and storage['scored_commands']==0
    assert storage['first_failure']==rules['first_failure']==V1_FAILURE and storage['host_fs']==rules['filesystem']=='ext4'
    assert set(storage['filesystems'].values())=={'ext4'} and storage['file_bytes']==2**20
    assert sha('protocol/SHA256SUMS')==WALL
    for line in raw('protocol/SHA256SUMS').splitlines():
        h,name=line.split();assert sha('protocol/'+name)==h
    assert obj('launcher/binding.json')=={'ref':WALL_GIT,'sha256':WALL}
    exits={j:int(raw('launcher/'+j+'.exit')) if 'launcher/'+j+'.exit' in files else None for j in ('admit','score','verify')}
    a,b,c=(exits[s] for s in ('admit','score','verify'))
    assert ((a==0 and b==0 and c==0 and status=='complete') or
            (a==0 and b==0 and c not in (None,0) and status=='verify-failed') or
            (a==0 and b not in (None,0) and c is None and status=='score-failed') or
            (a not in (None,0) and b is None and c is None and status=='admission-failed')),exits
    for stage,ret in exits.items():
        if ret is not None:assert all('launcher/'+stage+'.'+suffix in files for suffix in ('exit','stdout','stderr'))
    plan=g.P;schedule=[(i,j,arm,f'{i:02d}-{j}-{arm}') for i,order in enumerate(plan['order'],1) for j,arm in enumerate(order,1)]
    byname=packet['slots'];attempted=[t for t in schedule if t[3] in byname]
    assert len(attempted)==len(byname) and attempted==schedule[:len(attempted)]
    private_text=[k for k,v in files.items() if v['capture']=='private-text']
    qa=obj('qa.json');assert qa['source']==plan['source'] and qa['status']=='pass'
    assert (qa['observer'],qa['composed'])==(plan['subject_images']['B'],plan['subject_images']['C'])
    assert set(qa['tests'])=={'built-library','unused','used','missing-proof','observer-replacement','ordinary-reader','cached-state-migration'}
    assert set(qa['build'])=={'observer','composed'}
    for k,v in qa['tests'].items():assert v['exit']==0 and v['subject'] in (qa['observer'],qa['composed'])
    for role,record in qa['build'].items():
        assert record['cargo_sha256']==qa[role] and all(re.fullmatch('[a-f0-9]{64}',record[k]) for k in ('recipe_sha256','profiles_sha256','source_recipe_sha256'))
    assert all(qa['build']['observer'][k]==qa['build']['composed'][k] for k in ('recipe_sha256','profiles_sha256'))
    for group in ('tests','build'):
        for v in qa[group].values():assert sha('qa/'+v['evidence'])==v['receipt_sha256']
    n,r,prior=priors
    assert sha('native/variants.json')==prior['variants_sha256'] and sha('native/frozen-native-guard.json')==prior['native_gate_sha256']
    for k,want in [('v2/SHA256SUMS',plan['adopted_seed_v2']['manifest']),('v3/SHA256SUMS',plan['native_manifest'])]:assert sha(k)==want
    if a!=0:
        assert not attempted and not packet['result_directory_present'] and 'result/complete.json' not in files
        return {'terminal':status,'launcher':exits,'qualified':False,'observed_clocks':0,'statistics':None,'qa_sha256':sha('qa.json'),'native_gate_sha256':sha('native/frozen-native-guard.json'),
                'exceptions':{k:sha(k) for k in files if k in ('admission.failure','launcher/admit.stderr')},'commitment_only_text':private_text}
    adm=obj('admission.json');assert adm['worker_manifest']==WALL and adm['scored_commands']==0
    assert adm['qa_sha256']==sha('qa.json') and adm['ci_status']=='pass'
    assert adm['fs']=='ext4' and adm['copy']=='never' and adm['pessimistic_full_copy_bytes_all_48']==48*adm['seed']['unique_file_bytes']
    m=native_check(adm,n,r,prior)
    assert obj('native/frozen-native-guard.json')==m
    if 'launcher/grant.json' in files:
        grant=obj('launcher/grant.json')
        assert grant['native_sha256']==sha('admission.json') and grant['plan_manifest']==WALL and grant['published_plan']==WALL_GIT
        assert re.fullmatch('[0-9a-f]{40}',grant['published_native']) and grant['h5_clear'] and not grant['other_host_measurement'] and grant['ci_review']=='accepted'
        if 'result/grant.json' in files:assert obj('result/grant.json')==grant
    if status=='complete':assert 'result/grant.json' in files and len(attempted)==48 and not packet['projection_errors']
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
        if prefix+'start.json' in files:
            st=obj(prefix+'start.json');assert (st['block'],st['slot'],st['arm'])==(i,j,arm)
            assert st['image']==m['subjects'][arm] and st['native_binding']==sha('admission.json')
            assert st['seed']==adm['seed']['digest'] and st['copy']==adm['copy'] and st['cpu']==plan['cpu']
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
        assert a2['units']==619 and len(a2['exes'])==102 and sorted(g.digest(x[1]) for x in a2['diagnostics'])==sorted(x[3] for x in n['steps']['repeat-'+role(arm)]['diagnostics'])
        assert top_diagnostics(raw(o+'stderr'),a2)==v['diagnostics']
        events=slot['events'];reference=n['steps']['repeat-'+role(arm)];rows=events['rows']
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
            assert f+'trace/'+proc['pid'] in files and all(re.fullmatch('[a-f0-9]{64}',proc[k]) for k in ('raw','argv_sha256','exe_sha256'))
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
        scores=evaluate(plan,pairs);original=json.loads(raw('launcher/verify.stdout'))
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
            assert set(final)==set(m['allowed'])|set(m['registry'])
            entry['terminal_snapshot']=summarize({k:v['sha256'] for k,v in final.items() if v is not None},m['allowed']|registry)
        failed_maps[name]=entry
    return {'terminal':status,'launcher':exits,'observed_clocks':len(clocks),'verified_slots':len(verified),
            'complete_pair_checkpoints':len(checkpoint),'failed_slot_products':failed_maps,'retained_private_states':[k for k,v in byname.items() if v['retained_state']],
            'clocks_block_slot_arm_ns_exit':clocks,'exceptions':{k:sha(k) for k in files if k in ('result/first-failure.txt','admission.failure','launcher/score.stderr','launcher/verify.stderr')},
            'qualified':scores['qualifies'] if scores else False,'statistics':scores,'commitment_only_text':private_text}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('receipt',type=Path);p.add_argument('protocol',type=Path);p.add_argument('prior_native',type=Path)
    a=p.parse_args();q=json.loads(gzip.decompress(a.receipt.read_bytes()))
    bind_published_admission(q)
    print(json.dumps(check_packet(q,a.protocol,prior_native(a.prior_native)),indent=2,sort_keys=True))
