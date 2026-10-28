"""Run the sealed #260 replacement study on its registered H5 host."""
from pathlib import Path
import base64
import fcntl
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time

base = Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
plan = base/'wall-protocol-v3c'
launch = base/'wall-launch-v3c'
result = base/'early-scheduler-wall-rc17-v3c'
admission = base/'early-scheduler-wall-admission-v3c.json'
mode, ref, digest = sys.argv[1:]
assert socket.gethostname() == 'charlie-ohm-c5-check-1025'
assert re.fullmatch('[0-9a-f]{40}',ref) and re.fullmatch('[0-9a-f]{64}',digest)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def save(path, value):
    with path.open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2)
        f.write('\n')

def predecessors():
    parents=[('v3', '390db41469e8784dca0268c6317ea4b58b2e51c2', '9099beedd4c6a180c1c5747c077d1a45e1868e922dc594031d5ac4a292bfc9c4'), ('v3b', '18d39259d88610e634243199b707c5435a506d77', '2db9f4a735f6ebaab6f86c77e5643d6a99dd00c7691d62de2bb1e168720ce3c8')]
    for name,commit,digest0 in parents:
        source=base/('wall-protocol-'+name);l=base/('wall-launch-'+name)
        assert not source.is_symlink() and not l.is_symlink() and sha(source/'SHA256SUMS')==digest0 and read(l/'binding.json')=={'ref':commit,'sha256':digest0}
        assert not any((base/n).exists() for n in ('early-scheduler-wall-rc17-'+name,'early-scheduler-wall-admission-'+name+'.json','early-scheduler-wall-admission-'+name+'.failure'))

def check_manager(manager):
    assert manager.is_file() and not manager.is_symlink() and sha(manager)=='acf1088fd8dab3b2c06f6be9b6ed35c2f0c3649b8a9a2b671b5f5d1e0ec2c614'

def blob(path):
    assert path.is_file() and not path.is_symlink();raw=path.read_bytes()
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes_b64':base64.b64encode(raw).decode('ascii')}


def same_ci(a,b):
    return {r['number']:(r['head'],r['url'],sorted(tuple(c[k] for k in ('name','status','conclusion','detailsUrl')) for c in r['checks'])) for r in a}=={r['number']:(r['head'],r['url'],sorted(tuple(c[k] for k in ('name','status','conclusion','detailsUrl')) for c in r['checks'])) for r in b}

def start(role, args):
    manager = launch/'job.py'
    if not manager.exists():
        with manager.open('x') as f:
            f.write("from pathlib import Path\nimport subprocess,sys\np=Path(sys.argv[1]);role=sys.argv[2]\nwith (p/(role+'.out')).open('xb') as so, (p/(role+'.err')).open('xb') as se:\n rc=subprocess.run([sys.executable,'-IB',*sys.argv[3:]],stdout=so,stderr=se).returncode\nwith (p/(role+'.exit')).open('x') as f: f.write(str(rc))\n")
    check_manager(manager)
    assert not any((launch/(role+s)).exists() for s in ('.out','.err','.exit'))
    cmd = shlex.join([sys.executable,'-IB',str(manager),str(launch),role,*map(str,args)])
    subprocess.run(['tmux','new-session','-d','-s','ohm-wall-v3c-'+role,cmd],check=True)
    print(json.dumps({'started':role,'ref':ref}))

binding = dict(ref=ref,sha256=digest)
if mode=='install':
    predecessors()
    assert not admission.with_suffix('.failure').exists()
    assert not any(p.exists() for p in (plan,launch,result,admission))
    archive = sys.stdin.buffer.read(1024*1024+1)
    assert 0 < len(archive) <= 1024*1024
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as bundle:
        members=bundle.getmembers()
        assert 10 < len(members) < 150 and len({m.name for m in members})==len(members)
        assert all(m.isfile() and Path(m.name).name==m.name and m.size < 655360 for m in members)
        plan.mkdir(mode=0o700)
        bundle.extractall(plan,filter='data')
    assert sha(plan/'SHA256SUMS') == digest
    names = {line.split('  ',1)[1] for line in (plan/'SHA256SUMS').read_text().splitlines()}
    assert names|{'SHA256SUMS'} == {p.name for p in plan.iterdir()}
    subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=plan,check=True)
    launch.mkdir(mode=0o700)
    save(launch/'binding.json',binding)
    print(json.dumps({'installed':ref,'files':len(names)+1}))
    sys.exit()

