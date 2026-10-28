"""Bind the current private PR heads, published native receipts, and new zero-clock admission."""
import base64
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

here=Path(__file__).resolve().parent
root=here.parent
repo=Path('/home/dev-user/code/oss/ohm-finished-early-test-20261027')
evidence=Path('/home/dev-user/code/oss/ohm-ruff-whole-extern-skip-20261027')
gh='/home/dev-user/.local/bin/gh-auto'
key='rc17-composed-early-wall-plan-v3c'
packet=root/key
mode=sys.argv[1]
assert mode in ('catalog','seal','grant','recheck-score')

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(p):
    return json.loads(p.read_bytes())

def save(p,v):
    with p.open('x') as f:
        json.dump(v,f,sort_keys=True,indent=2)
        f.write('\n')

def run(cwd,*args):
    return subprocess.check_output(args,cwd=cwd)

def utc_receipts():
    assert run(repo,gh,'api','user','--jq','.login').strip()==b'charliermarsh'
    out=[]
    for role in ('observer','composed'):
        s=study['composed_ci'][role]
        row=json.loads(run(repo,gh,'pr','view',str(s['number']),'--json','number,url,state,isDraft,headRefOid,baseRefName,statusCheckRollup'))
        assert row['headRefOid']==s['head'] and row['isDraft'] and row['state']=='OPEN'
        if role=='composed':
            assert row['baseRefName']=='charlie/ohm-require-consumed-observer-inputs-20261028'
        out.append({'number':row['number'],'url':row['url'],'head':row['headRefOid'],
                    'checks':[{k:c[k] for k in ('name','status','conclusion','detailsUrl')} for c in row['statusCheckRollup']]})
    catalog.check_ci(study,out)
    return out

def archived(component,name):
    assert re.fullmatch(r'[a-zA-Z0-9_.-]+',component) and not Path(name).is_absolute() and '..' not in Path(name).parts
    commit=refs[component]
    assert re.fullmatch('[a-f0-9]{40}',commit)
    return run(evidence,'git','show',f'{commit}:benchmarks/ruff-dev-loop-20261027/{component}/{name}')

def same_ci(a,b):
    def flags(rows):
        return {r['number']:(r['head'],r['url'],sorted(tuple(c[k] for k in ('name','status','conclusion','detailsUrl')) for c in r['checks'])) for r in rows}
    return flags(a)==flags(b)

refs=read(root/'published-20261027-corrected-cohort-refs.json')
study=read(packet/'plan.json')
ref=refs[key]; digest=sha(packet/'SHA256SUMS')
assert archived(key,'SHA256SUMS')==(packet/'SHA256SUMS').read_bytes()
sys.path.insert(0,str(packet))
import catalog
sys.path.insert(0,str(root/'rc17-composed-early-wall-export-v3c'))
from sideproof import check_h2,check_native,H2_RESULT,NATIVE_READER

from bootstrap_lineage import BOOT,BOOT_MANIFEST,STARTUP_SHA,VERIFIER,WALL_B,WALL_B_MANIFEST
from continuation import HISTORICAL
assert ref=='f8ee28c60e872a090b4600f473b303738be05029' and digest=='fdec44bb8406ac845ddb1459377c9f92d3dac6bf06b925f6a685443f863a3e25'
catalog_key='rc17-composed-all-links-bootstrap';assert refs[catalog_key]==BOOT
h=lambda raw:hashlib.sha256(raw).hexdigest()

def published(component,name):
    manifest={n:v for v,n in (s.split('  ',1) for s in archived(component,'SHA256SUMS').decode().splitlines())}
    raw=archived(component,name);assert manifest[name]==h(raw);return raw

def b64(raw):return base64.b64encode(raw).decode('ascii')

def exact_ci(raw):
    rows=json.loads(raw);catalog.check_ci(study,rows);return rows

