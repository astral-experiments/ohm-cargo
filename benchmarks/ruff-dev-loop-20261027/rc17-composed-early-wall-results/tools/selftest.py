"""Construct local synthetic receipts. No Cargo, Rust, Wild or H5 work is performed."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from export import capture, dig, canonical, file_sha, safe, V1_GIT, V1_WALL
from verify import check_packet, manifest, WALL, WALL_GIT, prior_native, native_check, bind_published_admission

HERE=Path(__file__).resolve().parent
PROTOCOL=Path(sys.argv[1]).resolve()
manifest(PROTOCOL,WALL)
sys.path.insert(0,str(PROTOCOL))
import guards as g
from analysis import evaluate
from verify_result import run as original_verifier


def put(f,value):
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_bytes(value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
    return file_sha(f)


def fixture(base):
    w=base/'early-scheduler-wall-rc17-v2';log=base/'wall-launch-v2';ph=base/'wall-protocol-v2';prep=base/'wall-qa-v1'
    for path in (w,log,prep):path.mkdir()
    shutil.copytree(PROTOCOL,ph)
    v1=base/'wall-protocol-v1';v1.mkdir()
    src=next(PROTOCOL.parent/n/'SHA256SUMS' for n in ('rc17-composed-early-wall-plan','rc17-composed-early-wall-proposal') if (PROTOCOL.parent/n/'SHA256SUMS').is_file())
    shutil.copyfile(src,v1/'SHA256SUMS')
    put(base/'wall-launch-v1/binding.json',json.dumps({'ref':V1_GIT,'sha256':V1_WALL}).encode());put(base/'wall-launch-v1/admit.exit',b'1');put(base/'wall-launch-v1/admit.stdout',b'')
    original=json.loads((PROTOCOL/'wall-v1-failure-receipt.json').read_bytes());trace=original['trace']
    put(base/'early-scheduler-wall-admission-v1.failure',trace.encode())
    # These collector-fixture bytes must match the independently recorded real source digest.
    header,rest=trace.split('\n',1);filename=rest.split('"')[1]
    se=(header+'\n'+f'  File "{filename}", line 229, in <module>\n    main()\n'+rest).encode()
    assert put(base/'wall-launch-v1/admit.stderr',se)==original['remote']['admit.stderr']
    put(log/'binding.json',{'ref':WALL_GIT,'sha256':WALL})
    can=base/'ruff-evaluation-v2/canonical';root=can/'target';files={str(root/str(i)):f'{i:064x}' for i in range(110)}
    exe=list(files)[:102];registry={str(root/('registry'+str(i))):f'{i:064x}' for i in range(78)}
    events=[dict(reason='compiler-artifact',fresh=i<563,executable=str(root/str(i)) if i<102 else None,filenames=[str(root/str(i))],
               package_id='path+file:///ruff#x' if i<110 else 'registry+x',manifest_path='/canonical/ruff/Cargo.toml',
               target={'kind':['test']},profile={'test':i<84},features=[]) for i in range(619)]
    from export import SCHEMA
    encoded=[json.dumps({k:r[k] for k in SCHEMA},sort_keys=True) for r in events]
    rows={dig(s.encode()):{'owner':'workspace' if i<110 else 'registry','executable':str(Path('target')/str(i)) if i<102 else None,'test':i<84} for i,s in enumerate(encoded)}
    diag=[];bytes_listing=b'one: test\n';listing=dig(bytes_listing)
    counts={'full':1,'wild':1}
    procs=[dict(kind=k,target=t,exit=0,argv=[k],pid='exec.'+str(i),raw=dig(k.encode()),exe='/path/to/'+k) for i,(k,t) in enumerate([('full','ron'),('wild',exe[0])],1)]
    products=dict(units=619, fresh=563,roster=g.digest(sorted(encoded)),exes=exe,diagnostics=diag,ty_server={'fresh':True},e2e=exe[:1],native=files,counts=counts)
    variant=put(base/'wall-native-proofs/variants.json',{})
    stats={phase+'-'+role:counts for phase in ('selected','repeat') for role in ('observer','composed')}
    m=dict(subjects=g.P['subject_images'],allowed={k:[v] for k,v in files.items()},roster=g.summary(products),
           repeat_roster=g.digest(sorted(g.row_roster(procs).items())),listing_sha256=listing,registry=registry,registry_sha256=g.digest(registry),
           variants_sha256=variant,source_plan=g.P['native_manifest'],stats=stats,files={})
    gate_sha=put(base/'wall-native-proofs/frozen-native-guard.json',m)
    simple={'rows':rows,'workspace':{str(Path(k).relative_to(can)):h for k,h in files.items()},'registry':{str(Path(k).relative_to(can)):h for k,h in registry.items()},
            'fresh':563,'diagnostics':[],'receipt_sha256':{}}
    native=({'canonical':str(can),'steps':{tag:simple for tag in stats}}, {'targets':{},'native_variant_manifest_sha256':variant},
            {'subjects':m['subjects'],'typed_roster':m['roster'],'listing_sha256':listing,'counts':stats,'native_protocol':m['source_plan'],
             'variants_sha256':variant,'registry_sha256':m['registry_sha256'],'native_gate_sha256':gate_sha})
    shutil.copytree(PROTOCOL.parent/'rc17-composed-early-safety-results',prep,dirs_exist_ok=True)
    qa_sha=file_sha(prep/'qa.json');adm=base/'early-scheduler-wall-admission-v2.json';seed='a'*64
    ad=put(adm,dict(native=m,worker_manifest=WALL,qa_sha256=qa_sha,ci_status='pass',scored_commands=0,fs='ext4',copy='never',seed={'digest':seed,'unique_file_bytes':1},pessimistic_full_copy_bytes_all_48=48))
    # Copy the actual immutable native protocol manifests for their original whole-file hashes.
    for role,src in [('v2','rc17-composed-early-native-registry-plan'),('v3','rc17-composed-early-native-workspace-plan')]:
        d=base/('protocol-'+role);d.mkdir();shutil.copyfile(PROTOCOL.parent/src/'SHA256SUMS',d/'SHA256SUMS')
    grant=dict(go='score exact 24 pairs',native_sha256=ad,plan_manifest=WALL,published_plan=WALL_GIT,published_native='1'*40,h5_clear=True,other_host_measurement=False,ci_review='accepted')
    put(w/'grant.json',grant);put(log/'grant.json',grant)
    for stage in ('admit','score','verify'):
        for file in ('stdout','stderr','exit'):
            put(log/(stage+'.'+file),b'0' if file=='exit' else b'')
    standard=''.join(json.dumps(x)+'\n' for x in [*events,{'reason':'build-finished','success':True}]).encode();pairs=[];start=1
    for i,order in enumerate(g.P['order'],1):
        ns={}
        for pos,arm in enumerate(order,1):
            s=w/f'{i:02d}-{pos}-{arm}';o=s/'ordinary';f=s/'unchanged';ident=dict(block=i,slot=pos,arm=arm,image=m['subjects'][arm])
            put(s/'start.json',dict(**ident,native_binding=ad,copy='never',seed=seed,cpu=g.P['cpu']))
            dur=100 if arm=='B' else 65;ns[arm]=dur
            put(o/'clock.json',dict(argv=g.P['command'],start=start,stop=start+dur,elapsed_ns=dur,returncode=0));start+=dur+1
            put(o/'stdout',b'');put(o/'stderr',b'Finished\n');put(o/'e2e-list',bytes_listing);put(o/'e2e-list.stderr',b'')
            hx=put(s/'first-110.json',files);hr=put(s/'first-78-registry.json',registry)
            put(f/'stdout',standard);put(f/'stderr',b'');put(f/'products.json',products);put(f/'physical.json',procs);put(f/'registry-native.json',registry);put(f/'e2e-list',bytes_listing)
            put(f/'command.json',dict(arm=g.P['subjects'][arm],binary=m['subjects'][arm],code=0,edited=True,traced=True,command=g.P['command']+['--message-format=json']))
            for j in procs:put(f/'trace'/j['pid'],j['kind'].encode())
            put(s/'verified.json',dict(**ident,elapsed_ns=dur,registry_78=hr,first_110=hx,follow_110=g.digest(files),follow_roster=m['roster'],
                                      follow_counts=counts,follow_fresh=563,stdout=dig(b''),stderr=dig(b'Finished\n'),e2e_list=listing,diagnostics={}))
        pairs.append(dict(block=i,order=order,ns=ns,matching_raw=110,raw_differences={}))
    rh=put(w/'pairs.json',pairs);oh=put(w/'result.json',evaluate(g.P,pairs))
    put(w/'complete.json',dict(pairs=24,slots=48,admission=ad,plan=WALL,rows=rh,analysis=oh))
    exact=original_verifier(w,adm);put(log/'verify.stdout',exact)
    return w,log,native


def rejected(call):
    try:call()
    except (ValueError,AssertionError,KeyError):return
    raise RuntimeError('unexpected acceptance')


def test():
    with tempfile.TemporaryDirectory(prefix='h5-export-selftest-') as td:
        base=Path(td);w,log,native=fixture(base)
        complete=capture(base);v=check_packet(complete,PROTOCOL,native)
        # A synthetic complete series exercises the algorithm yet cannot be accepted as an actual H5 admission.
        rejected(lambda:bind_published_admission(complete))
        real_path=PROTOCOL.parent/'rc17-composed-wall-admission-v2/admission.json'
        assert file_sha(real_path)=='329818680f8d76f26cf15f6c4c5007c69001f6e85bd873c659a7bea283f6177e'
        actual=native_check(json.loads(real_path.read_bytes()),*prior_native(PROTOCOL.parent/'rc17-composed-early-native-results'))
        assert len(actual['allowed'])==110 and len(actual['registry'])==78 and len(actual['subjects'])==2
        assert v['qualified'] and v['observed_clocks']==48 and abs(v['statistics']['paired_reduction_pct']-35)<1e-10
        bad=copy.deepcopy(complete);bad['slots']['01-1-B']['jobs'][0]['kind']='wild'
        rejected(lambda:check_packet(bad,PROTOCOL,native))
        bad=copy.deepcopy(complete);bad['bodies'][bad['files']['01-1-B/ordinary/stderr']['sha256']]+='x'
        rejected(lambda:check_packet(bad,PROTOCOL,native))
        put(log/'verify.exit',b'1');put(log/'verify.stderr',b'AssertionError: unexpected raw output\n')
        terminal=check_packet(capture(base),PROTOCOL,native)
        assert terminal['terminal']=='verify-failed' and terminal['statistics'] is None
        for f in ('exit','stdout','stderr'):(log/('verify.'+f)).unlink()
        rejected(lambda:capture(base))
        put(log/'score.exit',b'1');exc=b'ValueError: Unadmitted raw ELF hashes: {"target": "changed"}\n';put(log/'score.stderr',exc);put(w/'first-failure.txt',exc)
        for f in w.iterdir():
            if f.is_dir() and f.name not in ('01-1-B','01-2-C','02-1-C'):shutil.rmtree(f)
        for f in ('result.json','complete.json'):(w/f).unlink()
        put(w/'pairs.json',json.loads((w/'pairs.json').read_bytes())[:1])
        f=w/'02-1-C';(f/'verified.json').unlink();shutil.rmtree(f/'unchanged');(f/'private-state').mkdir()
        raw=json.loads((f/'first-110.json').read_bytes());key=next(iter(raw));raw[key]='e'*64;put(f/'first-110.json',raw)
        aborted=capture(base);r=check_packet(aborted,PROTOCOL,native)
        assert r['failed_slot_products']['02-1-C']['first_workspace']['unadmitted']=={key:'e'*64}
        assert r['observed_clocks']==3 and r['verified_slots']==2 and r['complete_pair_checkpoints']==1 and r['statistics'] is None
        assert r['retained_private_states']==['02-1-C'] and r['exceptions']['result/first-failure.txt']==dig(exc)
        assert len(aborted['slots']['02-1-C']['terminal_retained_outputs'])==188
        changed=copy.deepcopy(aborted);changed['slots']['06-2-B']=changed['slots'].pop('02-1-C')
        rejected(lambda:check_packet(changed,PROTOCOL,native))
        shutil.rmtree(w)
        for f in ('exit','stdout','stderr'):(log/('score.'+f)).unlink()
        put(log/'admit.exit',b'1');put(base/'early-scheduler-wall-admission-v2.failure',b'AssertionError: no space\n')
        result=check_packet(capture(base),PROTOCOL,native);assert result['terminal']=='admission-failed' and result['statistics'] is None
        for bad in (b'https://user:'+b'password@example.com',b'git'+b'hub_pat_'+b'A'*32,b'gh'+b'p_'+b'B'*24,b'artifact'+b'ory.example',b'example.'+b'openai'+b'.org',b'authori'+b'zation: '+b'bearer '+b'a'*12):
            assert safe(bad) is None
        assert safe(b'timestamps, ordinary Cargo timing and a public package name') is not None
    return {'entire_native_authority_and_portable_clocks':48,'synthetic_speedup_pct':35,'failed_after_clocks':3,'failed_complete_slots':2,
            'first_failure_retained':True,'missing_and_corrupt_receipts_are_never_a_complete_trial':True,
            'pending_trial_refused':True,'admission_and_final_native_failures_preserved':True,'real_published_admission_checked':True,'synthetic_admission_cannot_be_reported_as_real':True,'six_redaction_probes_and_public_control':True,'actual_remote_or_cargo_commands':0}


if __name__=='__main__':print(json.dumps(test(),indent=2,sort_keys=True))
