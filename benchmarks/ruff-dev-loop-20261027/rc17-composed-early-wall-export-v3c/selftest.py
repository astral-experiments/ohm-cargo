"""Make a tiny synthetic native/48-slot terminal experiment; no original wall filesystem is read."""
import ast, base64, collections, copy, gzip, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import export as e,verify as v,bindings as b
PROTOCOL=Path(sys.argv[1]).resolve()
b.manifest(PROTOCOL,e.WALL);sys.path.insert(0,str(PROTOCOL))
import guards as g,catalog,verify_result,analysis
CAT='1'*40;ADM='2'*40;S='3'*64
def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    data=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    path.write_bytes(data);return e.dig(data)
def z(path,value):return put(path,gzip.compress(e.canonical(value),mtime=0))
def snap(p):return {'path':p.name,'sha256':e.file_sha(p)}
def make_manifest(r):return put(r/'SHA256SUMS',''.join(e.file_sha(p)+'  '+str(p.relative_to(r))+'\n' for p in sorted(r.rglob('*')) if p.is_file() and p.name!='SHA256SUMS').encode())
def sig(value):return e.dig(value.encode())
def hashes(n):return {str(i):sig(str(i)) for i in range(n)}
def must_fail(fn):
    try:fn()
    except (AssertionError,KeyError,ValueError,FileNotFoundError):return
    raise AssertionError('invalid synthetic evidence accepted')
def make_stock(p):
    plan=g.P;hist=json.loads(gzip.decompress((PROTOCOL/'historical-links.json.gz').read_bytes()))['phases']
    names=sorted({j['target'] for rows in hist.values() for j in rows})
    initial={n:sig('first '+n) for n in names};changed={n:plan['stopped_v2']['unadmitted'].get(Path(n).name,sig('second '+n)) for n in names}
    initial.update({f'target/synthetic/plain-{i}':sig('plain'+str(i)) for i in range(60)})
    files={t:{'target':t,'recipes':{},'raw_private_evidence':sig('private-'+t),'exact_fields_and_unchanged_ranges':{}} for t in names}
    targets={t:{'evidence':{'file':'targets/'+Path(t).name+'/all-widths.json','sha256':files[t]['raw_private_evidence']},'recipes':{}} for t in names}
    fresh={};old={};current=0;commands={};bf=list(range(16))
    for ph,rows in hist.items():
        fresh[ph]=[];old[ph]=[];counts=collections.Counter()
        for j in rows:
            t=j['target'];kind=catalog.expected_kind(ph,t);old[ph].append(j|{'kind':kind});counts[t]+=1
            current+=1;key=sig('recipe'+str(current));pins=[1000+current*40+i for i in range(33)]
            widths=[dict(width=i+1,plain_exit=0,depfile_exit=0,plain_sha256=hashv,depfile_sha256=hashv,plain_pid=pins[2*i],depfile_pid=pins[2*i+1]) for i,hashv in enumerate([initial[t],changed[t]]*8)]
            vals=[initial[t],changed[t]];tmap={v:'bodies/'+v for v in vals};ah=j['argv_sha256']
            tr={str(k):sig('trace'+str(k)) for k in pins};inputs=[[sig('orig'),sig('real'),10,sig('bytes')]]
            targets[t]['recipes'][key]={'phase':ph,'occurrence':counts[t],'stable_argv_sha256':ah,'inputs_sha256':sig(key+'inputs'),'bodies':tmap,'widths':widths,'stock_trace_set_sha256':g.digest(tr),'raw_input_file':{'sha256':sig(key+'raw inputs')}}
            fresh[ph].append(dict(target=t,kind=kind,occurrence=counts[t],exit=0,wild_sha256=plan['sdk']['tools']['wild'],recipe=key,
                                   raw_sha256=initial[t],argv_sha256=ah,exec_sha256=sig('exec'+key)))
            files[t]['recipes'][key]=dict(phase=ph,ordinal=counts[t],raw_default=initial[t],stock_processes=tr,
                raw_argv_sha256=ah,all_ordered_argv_fields_sha256=[sig('arg')],resolved_positive_and_literal_inputs_as_recorded=inputs,
                exact_physical_input_json_sha256=sig(key+'raw inputs'),public_input_projection_sha256=g.digest(inputs),kind='workspace',positive_names=1,positive_bytes=10,
                symbols_object_sha256=S,raw_dylibs_empty_directory=True,resolution_file_sha256=S,widths=widths,whole_bodies=vals)
        seed=ph.startswith('seed');commands[ph]=dict(units=617 if seed else 619,fresh=563,exes=100 if seed else 102,native=hashes(108 if seed else 110),counts={'wild':len(rows)},status=0)
    ordinal=0
    for t in names:
        for h,attribute in [(initial[t],0),(changed[t],8)]:
            files[t]['exact_fields_and_unchanged_ranges'][h]=dict(normalized=sig(t),bytes=70,sha256=h,build_id='ab'*32,rodata_entsize=attribute,
                fields={'build_id':[5,'ab'*32],'rodata':[40,attribute.to_bytes(8,'little').hex()]},ranges=[[0,5,S],[37,40,S],[48,70,S]])
        if Path(t).name in plan['stopped_v2']['unadmitted']:
            ordinal+=1;phase=f'failure-{ordinal}';key=sig(phase);r=copy.deepcopy(next(iter(files[t]['recipes'].values())))
            r['phase']=phase;r['kind']='reconstructed';files[t]['recipes'][key]=r;put(p/'reconstructions'/f'{phase}.json',{'raw':r['whole_bodies']})
        z(p/'links'/(Path(t).name+'.json.gz'),files[t])
    assert current==297 and ordinal==2
    term={t:{} for t in names};td=put(p/'terminal.json',term)
    ind=dict(accepted=True,admitted_or_failed_states_modified=0,all_untimed_stock_wild_processes=9867,explicit_reported_and_plain=9568,ordinary_stock_controls=299,
             workspace_linked_targets=50,phase_occurrences={ph:len(rows) for ph,rows in fresh.items()},raw_bodies=100)
    idig=put(p/'independent.json',ind)
    view=dict(schema=1,native_ref=e.NATIVE_GIT,wild_source=plan['catalog_scope']['public_wild_source'],wild_sha256=plan['sdk']['tools']['wild'],
        cpu=bf,jobs=8,widths=list(range(1,17)),historical=old,fresh=fresh,targets=targets,terminal={'file':'terminal.json','sha256':td},
        independent_verification={'file':'independent.json','sha256':idig})
    raw=e.canonical(view);put(p/'wall-view.json.gz',gzip.compress(raw,mtime=0));put(p/'wall-view.sha256',(e.dig(raw)+'  wall-view.json\n').encode())
    z(p/'commands.json.gz',commands);put(p/'registration.json',{'commit':e.STOCK_GIT,'protocol':e.STOCK_SRC});mani=make_manifest(p)
    desc={'ref':CAT,'manifest':mani,'files':{k:snap(p/name) for k,name in [('view_gzip','wall-view.json.gz'),('terminal','terminal.json'),('independent','independent.json'),('registration','registration.json')]}}
    return initial,changed,desc,raw