def lane_gate(path):
    lane=read(path)
    required={'study','study_ref','host','status','score_exit','terminal_component','terminal_ref','terminal_file','terminal_sha256','ended_unix_ns','released_unix_ns','released_for','admission_sha256','scored_processes_running','owner_review'}
    assert set(lane)==required and lane['host']=='charlie-ohm-relink-b-1024' and lane['study']=='rc17-text-size-first-selection-wall-plan'
    assert lane['study_ref']==refs[lane['study']]=='44c3e6db80242b5461bbb3f86f2fae5a0f166a45' and lane['terminal_ref']==refs[lane['terminal_component']] and lane['terminal_ref']!=lane['study_ref']
    assert lane['terminal_component']==H2_RESULT
    hraw=published(H2_RESULT,'host-receipts.json');state=check_h2(json.loads(hraw),lane['terminal_file'],lane['terminal_sha256'])
    assert (lane['score_exit'],lane['ended_unix_ns'])==state[:2] and lane['released_unix_ns']>=state[2]
    terminal=published(lane['terminal_component'],lane['terminal_file']);assert h(terminal)==lane['terminal_sha256'] and terminal
    if lane['status']=='complete':
        tt=json.loads(terminal);assert lane['score_exit']==0 and tt['phase']=='all_slots_finished' and tt['slots']==48
    else:
        assert lane['status']=='failed' and type(lane['score_exit']) is int and lane['score_exit']!=0 and Path(lane['terminal_file']).name=='failure.txt'
    assert 0<lane['ended_unix_ns']<=lane['released_unix_ns']<=time.time_ns() and lane['released_for']==ref and lane['admission_sha256']==sha(here/'wall-v3c-admission.json')
    assert lane['scored_processes_running']==0 and lane['owner_review']=='released by H2 operator after terminal'
    return lane

if mode=='catalog':
    cli=argparse.ArgumentParser();cli.add_argument('native_result');cli.add_argument('review_file');cli.add_argument('--verifier-file',default='independent.json');arg=cli.parse_args(sys.argv[2:])
    key0=arg.native_result;w=published(key0,arg.review_file);review=json.loads(w)
    raw={}
    for label,file in [('root-native-witness.json',arg.review_file),('bootstrap-completion.json','bootstrap-completion.json'),
         ('bootstrap-registration.json','bootstrap-registration.json'),('native-registration.json','continuation-registration.json'),
         ('host-reviewed-hashes.json','reviewed-hashes.json'),('native-verifier.json',arg.verifier_file)]:raw[label]=published(key0,file)
    raw['bootstrap-source-SHA256SUMS']=archived(catalog_key,'SHA256SUMS');assert h(raw['bootstrap-source-SHA256SUMS'])==BOOT_MANIFEST
    w0=json.loads(raw['host-reviewed-hashes.json']);reg=json.loads(raw['bootstrap-registration.json']);done=json.loads(raw['bootstrap-completion.json'])
    assert reg=={**HISTORICAL,'bootstrap_ref':BOOT,'bootstrap_sha256':BOOT_MANIFEST} and json.loads(raw['native-registration.json'])==HISTORICAL
    public_view=gzip.decompress(published(key0,'wall-view.json.gz'));view=json.loads(public_view);terminal=published(key0,'terminal.json')
    keys=('view_sha256','terminal_sha256','verifier_receipt_sha256');hashes=dict(zip(keys,map(h,(public_view,terminal,raw['native-verifier.json']))))
    assert done=={**reg,'whole_native_view_sha256':hashes['view_sha256'],'startup_snapshot_binding':STARTUP_SHA,'completed_original_verifier_sha256':VERIFIER}
    assert review['independent_review']=='accepted' and all(review[k]==w0[k]==v for k,v in hashes.items())
    assert (review['workspace_linked_targets'],review['fresh_occurrences'],review['registry_exact'],review['historical_native_ref'])==(50,297,78,study['catalog_scope']['native_reference'])
    assert (w0['catalog_protocol_ref'],w0['native_continuation_ref'],w0['native_bootstrap_ref'],w0['native_bootstrap_manifest'],w0['bootstrap_receipt_sha256'])==(HISTORICAL['original_ref'],HISTORICAL['continuation_ref'],BOOT,BOOT_MANIFEST,h(raw['bootstrap-completion.json']))
    assert h(published(key0,'root-native-reread.py'))==NATIVE_READER
    check_native(review,view,hashes)
    assert json.loads(raw['native-verifier.json'])['accepted'] is True and view['independent_verification']['sha256']==hashes['verifier_receipt_sha256']
    record=dict(plan_ref=ref,plan_manifest=digest,native_reference=study['catalog_scope']['native_reference'],catalog_protocol_ref=BOOT,catalog_result_ref=refs[key0],independent_review='accepted',**hashes)
    provenance={k:dict(bytes_b64=b64(v),sha256=h(v)) for k,v in raw.items()}
    names={'catalog_result_component':key0,'catalog_result_ref':refs[key0],'root_witness_file':arg.review_file,'reread_source_sha256':NATIVE_READER,'independent_verifier_file':arg.verifier_file,'bootstrap_ref':BOOT,'bootstrap_manifest':BOOT_MANIFEST}
    save(here/'wall-v3c-catalog-binding.json',dict(catalog=record,ci=utc_receipts(),proof=provenance,provenance=names));print('catalog',record['catalog_result_ref'])
