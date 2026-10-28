"""Generate a local operator transaction, including the two independently issued signals."""
import ast
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE=Path(__file__).resolve().parent
PLAN_NAME='rc17-composed-early-wall-plan-v3c'
REG='f8ee28c60e872a090b4600f473b303738be05029'
PLAN_SHA='fdec44bb8406ac845ddb1459377c9f92d3dac6bf06b925f6a685443f863a3e25'
H2='44c3e6db80242b5461bbb3f86f2fae5a0f166a45'
H5='charlie-ohm-c5-check-1025'
MANAGER='acf1088fd8dab3b2c06f6be9b6ed35c2f0c3649b8a9a2b671b5f5d1e0ec2c614'
def h(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(p.read_bytes())
def put(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    p.write_bytes(raw)
    return raw
def should_fail(fn):
    try:fn()
    except (AssertionError,KeyError,FileNotFoundError,ValueError):return
    raise AssertionError('an altered example passed')
def archive(source):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as f:
        for file in sorted(source.iterdir()):f.add(file,arcname=file.name,recursive=False)
    return out.getvalue()
def fake_plan_code(path,name):
    root=ast.parse(path.read_text());n=next(t for t in root.body if getattr(t,'name',None)==name)
    return ast.get_source_segment(path.read_text(),n)
def checked_seal(ops,fixtures):
    """Exercise the real sealing branch on invented file identities and original CI schema."""
    script=ops/'prepare-wall-v3c.py';tree=ast.parse(script.read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="mode == 'seal'")
    body=compile(ast.fix_missing_locations(ast.Module(body=node.body,type_ignores=[])),str(script),'exec')
    plan=fixtures/PLAN_NAME;sys.path.insert(0,str(plan))
    import catalog,bootstrap_lineage,continuation
    study=read(plan/'plan.json');ci=read(plan/'ci-exact-heads.json')
    with tempfile.TemporaryDirectory(prefix='synthetic-h5-seal-') as d:
        root=Path(d);here=root/'ops';here.mkdir();ref=REG;digest=PLAN_SHA
        native_result='6'*40
        names=dict(catalog_result_component='generated-native',catalog_result_ref=native_result,root_witness_file='actual-root-review.json',independent_verifier_file='actual.json',bootstrap_ref=bootstrap_lineage.BOOT,bootstrap_manifest=bootstrap_lineage.BOOT_MANIFEST)
        registration=dict(continuation.HISTORICAL,bootstrap_ref=bootstrap_lineage.BOOT,bootstrap_sha256=bootstrap_lineage.BOOT_MANIFEST)
        def raw(v):return (json.dumps(v,sort_keys=True,indent=4)+'\n\n').encode()
        cat={'catalog_result_ref':native_result,'plan_ref':ref}
        hashes=dict(view_sha256='1'*64,terminal_sha256='2'*64,verifier_receipt_sha256='3'*64)
        extra={'root-native-witness.json':raw(dict(independent_review='accepted',**hashes)),'bootstrap-completion.json':raw(dict(registration,whole_native_view_sha256=hashes['view_sha256'],startup_snapshot_binding=bootstrap_lineage.STARTUP_SHA,completed_original_verifier_sha256=bootstrap_lineage.VERIFIER)),
             'bootstrap-registration.json':raw(registration),'native-registration.json':raw(continuation.HISTORICAL),'host-reviewed-hashes.json':raw(hashes),'native-verifier.json':raw({'accepted':True}),'bootstrap-source-SHA256SUMS':(fixtures/'rc17-composed-all-links-bootstrap/SHA256SUMS').read_bytes()}
        digestset=lambda src:{k:{'bytes_b64':base64.b64encode(v).decode(),'sha256':h(v)} for k,v in src.items()}
        frozen={'ci.json':raw(ci),'catalog-publication.json':raw(cat),'provenance.json':raw(names),**extra}
        rec=dict(ci_sha256=h(frozen['ci.json']),catalog_publication_sha256=h(frozen['catalog-publication.json']))
        certificate=dict(fresh_occurrences=297,historical_occurrences=297,linked_targets=50,exact_others=60,widths=list(range(1,17)),plan_ref=ref,ci_sha256=rec['ci_sha256'],registered_catalog_sha256=rec['catalog_publication_sha256'],
            catalog_result_ref=native_result,catalog_protocol_ref=bootstrap_lineage.BOOT,v3b_wall_ref=bootstrap_lineage.WALL_B,v3b_wall_manifest=bootstrap_lineage.WALL_B_MANIFEST,native_bootstrap_ref=bootstrap_lineage.BOOT,native_bootstrap_manifest=bootstrap_lineage.BOOT_MANIFEST,original_native_verifier_sha256=bootstrap_lineage.VERIFIER,
            retained_occurrences=50,new_occurrences=249,retained_width_pairs=800,bootstrap_completion_sha256=h(extra['bootstrap-completion.json']),bootstrap_registration_sha256=h(extra['bootstrap-registration.json']))
        admission=dict(scored_commands=0,worker_manifest=digest,copy='never',fs='ext4',qa_sha256=study['composed_ci']['qa_sha256'],ci_status='pass',seed=dict(unique_file_bytes=13000000000,objects=50000),
                       native=dict(subjects=study['subject_images'],allowed={str(k):[] for k in range(110)},registry={str(k):'0'*64 for k in range(78)},registry_sha256='508c6cee5b0f1962ab784ffbd953dc3b06699f51663633cb279d4e1bb4131d53',native_catalog=certificate))
        frozen['admission.json']=put(here/'wall-v3c-admission.json',raw(admission))
        material=digestset(frozen)
        put(here/'wall-v3c-admission-material.json',material)
        put(here/'wall-v3c-catalog-binding.json',dict(ci=ci,catalog=cat,proof=digestset(extra),provenance=names))
        put(here/'wall-v3c-bind-catalog.json',rec)
        key='rc17-composed-all-links-bootstrap'
        refs={key:bootstrap_lineage.BOOT,**{k:'9'*40 for k in ['rc17-composed-early-safety-results','rc17-composed-early-native-results','rc17-composed-early-wall-results']}}
        ns=dict(root=root,here=here,ref=ref,digest=digest,study=study,refs=refs,catalog_key=key,catalog=catalog,json=json,hashlib=hashlib,base64=base64,h=h,utc_receipts=lambda:ci,BOOT=bootstrap_lineage.BOOT,BOOT_MANIFEST=bootstrap_lineage.BOOT_MANIFEST,WALL_B=bootstrap_lineage.WALL_B,WALL_B_MANIFEST=bootstrap_lineage.WALL_B_MANIFEST,VERIFIER=bootstrap_lineage.VERIFIER,HISTORICAL=continuation.HISTORICAL)
        for name in ['sha','save','read','exact_ci','same_ci']:exec(fake_plan_code(script,name),ns)
        out=root/'rc17-composed-wall-admission-v3c'
        for name in ['ci.json','catalog-publication.json','root-native-witness.json','bootstrap-completion.json','admission.json']:
            corrupt=copy.deepcopy(material)
            modified=frozen[name]+b' '
            corrupt[name]={'bytes_b64':base64.b64encode(modified).decode(),'sha256':h(modified)}
            put(here/'wall-v3c-admission-material.json',corrupt);should_fail(lambda:exec(body,ns));assert not out.exists()
        put(here/'wall-v3c-admission-material.json',material)
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):exec(body,ns)
        assert all((out/k).read_bytes()==v for k,v in frozen.items())
        signed={name:val for val,name in (l.split('  ',1) for l in (out/'SHA256SUMS').read_text().splitlines())}
        assert all(signed[n]==h(v) for n,v in frozen.items()) and len(signed)==14

def tested_main(fixtures,codebase):
    checked_seal(codebase,fixtures)
    stage=codebase/'wall-h5-v3c.py';prep=codebase/'prepare-wall-v3c.py';route=codebase/'route-wall-v3c.py'
    original=fixtures/'rc17-composed-early-test-ops/wall-h5-v3.py'
    # The launch payload is a literal, including modes, line breaks, role return code and binary stdio.
    def literal(p):
        vals=[n.value for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('from pathlib import Path\nimport subprocess,sys')]
        assert len(vals)==1 and h(vals[0].encode())==MANAGER
        return vals[0]
    assert literal(original)==literal(stage)
    with tempfile.TemporaryDirectory(prefix='ohm-local-h5-operator-') as td:
        base=Path(td)/'synthetic-h5';base.mkdir();src=fixtures/PLAN_NAME
        for parent,ref in [('v3','390db41469e8784dca0268c6317ea4b58b2e51c2'),('v3b','18d39259d88610e634243199b707c5435a506d77')]:
            source=fixtures/('rc17-composed-early-wall-plan-'+parent);raw=(source/'SHA256SUMS').read_bytes();put(base/('wall-protocol-'+parent)/'SHA256SUMS',raw);put(base/('wall-launch-'+parent)/'binding.json',dict(ref=ref,sha256=h(raw)))
        host_program=stage.read_text().replace("Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')",repr(base))
        # No SSH, tmux, lock polling, clocks or package operations. Only source extraction and data transport.
        host_program=host_program.replace('from pathlib import Path','from pathlib import Path,PosixPath',1).replace("socket.gethostname() == 'charlie-ohm-c5-check-1025'","True")
        def host(mode,data=b''):return subprocess.run([sys.executable,'-IB','-c',host_program,mode,REG,PLAN_SHA],input=data,capture_output=True)
        payload=archive(src);bad=base/'early-scheduler-wall-rc17-v3b';bad.mkdir();assert host('install',payload).returncode!=0 and not (base/'wall-protocol-v3c').exists();bad.rmdir()
        installed=host('install',payload);assert installed.returncode==0,installed.stderr
        assert json.loads(installed.stdout)=={'files':46,'installed':REG} and host('install',payload).returncode!=0
        launch=base/'wall-launch-v3c';assert {p.name for p in launch.iterdir()}=={'binding.json'}
        # Use the actual role execution helper only to test refusal before subprocess.
        ns={'Path':Path,'launch':launch,'subprocess':None,'sys':sys,'ref':REG,'hashlib':hashlib,'json':json}
        for name in ('sha','check_manager','start'):exec(fake_plan_code(stage,name),ns)
        (launch/'verify.exit').write_text('0');should_fail(lambda:ns['start']('verify',[]));assert (launch/'job.py').read_text()==literal(original)
        assert not (launch/'verify.out').exists() and not (launch/'verify.err').exists();(launch/'verify.exit').unlink()
        raw_ci=(src/'ci-exact-heads.json').read_bytes();checks=json.loads(raw_ci)
        names={'root-native-witness.json','bootstrap-completion.json','bootstrap-registration.json','native-registration.json','host-reviewed-hashes.json','native-verifier.json','bootstrap-source-SHA256SUMS'}
        prereg={name:put(launch/'provenance'/name,{'example':name}) for name in names}
        put(launch/'provenance/provenance.json',{'source':'generated'})
        # Deliberately distinguish formatted JSON equality from the exact original H5 files.
        saved_ci=put(launch/'ci.json',raw_ci+b'\n')
        saved_catalog=put(launch/'catalog-publication.json',b'{ "generated" : true }\n')
        admission=put(base/'early-scheduler-wall-admission-v3c.json',b'{"scored_commands": 0,"native":{"allowed":[]}}\n')
        (launch/'admit.exit').write_text('1');assert host('admission').returncode!=0
        (launch/'admit.exit').write_text('0');wire=host('admission');assert wire.returncode==0,wire.stderr
        decoded={k:base64.b64decode(v['bytes_b64'],validate=True) for k,v in json.loads(wire.stdout).items()}
        assert len(decoded)==11 and decoded['admission.json']==admission and decoded['ci.json']==saved_ci and decoded['catalog-publication.json']==saved_catalog and all(decoded[k]==v for k,v in prereg.items())
        # Test the operator's independent H2 reader and authenticated source/commit mapping using actual function code.
        here=Path(td)/'ops';here.mkdir();put(here/'wall-v3c-admission.json',admission)
        sys.path.insert(0,str(fixtures/'rc17-composed-early-wall-export-v3c'));import sideproof
        hr='6'*40;key=sideproof.H2_RESULT;fixture=Path(td)/'published-h2';rawterm=put(fixture/'terminal.json',{'slots':48,'phase':'all_slots_finished'});rf={'rc17-text-size-first-selection-wall-plan':H2,key:hr}
        ns={'Path':Path,'hashlib':hashlib,'json':json,'re':__import__('re'),'time':time,'refs':rf,'here':here,'ref':REG,'h':h,
            'H2_RESULT':sideproof.H2_RESULT,'check_h2':sideproof.check_h2,'published':lambda k,n:(fixture/n).read_bytes() if rf[k]==hr else None}
        for name in ('sha','read','lane_gate','same_ci'):exec(fake_plan_code(prep,name),ns)
        a=now=time.time_ns()-1000000
        lane=dict(host='charlie-ohm-relink-b-1024',study='rc17-text-size-first-selection-wall-plan',study_ref=H2,terminal_ref=hr,terminal_component=key,terminal_file='terminal.json',
           terminal_sha256=h(rawterm),status='complete',score_exit=0,ended_unix_ns=now-5,released_unix_ns=now,released_for=REG,admission_sha256=h(admission),scored_processes_running=0,owner_review='released by H2 operator after terminal')
        inp=here/'lane.json'
        def verify_lane(obj):put(inp,obj);return ns['lane_gate'](inp)
        def physical(value,verified=None):
            roles={'admit':0,'score':value['score_exit'],'verify':0}
            return {'kind':'result','registration':{'wall_ref':H2},'role_exits':roles,'role_logs':{k:{'exit':h(str(v).encode()),'out':h(b''),'err':h(b'')} for k,v in roles.items()},'terminal_file':value['terminal_file'],'terminal_sha256':value['terminal_sha256'],'ended_unix_ns':value['ended_unix_ns'],'verified_unix_ns':verified or now-1}
        put(fixture/'host-receipts.json',physical(lane));assert verify_lane(lane)==lane;assert ns['same_ci'](checks,list(reversed(checks)))
        changed=copy.deepcopy(checks);changed[0]['head']='0'*40;assert not ns['same_ci'](checks,changed)
        for key1,value in [('owner_review','implicit release'),('released_for','f'*40),('ended_unix_ns',now+1),('released_unix_ns',now+10**12),('terminal_sha256','0'*64),('terminal_ref',H2),('study_ref','9'*40),('scored_processes_running',1),('admission_sha256','1'*64),('terminal_file','unpublished.json'),('status','running'),('score_exit',1)]:
            should_fail(lambda:verify_lane(lane|{key1:value}))
        should_fail(lambda:verify_lane({k:v for k,v in lane.items() if k!='owner_review'}))
        saved=rawterm;put(fixture/'terminal.json',{'phase':'running','slots':47});ln=lane|{'terminal_sha256':h((fixture/'terminal.json').read_bytes())};should_fail(lambda:verify_lane(ln));put(fixture/'terminal.json',saved)
        fail=put(fixture/'failure.txt',b'synthetic H2 stop after recorded terminal exception\n')
        stopped=lane|dict(status='failed',score_exit=1,terminal_file='failure.txt',terminal_sha256=h(fail));put(fixture/'host-receipts.json',physical(stopped));assert verify_lane(stopped)==stopped
        put(fixture/'host-receipts.json',physical(stopped,now+1));should_fail(lambda:verify_lane(stopped))
        should_fail(lambda:verify_lane(stopped|{'score_exit':0}))
        cmd=ast.parse(route.read_text());assert 'recheck-score' in [n.value for n in ast.walk(cmd) if isinstance(n,ast.Constant)]
        for p in (stage,route,prep):compile(p.read_text(),str(p),'exec')
    return dict(local_generated_only=True,remote_calls=0,scored_jobs=0,clock_files_opened=0,original_job_manager_sha256=MANAGER,source_only_installer_refused_reuse_and_previous_state=True,
        literal_11_launch_blobs_byte_identical=True,portable_admission_seal_rejects_five_semantically_equal_byte_changes=True,seal_authenticates_all_14_files=True,late_admission_read_refused=True,H2_completed_and_stopped_allowed_only_with_explicit_release=True,H2_wrong_or_missing_fields_rejected=16,changed_CI_head_rejected=True)
if __name__=='__main__':
    d=Path(sys.argv[1]).resolve();print(json.dumps(tested_main(d,HERE),sort_keys=True,indent=2))
