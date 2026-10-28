"""Check the original wall, independent continuation and the 50 retained native captures."""
from pathlib import Path
import json,re
from export import BASE,WALL_PARENT,WALL_PARENT_SHA,STOCK_GIT,STOCK_SRC,CONT_GIT,CONT_SRC,WALL_B,WALL_B_SHA,BOOT,BOOT_SHA,STOPPED_GIT,STOPPED_SHA,canonical,dig,file_sha

RETAINED='609e53b6ea3eb204ccc19b55266c61ef939bc73cce0b103c325a6f325ea3f7f2'
SOURCES={'original_ref':STOCK_GIT,'original_protocol_sha256':STOCK_SRC,'continuation_ref':CONT_GIT,'continuation_sha256':CONT_SRC,
         'stopped_evidence_ref':STOPPED_GIT,'stopped_evidence_sha256':STOPPED_SHA}
PHASES={'failure-1':1,'failure-2':1,'seed-repeat1':48}

def expected_retained(protocol):
    p=protocol/'retained-native-bindings.json';assert file_sha(p)==RETAINED;return json.loads(p.read_bytes())

def check_lineage(packet,protocol,public,sha,raw,obj):
    from catalog import digest
    from continuation import registrations
    h='parent-source/'
    assert sha(h+'SHA256SUMS')==WALL_PARENT_SHA and obj('parent-launch/binding.json')=={'ref':WALL_PARENT,'sha256':WALL_PARENT_SHA}
    parent={name:value for value,name in (row.split('  ',1) for row in raw(h+'SHA256SUMS').splitlines())}
    assert all(sha(h+name)==value for name,value in parent.items())
    model=json.loads((protocol/'parent-comparison.json').read_bytes())
    assert {n for n,v in parent.items() if sha('parent-b-source/'+n)!=v}==set(model['routing_or_provenance_files']) and len(parent)-len(model['routing_or_provenance_files'])==24
    assert model['parent_wall_ref']==WALL_PARENT and model['parent_manifest']==WALL_PARENT_SHA
    assert sha('parent-b-source/SHA256SUMS')==WALL_B_SHA and obj('parent-b-launch/binding.json')=={'ref':WALL_B,'sha256':WALL_B_SHA}
    parent_b={n:v for v,n in (line.split('  ',1) for line in raw('parent-b-source/SHA256SUMS').splitlines())};amend=json.loads((protocol/'amendment-comparison.json').read_bytes())
    assert all(sha('parent-b-source/'+n)==v for n,v in parent_b.items()) and set(amend['changed_previous_files'])=={n for n,v in parent_b.items() if sha('protocol/'+n)!=v}
    assert int(raw('bootstrap/exit'))==0 and sha('bootstrap/source/SHA256SUMS')==BOOT_SHA
    assert json.loads((protocol/'native-continuation.json').read_bytes())==SOURCES
    assert sha('continuation/source/SHA256SUMS')==CONT_SRC and sha('continuation/source/stopped-source-binding.json')==sha('protocol/retained-native-bindings.json')==RETAINED
    assert int(raw('continuation/exit'))==1 and obj('continuation/registration.json')==obj('stock/continuation-registration.json')==SOURCES
    registrations(obj('continuation/registration.json'),obj('stock/continuation-registration.json'),obj('launcher/catalog-publication.json'))
    assert {k:v for k,v in public['continuation'].items() if k not in ('bootreg','completion')}=={k:sha('stock/'+p) for k,p in [('continuation','continuation-registration.json'),('before','tree-before-resume.json'),('after','physical-preservation.json')]}
    lin=packet['lineage'];ids=lin['root_identities'];assert all(isinstance(pair,list) and len(pair)==2 and all(type(i) is int and i>0 for i in pair) for pair in ids)
    assert len(ids)==2 and ids[0][0]==ids[1][0] and ids[0][1]!=ids[1][1]
    assert lin['untouched']==dict.fromkeys(('parent_result_absent','parent_admission_absent','old_second_phase_absent','old_terminal_absent','parent_a_failure_absent','parent_b_pristine'),True)
    before=obj('stock/tree-before-resume.json');after=obj('stock/physical-preservation.json');tree=before['preserved_original'];seed=before['seed_state']
    for value in (tree,seed):
        assert set(value)=={'digest','objects','unique_file_bytes'} and re.fullmatch('[0-9a-f]{64}',value['digest']) and value['objects']>0 and value['unique_file_bytes']>0
    assert tree==before['byte_matched_copy'] and before['cross_root_regular_inode_overlap']==0
    assert [before['host_visible_original_root'],before['host_visible_copy_root']]==[str(BASE/x) for x in ('whole-wild-width-v1','whole-wild-width-v2')]
    assert [before['host_visible_original_inode'],before['host_visible_copy_inode']]==[p[1] for p in ids]
    import bootstrap_lineage as proof
    reg=obj('bootstrap/registration.json');done=obj('stock/bootstrap-completion.json')
    assert sha('bootstrap/source/startup-binding.json')==sha('protocol/bootstrap-startup.json')==proof.STARTUP_SHA
    assert sha('bootstrap/registration.json')==public['continuation']['bootreg'] and sha('stock/bootstrap-completion.json')==public['continuation']['completion']
    h={key:sha(n) for key,n in [('old_failure','retained/raw/failure.txt'),('old_exit','retained/raw/exit'),('startup_exit','continuation/exit'),('startup_stderr','continuation/stderr'),('startup_failure','stock/continuation-failure.txt')]}
    extra=proof.check(SOURCES,reg,h,raw('bootstrap/exit').encode(),before);proof.completion(reg,done,sha('stock/wall-view.json'),sha('stock/source/verify.py'))
    assert after==dict(old_complete_tree_final_sha256=tree['digest'],old_seed_state_final_sha256=seed['digest'],original_and_copy_initially_identical=True,old_capture_and_startup_exits=1,preserved_sources_and_stop=True,startup_traceback_sha256=h['startup_failure'])
    frozen=expected_retained(protocol);files=lin['file_identities'];indices=frozen['native_control_index']
    assert set(indices)==set(PHASES) and set(files)=={'retained','adopted'} and files['retained'].keys()==files['adopted'].keys()
    for label in files:
        reg=obj(label+'/registration.json');assert reg['protocol']==sha(label+'/source/SHA256SUMS')==STOCK_SRC and reg['commit']==STOCK_GIT
        paths=files[label];prefix=label+'/raw/';fixed={'failure.txt':'traceback','exit':'exit','seed.json':'seed','source/worker.py':'worker','commands/seed-repeat1/products.json':'seed_617_products'}
        assert all(sha(prefix+n)==frozen[k] for n,k in fixed.items())
        expected=set(fixed)
        for phase,count in PHASES.items():
            pf='commands/'+phase+'/physical.json';expected.add(pf);group={}
            for name in paths:
                m=re.fullmatch('captures/'+phase+r'/(\d+)/capture.json',name)
                if m:group[m[1]]=sha(prefix+name);expected.add(name)
            idx=indices[phase];assert len(group)==idx['targets']==count and digest(group)==idx['capture_tree'] and sha(prefix+pf)==idx['job_file']
        assert set(paths)==expected and all(len(v)==2 and v[0]==ids[0][0] and type(v[1]) is int and v[1]>0 for v in paths.values())
    assert not ({tuple(x) for x in files['retained'].values()} & {tuple(x) for x in files['adopted'].values()})
    return dict(**extra,bootstrap_registration_sha256=sha('bootstrap/registration.json'),bootstrap_completion_sha256=sha('stock/bootstrap-completion.json'),native_continuation_ref=CONT_GIT,native_continuation_manifest=CONT_SRC,stopped_native_ref=STOPPED_GIT,stopped_native_manifest=STOPPED_SHA,
                retained_native_bindings_sha256=RETAINED,retained_occurrences=50,new_occurrences=249,retained_width_pairs=800,original_wall_ref=WALL_PARENT,
                original_wall_manifest=WALL_PARENT_SHA,copy_receipt_sha256=sha('stock/tree-before-resume.json'),preservation_receipt_sha256=sha('stock/physical-preservation.json'))