elif mode=='seal':
    admission=here/'wall-v3c-admission.json';bound=read(admission)
    bindings=read(here/'wall-v3c-catalog-binding.json')
    recorded=read(here/'wall-v3c-bind-catalog.json')
    actual=utc_receipts();assert same_ci(actual,bindings['ci'])
    assert bound['scored_commands']==0 and bound['worker_manifest']==digest and bound['copy']=='never' and bound['fs']=='ext4'
    assert bound['qa_sha256']==study['composed_ci']['qa_sha256'] and bound['ci_status']=='pass'
    n=bound['native'];complete=n['native_catalog']
    assert n['subjects']==study['subject_images'] and len(n['allowed'])==110 and len(n['registry'])==78
    assert n['registry_sha256']=='508c6cee5b0f1962ab784ffbd953dc3b06699f51663633cb279d4e1bb4131d53'
    assert complete['fresh_occurrences']==complete['historical_occurrences']==297 and complete['linked_targets']==50 and complete['exact_others']==60
    assert complete['widths']==list(range(1,17)) and complete['plan_ref']==ref and complete['ci_sha256']==recorded['ci_sha256']
    assert complete['registered_catalog_sha256']==recorded['catalog_publication_sha256']
    assert bound['seed']['unique_file_bytes']>12_000_000_000 and bound['seed']['objects']>44000
    assert complete['catalog_result_ref']==bindings['catalog']['catalog_result_ref'] and complete['catalog_protocol_ref']==refs[catalog_key]
    assert (complete['v3b_wall_ref'],complete['v3b_wall_manifest'],complete['native_bootstrap_ref'],complete['native_bootstrap_manifest'],complete['original_native_verifier_sha256'])==(WALL_B,WALL_B_MANIFEST,BOOT,BOOT_MANIFEST,VERIFIER)
    assert complete['retained_occurrences']==50 and complete['new_occurrences']==249 and complete['retained_width_pairs']==800
    collected=read(here/'wall-v3c-admission-material.json'); wire={k:base64.b64decode(node['bytes_b64'],validate=True) for k,node in collected.items()}
    assert set(wire)=={'admission.json','catalog-publication.json','ci.json','provenance.json',*bindings['proof']}
    assert all(h(v)==collected[k]['sha256'] for k,v in wire.items()) and wire['admission.json']==admission.read_bytes()
    assert h(wire['ci.json'])==recorded['ci_sha256'] and h(wire['catalog-publication.json'])==recorded['catalog_publication_sha256']
    assert json.loads(wire['provenance.json'])==bindings['provenance'] and all(h(wire[k])==item['sha256'] for k,item in bindings['proof'].items())
    assert complete['bootstrap_completion_sha256']==h(wire['bootstrap-completion.json']) and complete['bootstrap_registration_sha256']==h(wire['bootstrap-registration.json'])
    assert same_ci(exact_ci(wire['ci.json']),actual) and json.loads(wire['catalog-publication.json'])==bindings['catalog']
    out=root/'rc17-composed-wall-admission-v3c';out.mkdir()
    for k,v in wire.items():
        with (out/k).open('xb') as f:f.write(v)

    reginfo=bindings['provenance'];save(out/'checked-ci.json',actual)
    save(out/'source-bindings.json',dict(registered_plan=ref,plan_sha256=digest,admission_sha256=sha(admission),catalog=bindings['catalog'],
         verified_host_witnesses=recorded,safety=refs['rc17-composed-early-safety-results'],original_native=refs['rc17-composed-early-native-results'],
         bootstrap=reginfo,stopped_native=HISTORICAL['stopped_evidence_ref'],original_wall='390db41469e8784dca0268c6317ea4b58b2e51c2',v3b=WALL_B,stopped_timing=refs['rc17-composed-early-wall-results']))
    (out/'README.md').write_text(
        '# Native admission for the Ruff test-build comparison\n\n'
        'Before starting any clock, H5 verified both Cargo executables, the independent seed, the current draft heads and their eight passing CI jobs. '
        'The conditional APFS job was skipped on each head. The two binaries compile the same Ruff source with the shipped Ohm compiler and linker. '
        'The scheduler change removes one duplicate compiler invocation and link when first selecting the whole workspace.\n\n'
        'The verifier checked six native command rosters covering 297 linker invocations. For the 50 workspace outputs they link, the catalog admits only '
        'whole-file SHA-256 values reproduced by stock Wild with the original operands at explicit worker counts. The other 60 workspace outputs and all '
        '78 registry outputs retain a single required digest each. Both previously rejected digests were reproduced. The earlier four clock readings stay '
        'excluded. This packet contains zero replacement timings.\n\n'
        'The verified host record is in admission.json. The immutable source and result commits are in source-bindings.json.\n')
    (out/'SHA256SUMS').write_text(''.join(f'{sha(f)}  {f.name}\n' for f in sorted(out.iterdir())))
    print('manifest',sha(out/'SHA256SUMS'),'admission',sha(admission))