predecessors()
assert read(launch/'binding.json') == binding and sha(plan/'SHA256SUMS') == digest
if mode == 'status':
    status = {'free_gib':round(shutil.disk_usage(base).free/2**30,1),
              'catalog_bound':(launch/'catalog-publication.json').is_file(),
              'admission':sha(admission) if admission.is_file() else None,
              'slots_with_clocks':len(list(result.glob('*/ordinary/clock.json'))),
              'verified_slots':len(list(result.glob('*/verified.json'))),
              'complete':(result/'complete.json').is_file()}
    for role in ('admit','score','verify'):
        rc = launch/(role+'.exit')
        status[role] = rc.read_text() if rc.exists() else None
    for label,path in [('admission_failure',admission.with_suffix('.failure')),('score_failure',result/'first-failure.txt')]:
        status[label] = path.read_text()[-1200:] if path.exists() else None
    print(json.dumps(status))
elif mode == 'bind-catalog':
    assert not result.exists() and not admission.exists()
    data = json.load(sys.stdin)
    expected = json.loads((plan/'plan.json').read_bytes())
    catalog = data['catalog']
    assert (catalog['plan_ref'],catalog['plan_manifest']) == (ref,digest)
    assert catalog['native_reference']==expected['catalog_scope']['native_reference'] and catalog['independent_review']=='accepted'
    for file,k in [('wall-view.json','view_sha256'),('terminal.json','terminal_sha256')]:
        assert sha(base/'whole-wild-width-v2'/file)==catalog[k]
    view=read(base/'whole-wild-width-v2'/'wall-view.json')
    verified=view['independent_verification']
    proof=(base/'whole-wild-width-v2'/verified['file']).resolve()
    assert proof.is_relative_to((base/'whole-wild-width-v2').resolve())
    assert sha(proof)==verified['sha256']==catalog['verifier_receipt_sha256']
    sys.path.insert(0,str(plan))
    from catalog import check_ci
    check_ci(expected,data['ci'])
    sys.path.insert(0,str(plan));import bootstrap_lineage as bs
    from continuation import HISTORICAL
    import guards
    assert catalog['catalog_protocol_ref']==bs.BOOT and data['provenance']['bootstrap_ref']==bs.BOOT and data['provenance']['bootstrap_manifest']==bs.BOOT_MANIFEST
    assert data['provenance']['catalog_result_ref']==catalog['catalog_result_ref']
    proof=data['proof'];names={'root-native-witness.json','bootstrap-completion.json','bootstrap-registration.json','native-registration.json','host-reviewed-hashes.json','native-verifier.json','bootstrap-source-SHA256SUMS'}
    assert set(proof)==names
    material={k:base64.b64decode(node['bytes_b64'],validate=True) for k,node in proof.items()}
    assert all(hashlib.sha256(raw).hexdigest()==proof[k]['sha256'] and len(raw)<=2**20 for k,raw in material.items())
    boot=base/'whole-wild-width-v2-bootstrap';root=base/'whole-wild-width-v2';here_proof=bs.physical(guards,HISTORICAL)
    expected_sources={'bootstrap-completion.json':root/'bootstrap-completion.json','bootstrap-registration.json':boot/'registration.json',
        'native-registration.json':root/'continuation-registration.json','host-reviewed-hashes.json':root/'reviewed-hashes.json',
        'native-verifier.json':(root/view['independent_verification']['file']).resolve(),'bootstrap-source-SHA256SUMS':boot/'source/SHA256SUMS'}
    assert all(f.is_file() and not f.is_symlink() and sha(f)==proof[k]['sha256'] for k,f in expected_sources.items())
    assert here_proof['bootstrap_completion_sha256']==proof['bootstrap-completion.json']['sha256']
    witness=json.loads(material['root-native-witness.json']);assert witness['independent_review']=='accepted' and (witness['workspace_linked_targets'],witness['fresh_occurrences'],witness['registry_exact'])==(50,297,78)
    assert all(witness[k]==catalog[k] for k in ('view_sha256','terminal_sha256','verifier_receipt_sha256'))
    output={j['evidence']['file']:j['evidence']['sha256'] for j in view['targets'].values()}
    assert len(output)==50 and data['provenance']['reread_source_sha256']=='ec0d86f448c442168b7407fff3814a9b1cdfe05d26b77795f7c80467f191b758'
    output.update({'wall-view.json':catalog['view_sha256'],'terminal.json':catalog['terminal_sha256'],'independent.json':catalog['verifier_receipt_sha256']})
    assert witness['byte_recomputed_outputs']==output and (witness['reopened_unique_stock_processes'],witness['explicit_processes'],witness['ordinary_controls'])==(9867,9568,299)
    assert witness['read_only'] is True and witness['counted_clocks']==0 and witness['original_verifier_sha256']==bs.VERIFIER
    assert not any((launch/n).exists() for n in ('ci.json','catalog-publication.json'))
    archive=launch/'provenance';archive.mkdir(mode=0o700)
    for name,raw in material.items():
        with (archive/name).open('xb') as f:f.write(raw)
    save(archive/'provenance.json',data['provenance'])
    save(launch/'ci.json',data['ci'])
    save(launch/'catalog-publication.json',catalog)
    print(json.dumps({'ci_sha256':sha(launch/'ci.json'),'catalog_publication_sha256':sha(launch/'catalog-publication.json')}))