def check_release(aux,admitted_ci,plan,public,admission):
    import base64
    from catalog import check_ci
    assert set(aux)=={'h2_release','h2_release_sha256','h2_release_b64','h2_physical','fresh_ci','owner_approval','idle'}
    h2=aux['h2_release'];encoded=base64.b64decode(aux['h2_release_b64'],validate=True)
    assert dig(encoded)==aux['h2_release_sha256'] and json.loads(encoded)==h2
    external=public['h2'];assert (h2['terminal_ref'],h2['terminal_file'],h2['terminal_sha256'],h2['status'])==tuple(external[k] for k in ('ref','file','sha256','status'))
    from sideproof import check_h2,H2_RESULT
    assert h2['terminal_component']==H2_RESULT and aux['h2_physical']==external['physical']
    code,ended,verified=check_h2(aux['h2_physical'],h2['terminal_file'],h2['terminal_sha256'])
    assert code==h2['score_exit'] and ended==h2['ended_unix_ns'] and verified<=h2['released_unix_ns']
    assert h2['host']=='charlie-ohm-relink-b-1024' and h2['study']=='rc17-text-size-first-selection-wall-plan' and h2['study_ref']=='44c3e6db80242b5461bbb3f86f2fae5a0f166a45' and h2['terminal_ref']!=h2['study_ref']
    assert h2['released_for']==public['wall_ref'] and h2['admission_sha256']==admission and h2['scored_processes_running']==0 and h2['owner_review']=='released by H2 operator after terminal'
    assert (h2['status']=='complete' and h2['score_exit']==0) or (h2['status']=='failed' and type(h2['score_exit']) is int and h2['score_exit']!=0)
    a=aux['owner_approval'];idle=aux['idle'];assert a['host']==idle['host']=='charlie-ohm-c5-check-1025' and a['admission_sha256']==idle['admission']==admission
    assert 0<h2['ended_unix_ns']<=h2['released_unix_ns']<=a['unix_ns'] and idle['unix_ns']>0
    assert a['owner_review'] and a['other_scored_processes']==idle['study_sessions']==idle['scored_commands']==0 and a['h2_release_sha256']==dig(encoded) and idle['no_compilers'] and idle['lock_clear']
    check_ci(plan,aux['fresh_ci']);normalize=lambda rows:{r['number']:(r['head'],r['url'],sorted(tuple(c[k] for k in ('name','status','conclusion','detailsUrl')) for c in r['checks'])) for r in rows}
    assert normalize(aux['fresh_ci'])==normalize(admitted_ci)