def make_lineage(base,stock,descriptor):
    import lineage
    old=base/'whole-wild-width-v1';new=base/'whole-wild-width-v2';deployed=base/'whole-wild-width-v2-protocol'
    src=PROTOCOL.parent;parent=base/'wall-protocol-v3';shutil.copytree(src/'rc17-composed-early-wall-plan-v3',parent)
    put(base/'wall-launch-v3/binding.json',dict(sha256=e.WALL_PARENT_SHA,ref=e.WALL_PARENT))
    shutil.copytree(src/'rc17-composed-early-wall-plan-v3b',base/'wall-protocol-v3b')
    put(base/'wall-launch-v3b/binding.json',dict(sha256=e.WALL_B_SHA,ref=e.WALL_B))
    boot=base/'whole-wild-width-v2-bootstrap';bsrc=src/'rc17-composed-all-links-bootstrap'
    for n in ('SHA256SUMS','startup-binding.json'):
        put(boot/'source'/n,(bsrc/n).read_bytes())
    reg=dict(lineage.SOURCES,bootstrap_ref=e.BOOT,bootstrap_sha256=e.BOOT_SHA)
    br=put(boot/'registration.json',reg);put(boot/'exit',b'0\n')
    import bootstrap_lineage as proof
    done=dict(reg,whole_native_view_sha256=e.file_sha(new/'wall-view.json'),startup_snapshot_binding=proof.STARTUP_SHA,completed_original_verifier_sha256=proof.VERIFIER)
    bc=put(new/'bootstrap-completion.json',done)
    put(new/'source/verify.py',(src/'rc17-composed-all-links-protocol/verify.py').read_bytes())
    put(stock/'bootstrap-registration.json',(boot/'registration.json').read_bytes())
    descriptor['files']['bootreg']=snap(stock/'bootstrap-registration.json')
    pm=src/'rc17-composed-all-links-protocol'/'SHA256SUMS'
    for root in (old,new):
        put(root/'source/SHA256SUMS',pm.read_bytes());put(root/'registration.json',{'commit':e.STOCK_GIT,'protocol':e.STOCK_SRC})
    put(deployed/'source/SHA256SUMS',(src/'rc17-composed-all-links-continuation-plan'/'SHA256SUMS').read_bytes())
    put(deployed/'source/stopped-source-binding.json',(PROTOCOL/'retained-native-bindings.json').read_bytes())
    put(deployed/'registration.json',lineage.SOURCES);put(deployed/'exit',b'1\n');put(deployed/'stderr',b'generated prior startup refusal\n');put(new/'continuation-failure.txt',b'generated earlier continuation refusal\n');put(new/'continuation-registration.json',lineage.SOURCES)
    # A generated physical native tree cannot share the published cryptographic preimages. Only this
    # test harness substitutes its calculated 50-file golden, as it does for the synthetic QA blob.
    frozen={'native_control_index':{}}
    for name,key in [('failure.txt','traceback'),('exit','exit'),('seed.json','seed'),('source/worker.py','worker'),('commands/seed-repeat1/products.json','seed_617_products')]:
        val=b'1\n' if name=='exit' else e.canonical({'generated':key});frozen[key]=put(old/name,val);put(new/name,val)
    for phase,count in lineage.PHASES.items():
        group={}
        for i in range(count):
            name='captures/'+phase+'/'+str(i+100)+'/capture.json';data={'generated':name};group[str(i+100)]=put(old/name,data);put(new/name,data)
        name='commands/'+phase+'/physical.json';h=put(old/name,group);put(new/name,group)
        frozen['native_control_index'][phase]={'capture_tree':g.digest(group),'job_file':h,'targets':count}
    lineage.expected_retained=lambda _:frozen
    tree={'digest':sig('initial native'),'objects':1000,'unique_file_bytes':1000};seed=dict(tree,digest=sig('initial seed'))
    before={'preserved_original':tree,'byte_matched_copy':tree,'seed_state':seed,'cross_root_regular_inode_overlap':0,
        'host_visible_original_root':str(e.BASE/old.name),'host_visible_copy_root':str(e.BASE/new.name),
        'host_visible_original_inode':old.stat().st_ino,'host_visible_copy_inode':new.stat().st_ino}
    hashes={'old_failure':frozen['traceback'],'old_exit':frozen['exit'],'startup_exit':e.file_sha(deployed/'exit'),'startup_stderr':e.file_sha(deployed/'stderr'),'startup_failure':e.file_sha(new/'continuation-failure.txt')}
    proof.RECEIPT=dict(proof.RECEIPT,new_root_preverified=before,immutable_v1_exception=hashes['old_failure'],immutable_v1_exit=hashes['old_exit'],startup_exit1=hashes['startup_exit'],launcher_stderr=hashes['startup_stderr'],frozen_continuation_traceback=hashes['startup_failure'])
    extra=proof.check(lineage.SOURCES,reg,hashes,b'0\n',before)
    after={'old_complete_tree_final_sha256':tree['digest'],'old_seed_state_final_sha256':seed['digest'],'original_and_copy_initially_identical':True,'old_capture_and_startup_exits':1,'startup_traceback_sha256':hashes['startup_failure'],'preserved_sources_and_stop':True}
    a=put(new/'tree-before-resume.json',before);b=put(new/'physical-preservation.json',after)
    for key,n in [('continuation','continuation-registration.json'),('before','tree-before-resume.json'),('after','physical-preservation.json'),('completion','bootstrap-completion.json')]:
        shutil.copy2(new/n,stock/n);descriptor['files'][key]=snap(stock/n)
    descriptor['manifest']=make_manifest(stock)
    return dict(**extra,bootstrap_registration_sha256=br,bootstrap_completion_sha256=bc,native_continuation_ref=e.CONT_GIT,native_continuation_manifest=e.CONT_SRC,stopped_native_ref=e.STOPPED_GIT,stopped_native_manifest=e.STOPPED_SHA,
                retained_native_bindings_sha256=lineage.RETAINED,retained_occurrences=50,new_occurrences=249,retained_width_pairs=800,
                original_wall_ref=e.WALL_PARENT,original_wall_manifest=e.WALL_PARENT_SHA,copy_receipt_sha256=a,preservation_receipt_sha256=b)