elif mode == 'admit':
    assert not admission.exists() and not result.exists() and (launch/'catalog-publication.json').is_file()
    start('admit',[plan/'runner.py','admit',base/'wall-qa-v1'/'qa.json'])
elif mode == 'admission':
    assert (launch/'admit.exit').read_text()=='0' and read(admission)['scored_commands']==0
    sources={'admission.json':admission,'ci.json':launch/'ci.json','catalog-publication.json':launch/'catalog-publication.json'}
    p=launch/'provenance';assert p.is_dir() and not p.is_symlink()
    for item in p.iterdir():assert item.name not in sources;sources[item.name]=item
    print(json.dumps({k:blob(f) for k,f in sources.items()},sort_keys=True))
elif mode in ('idle','score'):
    assert (launch/'admit.exit').read_text()=='0' and not result.exists()
    assert not any((launch/n).exists() for n in ('grant.json','score.exit','admission-publication.json'))
    check = {'cargo','rustc','wild','wild-ld','collect2','gcc','cc','ld','ld.bfd','ld.lld','rust-lld','clang','clang++','cc1','drrun','drconfig','valgrind','callgrind','ninja','cmake','rustup','llvm-profdata','hyperfine','strace','ld.gold','mold'}
    with (base/'combined-native-measure.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        active=[]
        for p in Path('/proc').glob('[0-9]*'):
            try:
                name=(p/'comm').read_text().strip()
                state=(p/'stat').read_text().rsplit(')',1)[1].split()[0]
            except (FileNotFoundError,PermissionError,ProcessLookupError):
                continue
            if name in check and state!='Z':
                active.append([p.name,name])
        assert not active,active
        sessions = subprocess.run(['tmux','list-sessions','-F','#{session_name}'],capture_output=True,text=True)
        assert sessions.returncode in (0,1) and not any('ohm-wall-v3c-' in n for n in sessions.stdout.splitlines())
    if mode=='idle':
        print(json.dumps({'unix_ns':time.time_ns(),'host':socket.gethostname(),'no_compilers':True,'lock_clear':True,'study_sessions':0,'admission':sha(admission),'scored_commands':0}))
    else:
        data=json.load(sys.stdin);public=data['publication'];grant=data['grant'];aux=data['aux']
        sys.path.insert(0,str(plan));from catalog import check_ci
        checks=aux['fresh_ci'];check_ci(read(plan/'plan.json'),checks);assert same_ci(checks,read(launch/'ci.json'))
        h2=aux['h2_release'];rd=base64.b64decode(aux['h2_release_b64'],validate=True);assert hashlib.sha256(rd).hexdigest()==aux['h2_release_sha256'] and json.loads(rd)==h2
        meta=aux['h2_physical']
        assert meta['kind']=='result' and meta['registration']['wall_ref']==h2['study_ref'] and meta['terminal_sha256']==h2['terminal_sha256'] and meta['terminal_file']==h2['terminal_file']
        assert meta['role_exits']=={'admit':0,'score':h2['score_exit'],'verify':0} and meta['ended_unix_ns']==h2['ended_unix_ns']<=meta['verified_unix_ns']<=h2['released_unix_ns']
        a=aux['owner_approval'];idle=aux['idle'];now=time.time_ns()
        assert h2['study']=='rc17-text-size-first-selection-wall-plan' and h2['study_ref']=='44c3e6db80242b5461bbb3f86f2fae5a0f166a45' and h2['host']=='charlie-ohm-relink-b-1024' and h2['released_for']==ref and h2['admission_sha256']==sha(admission)
        assert re.fullmatch('[0-9a-f]{40}',h2['terminal_ref']) and re.fullmatch('[0-9a-f]{64}',h2['terminal_sha256']) and h2['scored_processes_running']==0
        assert h2['owner_review']=='released by H2 operator after terminal' and (h2['status']=='complete' and h2['score_exit']==0 or h2['status']=='failed' and h2['score_exit']!=0)
        assert 0<h2['ended_unix_ns']<=h2['released_unix_ns']<=a['unix_ns']<=now and now-a['unix_ns']<180*10**9
        assert a['host']==socket.gethostname() and a['other_scored_processes']==0 and a['owner_review'] and a['admission_sha256']==sha(admission) and a['h2_release_sha256']==aux['h2_release_sha256']
        assert idle['host']==socket.gethostname() and idle['lock_clear'] and idle['no_compilers'] and idle['study_sessions']==idle['scored_commands']==0 and idle['admission']==sha(admission) and 0<=now-idle['unix_ns']<180*10**9

        assert public['plan_ref']==ref and public['plan_manifest']==digest and public['admission_sha256']==sha(admission)
        assert public['catalog_publication_sha256']==sha(launch/'catalog-publication.json') and public['ci_sha256']==sha(launch/'ci.json')
        assert public['catalog_ref']==read(launch/'catalog-publication.json')['catalog_result_ref'] and re.fullmatch('[a-f0-9]{40}',public['admission_ref'])
        assert grant==dict(go='score exact v3c 24 fresh pairs',native_sha256=sha(admission),plan_manifest=digest,published_plan=ref,
                           published_catalog=public['catalog_ref'],published_native=public['admission_ref'],ci_sha256=public['ci_sha256'],
                           h5_clear=True,other_host_measurement=False,ci_review='accepted')
        save(launch/'operator-release.json',aux)
        save(launch/'admission-publication.json',public)
        save(launch/'grant.json',grant)
        start('score',[plan/'runner.py','score',launch/'grant.json'])
elif mode == 'verify':
    assert (launch/'score.exit').read_text()=='0' and (result/'complete.json').is_file()
    name=json.load(sys.stdin)['verifier_file'];assert re.fullmatch(r'[a-zA-Z0-9_.-]+\.py',name)
    verifier=plan/name;assert verifier.is_file() and not verifier.is_symlink() and sha(verifier)==sha(plan/'verify_result.py')=='d809ce76f63cfcfdb16c86b0b3e7ab0e57d025cfc0d0ec8d91e029dd7e251a9d'
    start('verify',[verifier,result,admission])
else:
    raise ValueError(mode)
