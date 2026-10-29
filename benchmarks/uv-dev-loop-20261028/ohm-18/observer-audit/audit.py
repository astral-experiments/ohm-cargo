"""Read small preserved launch receipts plus marker/compiler-cache identities; never print process environments."""
import datetime
import hashlib
import json
from pathlib import Path

here=Path(__file__).resolve().parent;suite=here.parent;work=suite.parent;lab=work/'round18-lab';bench=Path((work/'bench-home.path').read_text().strip());report={}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cache(root):
    f=root/'.rustc_info.json';q=read(f)
    return dict(target=str(root),ready_marker=(root/'.ohm-built-registry-ready').is_file(),compiler_fingerprint=q['rustc_fingerprint'],previous_fingerprint=q.get('previous',{}).get('rustc_fingerprint'),cache_mtime_ns=f.stat().st_mtime_ns,cache_sha256=sha(f))
def env_proof(out,prefix,root):
    slot=str(root/'bin/cargo');files=[]
    for f in out.glob(prefix+'.exec.*'):
        for line in f.read_text().splitlines():
            if line.startswith('execve("'+slot+'",') and line.endswith('= 0'):
                assert 'CARGO_HOME=' in line and 'RUSTC=' in line and 'RUSTC_WRAPPER=' not in line and 'RUSTC_WORKSPACE_WRAPPER=' not in line
                files.append(dict(path=str(f.relative_to(work)),sha256=sha(f),rustc_wrapper=False,workspace_wrapper=False))
    assert len(files)==1;return files[0]
for cohort in ('initial','replica'):
    root=bench/'role-studies-18'/cohort;old=suite/'edited-roles/results'/cohort/'check';proof=[]
    for d in sorted(old.glob('admit-*-native-*')):
        f=d/'native-execs.json';actual=read(f);assert actual[str(root/'tools/rustc-wrapper')]==actual[str(work/'upstream-monitor/toolchain18/bin/rustc')]==1
        proof.append(dict(path=str(f.relative_to(work)),sha256=sha(f),compiler_wrapper_processes=1,actual_distributed_rustc=1))
    assert len(proof)==2;report['edited-roles-'+cohort]=dict(cache=cache(root/'common'),native_admissions=proof,harness_sha256=sha(suite/'edited-roles/run.py'))
for label in ('initial','replica','fast'):
    d=lab/'driver-counters'/label;cfg=read(d/'protocol.json');q=cache(Path(cfg['target']));first=min(p.stat().st_mtime_ns for p in d.glob('check-[0-9]*.log'));assert q['cache_mtime_ns']<first
    report['warm-driver-'+label]=dict(cache=q,mode=cfg['mode'],argv=cfg['argv'],first_scored_check_log_mtime_ns=first,protocol_sha256=sha(d/'protocol.json'),harness_sha256=sha(work/'measure.py' if label!='replica' else lab/'measure-pause.py'),launcher_sha256=sha(lab/'counter-run.py'),warm_sha256=sha(lab/'counter-prep'/('initial' if label=='initial' else 'replica')/'ready.json'))
for guard in ('hash','ordered'):
    base=suite/('lockfile-collision' if guard=='hash' else 'lockfile-collision-ordered');plan=read(base/'plan.json');saved=base/'recovery' if guard=='hash' else base
    for label,c in plan['cohorts'].items():
        root=Path(c['fixture']);r=saved/'results'/label;proof=[env_proof(r,'settled.log',root)];wall=label.startswith('wall')
        if wall:
            d=suite/'resolver-native-repair'/guard/'results'/label
            proof += [env_proof(d,'admit-'+a+'.log',root) for a in ('base','candidate')]
        row=dict(cache=cache(root/'predecessor'),actual_argv=c['command'],native_exec_environment=proof,harness_sha256=sha(base/'common.py'))
        report[guard+'-'+label]=row
assert all(row['cache']['compiler_fingerprint']==6438448433861015610 for k,row in report.items() if not k.startswith('edited-roles'))
assert all(not row['cache']['ready_marker'] for k,row in report.items() if k.startswith(('hash-','ordered-')))
report['as_of']=datetime.datetime.now(datetime.timezone.utc).isoformat();(here/'receipts.json').write_text(json.dumps(report,indent=2)+'\n');print([(k,v['cache']['ready_marker'],v['cache']['compiler_fingerprint']) for k,v in report.items() if isinstance(v,dict)])