def synth(base,tmp):
    fp=base/'wall-protocol-v3c';shutil.copytree(PROTOCOL,fp)
    launch=base/'wall-launch-v3c';qa=base/'wall-qa-v1';w=base/'early-scheduler-wall-rc17-v3c';stock=tmp/'independently-published-stock';adpub=tmp/'independently-published-admission'
    w.mkdir();launch.mkdir();shutil.copy2(HERE/'job-template.py',launch/'job.py');put(launch/'binding.json',dict(ref=e.WALL_GIT,sha256=e.WALL))
    # Prior wall directories do not exist; none of the generated values come from any clock.
    initial,changed,cd,view=make_stock(stock);root=base/'whole-wild-width-v2'
    put(root/'wall-view.json',view)
    for n in ('registration.json','independent.json','terminal.json'):shutil.copy2(stock/n,root/n)
    registered=PROTOCOL.parent/'rc17-composed-all-links-protocol/SHA256SUMS'
    put(root/'source/SHA256SUMS',registered.read_bytes())
    lineage_proof=make_lineage(base,stock,cd)
    put(launch/'ci.json',(fp/'ci-exact-heads.json').read_bytes())
    ch=e.file_sha(launch/'ci.json');pub=dict(plan_ref=e.WALL_GIT,plan_manifest=e.WALL,native_reference=e.NATIVE_GIT,catalog_protocol_ref=e.BOOT,catalog_result_ref=CAT,
        independent_review='accepted',view_sha256=e.dig(view),terminal_sha256=e.file_sha(stock/'terminal.json'),verifier_receipt_sha256=e.file_sha(stock/'independent.json'))
    pubsum=put(launch/'catalog-publication.json',pub)
    assert (e.STOCK_SRC,e.WALL)==(e.file_sha(root/'source/SHA256SUMS'),e.file_sha(fp/'SHA256SUMS'))
    for role,src in [('v2','rc17-composed-early-native-registry-plan'),('v3','rc17-composed-early-native-workspace-plan')]:
        put(base/('protocol-'+role)/'SHA256SUMS',(PROTOCOL.parent/src/'SHA256SUMS').read_bytes())
    qrec=put(qa/'synthetic.json',{'synthetic':True});q={'source':g.P['source'],'status':'pass','observer':g.P['subject_images']['B'],'composed':g.P['subject_images']['C'],
        'tests':{k:{'exit':0,'evidence':'synthetic.json','receipt_sha256':qrec,'subject':g.P['subject_images']['C']} for k in ['built-library','unused','used','missing-proof','ordinary-reader','cached-state-migration','observer-replacement']},
        'build':{k:{'evidence':'synthetic.json','receipt_sha256':qrec,'cargo_sha256':g.P['subject_images'][a]} for a,k in g.ROLES.items()}}
    qsha=put(qa/'qa.json',q);v.QA_SHA=qsha
    can=e.BASE/'ruff-evaluation-v2/canonical';names=list(initial);files={str(can/k):v for k,v in initial.items()}
    exes=list(files)[:102];reg={str(can/'target'/f'synth-registry-{i}'):sig(str(i)) for i in range(78)}
    listing=b'one synthetic test: test\n';lh=e.dig(listing);diagnostics=[]
    rows=[dict(reason='compiler-artifact',fresh=i<563,executable=exes[i] if i<102 else None,filenames=[(list(files)[i] if i<110 else 'out/'+str(i))],
        package_id='path+file:///ruff#synth' if i<110 else 'registry+synth',manifest_path='/canonical/synthetic/Cargo.toml',target={'kind':['test']},profile={'test':i<84},features=[]) for i in range(619)]
    typed=[json.dumps({k:r[k] for k in e.SCHEMA},sort_keys=True) for r in rows]
    ids={sig(s):{'owner':'workspace' if i<110 else 'registry','executable':str(Path(exes[i]).relative_to(can)) if i<102 else None,'test':i<84,'fresh':i<563} for i,s in enumerate(typed)}
    procs=[];traces={}
    for i,(kind,target,argv,exe) in enumerate([('full','ron',['rustc','--crate-name','ron'],'/tool/rustc'),('wild',exes[0],['ld','-o',exes[0]],'/tool/ld')],1):
        name=f'exec.{i}';line=f'execve({json.dumps(exe)}, {json.dumps(argv)}, 0xbeef /* 2 vars */) = 0'
        traces[name]=(line+'\n+++ exited with 0 +++\n').encode()
        procs.append(dict(kind=kind,target=target,argv=argv,exe=exe,pid=name,raw=sig(line),exit=0))
    counts={'full':1,'wild':1};critical={'fresh':True,'file':str(can/'target/fake-typed.rlib'),'sha':sig('saved')}
    products=dict(units=619,fresh=563,roster=g.digest(sorted(typed)),exes=exes,diagnostics=[],ty_server=critical,e2e=exes[:1],native=files,counts=counts)
    variant=put(base/'wall-native-proofs/variants.json',{})
    statmap={ph+'-'+role:counts for ph in ('selected','repeat') for role in ('observer','composed')}
    old=dict(subjects=g.P['subject_images'],allowed={k:[v] for k,v in files.items()},roster=g.summary(products),typed_seed_rlib=critical,files={},
        stats=statmap,registry=reg,registry_sha256=g.digest(reg),repeat_roster=g.digest(sorted(g.row_roster(procs).items())),listing_sha256=lh,source_plan=g.P['native_manifest'],variants_sha256=variant)
    oldsha=put(base/'wall-native-proofs/frozen-native-guard.json',old)
    step=dict(rows=ids,workspace=initial,registry={str(Path(k).relative_to(can)):v for k,v in reg.items()},fresh=563,diagnostics=[],receipt_sha256={})
    priors=[{'canonical':str(can),'steps':{ph:step for ph in catalog.PHASES}},{'targets':{},'native_variant_manifest_sha256':variant},
        {'subjects':old['subjects'],'typed_roster':old['roster'],'listing_sha256':lh,'counts':statmap,'native_protocol':old['source_plan'],'native_gate_sha256':oldsha,'registry_sha256':old['registry_sha256'],'variants_sha256':variant}]
    expanded={k:sorted([v,changed[k]]) if k in changed else [v] for k,v in initial.items()}
    cert=dict(plan_ref=e.WALL_GIT,catalog_protocol_ref=e.BOOT,catalog_result_ref=CAT,registered_catalog_sha256=pubsum,catalog_view_sha256=pub['view_sha256'],
        terminal_sha256=pub['terminal_sha256'],independent_verification_sha256=pub['verifier_receipt_sha256'],ci_sha256=ch,widths=list(range(1,17)),linked_targets=50,exact_others=60,
        historical_occurrences=297,fresh_occurrences=297,input_families=297,raw_sha256_sets=g.digest(expanded),prior_failure_sha256=g.P['stopped_v2']['first_failure_sha256'],
        native_protocol_ref=e.STOCK_GIT,native_protocol_manifest=e.STOCK_SRC,independent_plain_and_reporting=9568,independent_ordinary_links=299,literal_recipes=297,**lineage_proof)
    m=old|{'allowed':{str(can/k):v for k,v in expanded.items()},'native_catalog':cert};seed=sig('seed')
    adm=base/'early-scheduler-wall-admission-v3c.json'
    adhash=put(adm,dict(worker_manifest=e.WALL,scored_commands=0,qa_sha256=qsha,ci_status='pass',fs='ext4',copy='never',pessimistic_full_copy_bytes_all_48=48,seed={'unique_file_bytes':1,'digest':seed},native=m))
    grant=dict(go='score exact v3c 24 fresh pairs',native_sha256=adhash,plan_manifest=e.WALL,published_plan=e.WALL_GIT,published_catalog=CAT,published_native=ADM,ci_sha256=ch,h5_clear=True,other_host_measurement=False,ci_review='accepted')
    ar=dict(plan_ref=e.WALL_GIT,catalog_ref=CAT,admission_ref=ADM,plan_manifest=e.WALL,admission_sha256=adhash,catalog_publication_sha256=pubsum,ci_sha256=ch)
    for name,val in [('grant.json',grant),('admission-publication.json',ar)]:put(launch/name,val);put(w/name,val)
    adpub.mkdir();shutil.copy2(adm,adpub/'admission.json');shutil.copy2(launch/'ci.json',adpub/'ci.json');shutil.copy2(launch/'catalog-publication.json',adpub/'catalog-publication.json')
    witness=dict(independent_review='accepted',workspace_linked_targets=50,fresh_occurrences=297,registry_exact=78,historical_native_ref=e.NATIVE_GIT,**{k:pub[k] for k in ('view_sha256','terminal_sha256','verifier_receipt_sha256')})
    import sideproof
    widths={j['evidence']['file']:j['evidence']['sha256'] for j in json.loads(view)['targets'].values()}
    widths.update({'terminal.json':pub['terminal_sha256'],'wall-view.json':pub['view_sha256'],'independent.json':pub['verifier_receipt_sha256']})
    witness.update(dict(read_only=True,counted_clocks=0,original_verifier_sha256=sideproof.ORIGINAL_VERIFIER,reopened_unique_stock_processes=9867,explicit_processes=9568,ordinary_controls=299,byte_recomputed_outputs=widths,previous_v2_startup_failure_sha256='89caf4045b6b3a8a76c48cf959f9603a9814cc4d2931504e134afaa62ef5f127',full_predecessor_commitment='4b91f1b8d572612351ea5261e0bd3fdc0444ebc62d18ec64e51a3a4cf0cd0237'))
    put(stock/'root-native-reread.py',(PROTOCOL.parent/'rc17-composed-early-test-ops/root-native-reread.py').read_bytes())
    put(stock/'review.json',witness);cd['manifest']=make_manifest(stock)
    prov={'catalog_result_component':'generated-stock','catalog_result_ref':CAT,'root_witness_file':'review.json','reread_source_sha256':sideproof.NATIVE_READER,'independent_verifier_file':'independent.json','bootstrap_ref':e.BOOT,'bootstrap_manifest':e.BOOT_SHA}
    for dest,source in [('root-native-witness.json','review.json'),('native-verifier.json','independent.json'),('bootstrap-registration.json','bootstrap-registration.json'),('bootstrap-completion.json','bootstrap-completion.json')]:
        raw=(stock/source).read_bytes();put(launch/'provenance'/dest,raw);put(adpub/dest,raw)
    put(launch/'provenance/provenance.json',prov);put(adpub/'provenance.json',prov)
    h2=tmp/'published-h2';put(h2/'unrelated-h2-observations',b'never needed by the second study');hd=put(h2/'terminal.json',{'phase':'all_slots_finished','slots':48})
    roles=dict(admit=0,score=0,verify=0);physical=dict(kind='result',registration={'wall_ref':sideproof.H2_PLAN},role_exits=roles,role_logs={r:dict(out=sig(''),err=sig(''),exit=sig(str(v))) for r,v in roles.items()},terminal_file='terminal.json',terminal_sha256=hd,ended_unix_ns=1,verified_unix_ns=2)
    put(h2/'host-receipts.json',physical)
    adfiles={'native':'admission.json','ci':'ci.json','catalog_publication':'catalog-publication.json','witness':'root-native-witness.json','proof':'native-verifier.json','bootreg':'bootstrap-registration.json','completion':'bootstrap-completion.json','provenance':'provenance.json'}
    pins={'catalog':cd,'admission':{'ref':ADM,'manifest':make_manifest(adpub),'files':{k:snap(adpub/name) for k,name in adfiles.items()}},'h2':{'ref':'4'*40,'manifest':make_manifest(h2),'files':{'terminal':snap(h2/'terminal.json'),'host':snap(h2/'host-receipts.json')}}}
    lane=dict(study='rc17-text-size-first-selection-wall-plan',study_ref='44c3e6db80242b5461bbb3f86f2fae5a0f166a45',host='charlie-ohm-relink-b-1024',status='complete',score_exit=0,terminal_component=sideproof.H2_RESULT,terminal_ref='4'*40,terminal_file='terminal.json',terminal_sha256=hd,ended_unix_ns=1,released_unix_ns=2,released_for=e.WALL_GIT,admission_sha256=adhash,scored_processes_running=0,owner_review='released by H2 operator after terminal')
    h2raw=e.canonical(lane);h2sha=e.dig(h2raw);hh='charlie-ohm-c5-check-1025'
    aux=dict(h2_physical=physical,h2_release=lane,h2_release_sha256=h2sha,h2_release_b64=base64.b64encode(h2raw).decode(),fresh_ci=json.loads((fp/'ci-exact-heads.json').read_bytes()),owner_approval=dict(host=hh,admission_sha256=adhash,other_scored_processes=0,owner_review='synthetic H5 owner',h2_release_sha256=h2sha,unix_ns=3),idle=dict(host=hh,admission=adhash,lock_clear=True,no_compilers=True,study_sessions=0,scored_commands=0,unix_ns=3))
    put(launch/'operator-release.json',aux)
    public=b.bind_external(pins,stock,adpub,h2)
    for stage in ('admit','score','verify'):
        for suffix in ('exit','out','err'):put(launch/(stage+'.'+suffix),b'0' if suffix=='exit' else b'')
    put(launch/'admit.out',('zero-clock binding '+adhash+'\n').encode());put(launch/'score.out',''.join(f'{i}/24 guarded pairs\n' for i in range(1,25)).encode())
    standard=b'\n'.join(e.canonical(x) for x in [*rows,{'reason':'build-finished','success':True}])+b'\n';pairs=[];start=1
    for i,order in enumerate(g.P['order'],1):
        ns={}
        for j,arm in enumerate(order,1):
            folder=w/f'{i:02d}-{j}-{arm}';o=folder/'ordinary';f=folder/'unchanged';kind=g.P['subjects'][arm];id=dict(block=i,slot=j,arm=arm,image=m['subjects'][arm])
            put(folder/'start.json',id|dict(native_binding=adhash,copy='never',seed=seed,cpu=g.P['cpu'],free=99*2**30,loadavg=[0,0,0]))
            delta=100 if arm=='B' else 65;ns[arm]=delta;put(o/'clock.json',dict(argv=g.P['command'],returncode=0,start=start,stop=start+delta,elapsed_ns=delta));start+=delta+1
            put(o/'stdout',b'');put(o/'stderr',b'Finished\n');put(o/'e2e-list',listing);put(o/'e2e-list.stderr',b'')
            hx=put(folder/'first-110.json',files);hr=put(folder/'first-78-registry.json',reg);put(f/'products.json',products);put(f/'physical.json',procs);put(f/'e2e-list',listing);put(f/'registry-native.json',reg)
            put(f/'stdout',standard);put(f/'stderr',b'');put(f/'command.json',dict(arm=kind,binary=m['subjects'][arm],code=0,edited=True,traced=True,command=g.P['command']+['--message-format=json']))
            for key,content in traces.items():put(f/'trace'/key,content)
            put(folder/'verified.json',id|dict(elapsed_ns=delta,registry_78=hr,first_110=hx,follow_110=g.digest(files),follow_roster=m['roster'],follow_counts=counts,follow_fresh=563,
                stdout=e.dig(b''),stderr=sig('Finished\n'),e2e_list=lh,diagnostics={}))
        pairs.append(dict(block=i,order=order,ns=ns,matching_raw=110,raw_differences={}))
    rh=put(w/'pairs.json',pairs);oh=put(w/'result.json',analysis.evaluate(g.P,pairs));put(w/'complete.json',dict(pairs=24,slots=48,admission=adhash,plan=e.WALL,rows=rh,analysis=oh))
    replay=verify_result.run(w,adm);put(launch/'verify.out',replay)
    return public,priors,pins,stock,adpub,w,launch