else:
    assert mode in ('grant','recheck-score')
    admission=here/'wall-v3c-admission.json'; frozen=read(admission);native=frozen['native']['native_catalog']
    idle=read(here/'wall-v3c-idle.json');approval=read(here/'wall-v3c-lanes.json')
    h2path=here/'wall-v3c-h2-released.json';h2=lane_gate(h2path)
    assert idle['lock_clear'] and idle['no_compilers'] and idle['study_sessions']==idle['scored_commands']==0
    assert idle['admission']==sha(admission) and 0 <= time.time_ns()-idle['unix_ns'] < 180*10**9
    assert approval['host']=='charlie-ohm-c5-check-1025' and approval['other_scored_processes']==0 and approval['owner_review']
    assert 0 <= time.time_ns()-approval['unix_ns'] < 180*10**9
    current=utc_receipts();assert same_ci(current,read(here/'wall-v3c-catalog-binding.json')['ci'])
    assert 0<=time.time_ns()-approval['unix_ns']<180*10**9
    assert approval['admission_sha256']==sha(admission) and approval['h2_release_sha256']==sha(h2path)
    assert approval['unix_ns']>=h2['released_unix_ns']
    key_ad='rc17-composed-wall-admission-v3c';local_ad=root/key_ad
    assert archived(key_ad,'SHA256SUMS')==(local_ad/'SHA256SUMS').read_bytes()
    for row in (local_ad/'SHA256SUMS').read_text().splitlines():
        _digest,name=row.split('  ',1);assert published(key_ad,name)==(local_ad/name).read_bytes()
    assert (local_ad/'admission.json').read_bytes()==admission.read_bytes()
    assert native['plan_ref']==ref and frozen['worker_manifest']==digest
    pub=dict(plan_ref=ref,catalog_ref=native['catalog_result_ref'],admission_ref=refs['rc17-composed-wall-admission-v3c'],plan_manifest=digest,
             admission_sha256=sha(admission),catalog_publication_sha256=native['registered_catalog_sha256'],ci_sha256=native['ci_sha256'])
    grant=dict(go='score exact v3c 24 fresh pairs',native_sha256=sha(admission),plan_manifest=digest,published_plan=ref,published_catalog=pub['catalog_ref'],
               published_native=pub['admission_ref'],ci_sha256=pub['ci_sha256'],h5_clear=True,other_host_measurement=False,ci_review='accepted')
    aux=dict(h2_physical=json.loads(published(H2_RESULT,'host-receipts.json')),h2_release=h2,h2_release_sha256=sha(h2path),h2_release_b64=b64(h2path.read_bytes()),fresh_ci=current,owner_approval=approval,idle=idle)
    score=here/'wall-v3c-score-binding.json'
    if mode=='grant':save(score,dict(publication=pub,grant=grant,aux=aux))
    else:
        checked=read(score);assert checked['publication']==pub and checked['grant']==grant
        previous=checked['aux'];assert same_ci(previous['fresh_ci'],current) and all(previous[k]==aux[k] for k in aux if k!='fresh_ci')
    print('ready',sha(here/'wall-v3c-score-binding.json'))