def run():
    with tempfile.TemporaryDirectory(prefix='terminal-export-v3c-generated-') as tmp:
        tmp=Path(tmp);root=tmp/'synthetic-h5';root.mkdir()
        public,priors,pins,stock,adpub,wall,log=synth(root,tmp)
        # Refuse any attempt to open an old wall state, or a current wall while a role still runs.
        tried=[];denied=['early-scheduler-wall-rc17-v2','wall-launch-v2','early-scheduler-wall-rc17-v3','early-scheduler-wall-rc17-v3b'];guard={'live':False}
        def audit(what,args):
            if what not in ('open','os.listdir','os.scandir') or not args or not isinstance(args[0],(str,bytes)):return
            path=os.fsdecode(args[0])
            if any(('/'+k+'/') in path or path.endswith('/'+k) for k in denied) or guard['live'] and str(wall) in path:
                tried.append(path);raise RuntimeError('protected study file opened')
        denied.append('unrelated-h2-observations');sys.addaudithook(audit)
        complete=e.capture(root);r=v.check_packet(complete,PROTOCOL,priors,public)
        assert r['terminal']=='complete' and r['qualified'] and r['verified_slots']==48 and r['statistics']['favorable']==24
        assert r['statistics']['extreme']==2 and r['statistics']['assignments']==2704156 and all(abs(x-35)<1e-10 for x in r['statistics']['ci95'])
        def check(p):return v.check_packet(p,PROTOCOL,priors,public)
        bad=copy.deepcopy(complete);bad['slots']['01-1-B']['jobs'][0]['kind']='wild';must_fail(lambda:check(bad))
        bad=copy.deepcopy(complete);bad['bodies'][bad['files']['01-1-B/ordinary/stderr']['sha256']]+='x';must_fail(lambda:check(bad))
        for delta in ({'catalog_ref':e.STOCK_GIT},{'admission_ref':g.P['stopped_v2']['result_ref']},{'ci_sha':'0'*64},{'admission_sha':'1'*64},{'catalog_publication_sha':'3'*64}):
            must_fail(lambda:v.check_packet(complete,PROTOCOL,priors,public|delta))
        bad=copy.deepcopy(pins);bad['catalog']['files']['terminal']['sha256']='0'*64;must_fail(lambda:b.bind_external(bad,stock,adpub,tmp/'published-h2'))
        bad=copy.deepcopy(pins);bad['admission']['ref']=CAT;must_fail(lambda:b.bind_external(bad,stock,adpub,tmp/'published-h2'))
        bad=copy.deepcopy(complete);q='launcher/ci.json';raw=json.loads(bad['bodies'][bad['files'][q]['sha256']]);raw[0]['head']='4'*40
        body=e.canonical(raw);bad['bodies'][e.dig(body)]=body.decode();bad['files'][q]={'sha256':e.dig(body),'bytes':len(body),'capture':'verbatim'}
        must_fail(lambda:check(bad))
        bad_view=copy.deepcopy(public['view']);t=next(iter(bad_view['targets']));key=next(iter(bad_view['targets'][t]['recipes']))
        bad_view['targets'][t]['recipes'][key]['bodies'][sig('unpublished width')]='body';must_fail(lambda:v.check_packet(complete,PROTOCOL,priors,public|{'view':bad_view}))
        make=tmp/'single-event';make.mkdir();(make/'trace').mkdir()
        record=json.loads((wall/'01-1-B/unchanged/physical.json').read_bytes())[:1];record[0]['argv'].append('foreign')
        put(make/'physical.json',record);shutil.copy2(wall/'01-1-B/unchanged/trace/exec.1',make/'trace/exec.1');must_fail(lambda:e.project_jobs(make/'physical.json'))
        # Both physical stores must have the original captures, and inode-disjoint contents.
        bad=copy.deepcopy(complete);lin=bad['lineage'];lin['file_identities']['adopted']['seed.json']=lin['file_identities']['retained']['seed.json'];must_fail(lambda:check(bad))
        bad=copy.deepcopy(complete);del bad['lineage']['file_identities']['retained']['captures/failure-1/100/capture.json'];must_fail(lambda:check(bad))
        bad=copy.deepcopy(complete);bad['lineage']['untouched']['parent_admission_absent']=False;must_fail(lambda:check(bad))
        bad=copy.deepcopy(complete);bad['files']['adopted/raw/seed.json']['sha256']='0'*64;must_fail(lambda:check(bad))
        bad=copy.deepcopy(public);bad['continuation']['before']='0'*64;must_fail(lambda:v.check_packet(complete,PROTOCOL,priors,bad))
        bad=copy.deepcopy(pins);bad['catalog']['ref']=e.WALL_PARENT;must_fail(lambda:b.bind_external(bad,stock,adpub,tmp/'published-h2'))
        bad=copy.deepcopy(pins);bad['catalog']['ref']=e.CONT_GIT;must_fail(lambda:b.bind_external(bad,stock,adpub,tmp/'published-h2'))
        # Each stopped predecessor, the new startup and the independent, separately signed-off H2 end are required.
        for path in ('continuation/stderr','continuation/exit','stock/continuation-failure.txt','retained/raw/failure.txt','bootstrap/registration.json','bootstrap/source/startup-binding.json','bootstrap/exit','stock/bootstrap-completion.json','launcher/operator-release.json'):
            bad=copy.deepcopy(complete);del bad['files'][path];must_fail(lambda:check(bad))
        for path in ('continuation/stderr','stock/continuation-failure.txt','bootstrap/source/startup-binding.json','stock/source/verify.py'):
            bad=copy.deepcopy(complete);bad['files'][path]['sha256']='0'*64;must_fail(lambda:check(bad))
        bad=copy.deepcopy(public);del bad['h2'];must_fail(lambda:v.check_packet(complete,PROTOCOL,priors,bad))
        for key in ('ref','sha256','status'):
            bad=copy.deepcopy(public);bad['h2'][key]='not-the-terminal';must_fail(lambda:v.check_packet(complete,PROTOCOL,priors,bad))
        nested={'h2_release_b64':base64.b64encode(b'{"private":"/home/unrelated/private/path"}').decode(),'h2_release':{'private':'safe apparent text'}}
        guard_file=tmp/'unsafe-base64';put(guard_file,nested);fs={};bodies={};e.add(fs,bodies,guard_file,'launcher/operator-release.json',include=True)
        assert not bodies and fs['launcher/operator-release.json']['capture']=='private-text'
        import sideproof
        reread=json.loads((stock/'review.json').read_bytes())
        for k,vv in [('ordinary_controls',298),('reopened_unique_stock_processes',9866),('original_verifier_sha256','f'*64),('byte_recomputed_outputs',{}),('read_only',False),('counted_clocks',1)]:
            must_fail(lambda:sideproof.check_native(reread|{k:vv},public['view'],public['catalog_hashes']))
        for field,var in [('verified_unix_ns',0),('terminal_sha256','2'*64),('role_exits',{'admit':0,'score':0,'verify':1}),('role_logs',{})]:
            rec=public['h2']['physical']|{field:var};must_fail(lambda:sideproof.check_h2(rec,'terminal.json',public['h2']['sha256']))
        first=(wall/'01-1-B/ordinary/clock.json').read_bytes()
        (log/'verify.exit').unlink()
        guard['live']=True;must_fail(lambda:e.capture(root));guard['live']=False
        put(log/'verify.exit',b'1');put(log/'verify.err',b'RuntimeError: synthetic final verification rejected\n')
        failed=e.capture(root);vr=v.terminal_report(failed,PROTOCOL,priors,public)
        assert vr['terminal']=='verify-failed' and vr['statistics'] is None and failed['files']['result/result.json']['capture']=='digest-only'
        # Derivative old effects cannot leak through the failing verifier process' saved stdout either.
        assert failed['files']['launcher/verify.out']['capture']=='digest-only'
        for ext in ('out','err','exit'):(log/('verify.'+ext)).unlink()
        put(log/'score.exit',b'1');exc=b'ValueError: synthetic native output not admitted\n';put(log/'score.err',exc);put(wall/'first-failure.txt',exc)
        for file in wall.iterdir():
            if file.is_dir() and file.name not in ('01-1-B','01-2-C','02-1-B','02-1-C'):shutil.rmtree(file)
        for file in ('result.json','complete.json'):(wall/file).unlink()
        put(wall/'pairs.json',b.read(wall/'pairs.json')[:1]);d=next(wall.glob('02-1-*'));(d/'verified.json').unlink();shutil.rmtree(d/'unchanged');(d/'private-state').mkdir()
        broken=b.read(d/'first-110.json');ident=next(iter(broken));broken[ident]=sig('novel rejected ELF');put(d/'first-110.json',broken)
        aborted=e.capture(root);ar=v.check_packet(aborted,PROTOCOL,priors,public)
        assert ar['terminal']=='score-failed' and ar['statistics'] is None and ar['observed_clocks']==3 and ar['verified_slots']==2
        assert ar['failed_slot_products'][d.name]['first_workspace']['unadmitted']=={ident:sig('novel rejected ELF')}
        assert ar['exceptions']['result/first-failure.txt']==e.dig(exc) and ar['retained_private_states']==[d.name]
        assert len(aborted['slots'][d.name]['terminal_retained_outputs'])==188 and (wall/'01-1-B/ordinary/clock.json').read_bytes()==first
        # A failed slot with a new private registry endpoint remains hash-only, retained untouched on origin.
        private=b'Actual failed output descriptor\nValueError in /home/another-person/private/token.rs\n';put(wall/'first-failure.txt',private)
        priv=e.capture(root);rep=v.check_packet(priv,PROTOCOL,priors,public)
        assert rep['statistics'] is None and rep['exceptions']['result/first-failure.txt']==e.dig(private)
        assert priv['files']['result/first-failure.txt']['capture']=='private-text' and b'another-person' not in e.canonical(priv)
        assert priv['files']['result/first-failure.txt']['public_traceback_lines'][0]=={'text':'Actual failed output descriptor\n'}
        shutil.rmtree(wall)
        for suffix in ('err','out','exit'):(log/('score.'+suffix)).unlink()
        put(log/'admit.exit',b'1');decline=b'AssertionError: synthetic insufficient disk\n';put(root/'early-scheduler-wall-admission-v3c.failure',decline)
        rejected=v.terminal_report(e.capture(root),PROTOCOL,priors,b.bind_external({'catalog':pins['catalog'],'admission':None,'h2':None},stock,None))
        assert rejected['terminal']=='admission-failed' and rejected['statistics'] is None and rejected['observed_clocks']==0
        # Reserved domains and a scheme-only proxy header exercise refusal without storing credentials.
        for foreign in (b'https://reader@example.invalid/resource',b'/path/registry/src/mirror.example.invalid-abc/file',b'/home/new-user/private/',b'/Users/someuser/file',b'/arbitrary-team-root/sensitive/file.rs',b'file:///nonstandard/sensitive/path',
                        b'https://example.invalid/path',b'Proxy-Authorization: Basic',b'/mnt/devbox-scratch/another/inputs'):
            assert e.safe(foreign) is None
        assert e.safe(b'https://github.com/astral-sh/ohm-cargo/pull/260') is not None and not tried
    return dict(generated_only=True,synthetic_complete_pairs=24,synthetic_slots=48,synthetic_workspace_comparisons=2640,stock_native_occurrences=297,
        separate_reconstructions=2,physical_H2_exits_and_verified_mtime_checked=True,root_reread_all_53_byte_outputs_and_9867_processes_checked=True,synthetic_retained_occurrences=50,retained_width_pairs=800,physical_partitions_and_reused_refs_tested=True,synthetic_stock_pid_rows=9867,per_recipe_widths=16,source_file_gates_and_verifier_replayed=True,
        complete_original_statistic_and_CI_reproduced=True,admission_stop_no_clocks=True,late_verify_stop_no_effect=True,partial_score_stop_no_effect=True,
        first_exception_and_188_failed_state_files_preserved=True,foreign_path_digest_only=True,independent_publication_and_CI_tampering_rejected=True,
        both_stopped_native_traces_required=True,bootstrap_identity_and_original_verifier_required=True,missing_or_different_independent_H2_terminal_rejected=True,wrong_physical_exec_and_unregistered_raw_rejected=True,old_wall_reads=0,current_host_or_compiler_executions=0)
if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
