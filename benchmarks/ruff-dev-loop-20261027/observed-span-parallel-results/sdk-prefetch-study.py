"""Run the registered two-workload study, followed by the separate complete process audit."""
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paired import NAMES, Study, getargs, log_json, sha

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'sdk-prefetch-registration.json'
PLAN_SHA = '628f3f6f7d96baf32b9c95c957c5e3585388235c5da2b24fbe7f0d5d82ed774c'
READERS = {'hold_bridge', 'hold_direct'}


def prepare_ron(study, label, registry, lock):
    store = study.init(label)
    (store / 'src/Cargo.toml').write_text('[workspace]\nmembers=["probe_ron"]\nresolver="2"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n')
    crate = store / 'src/probe_ron'
    (crate / 'src').mkdir(parents=True)
    (crate / 'Cargo.toml').write_text('[package]\nname="probe_ron"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n')
    (crate / 'src/lib.rs').write_text('pub fn text()->String{ron::to_string(&17u32).unwrap()}\n#[test]fn check(){assert_eq!(text(),"17")}\n')
    (store / 'cargo-home/registry').symlink_to(registry)
    shutil.copyfile(lock,store/'src/Cargo.lock')
    return store


def run(study, store, arm, label, *, trace, ron=False):
    kwargs = {}
    if ron:
        kwargs.update(packages=('probe_ron',), mode='test --no-run', check_product=False,
                      envadd={'CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST':'all','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST':'all'})
    row = study.run(store, arm, label, trace=trace, **kwargs)
    if ron:
        terminal = gzip.decompress((study.logs / label / 'stderr.gz').read_bytes()).decode()
        written = re.findall(r'^\s*Executable unittests src/lib.rs \((.+)\)$',terminal,re.MULTILINE)
        assert len(written)==1,(label,written)
        executable = store / Path(written[0]).relative_to(study.active)
        assert executable.is_file() and os.access(executable,os.X_OK)
        row['ron_executable'] = {'name':executable.name,'sha256':sha(executable)}
        row['ron_source_manifest'] = {n:sha(store/'src'/n) for n in ('Cargo.toml','Cargo.lock','probe_ron/Cargo.toml','probe_ron/src/lib.rs')}
    if trace:
        text = gzip.decompress((study.logs/label/'exec.gz').read_bytes()).decode(errors='replace')
        row['checksum_helpers'] = sum('PR_SET_NAME, "cargo-checksum"' in line for line in text.splitlines())
    log_json(study.logs/label/'result.json',row)
    return row


def fresh(study, row, arm, gold, *, ron, trace):
    if ron:
        assert row['ron_executable']==gold['ron_executable'] and row['ron_source_manifest']==gold['ron_source_manifest']
        assert any(k.endswith('dep-lib-ron') and v['complete'] for k,v in row['readers'].items())
    else:
        study.equivalent(row,gold)
        assert row['source']==gold['source']
        assert len(row['readers'])==2 and all(v['complete'] and v['signed'] for v in row['readers'].values())
    if trace:
        assert not row['roster'] and bool(row['checksum_helpers'])==(arm=='C'),(row['phase'],row['roster'],row['checksum_helpers'])
        assert all(Path(p).name not in ('cc','collect2','ld.bfd') for p in row['successful_exec_images'])


def edited(study, row, gold, *, trace):
    study.equivalent(row,gold)
    assert row['source']==gold['source'] and len(row['readers'])==2
    assert all(v['complete'] and v['signed'] for v in row['readers'].values())
    if trace:
        rr=row['roster']
        assert len(rr)==5 and row['checksum_helpers']==0
        assert {x['crate'] for x in rr if x['mode']=='full'}==READERS|{'hold_shapes','hold_indirect'}
        assert {x['crate'] for x in rr if x['mode']=='relink'}=={'hold_plain'}
        assert {x['crate'] for x in rr if x['capture']}==READERS
        assert sum(Path(p).name=='ld.bfd' for p in row['successful_exec_images'])==3


def main():
    plan=json.loads(PLAN.read_text());assert sha(PLAN)==PLAN_SHA
    study=Study(getargs())
    study.bins['V']=Path(os.environ['PREVIOUS_CARGO']).resolve()
    registry=Path(os.environ['BENCH_REGISTRY']).resolve()
    lock=Path(os.environ['RUFF_LOCKFILE']).resolve()
    assert registry.is_dir() and sha(lock)==plan['inputs']['ruff_lock_sha256']
    assert sha(HERE/'sdk-prefetch-ron.py')==plan['inputs']['local_ron_fixture_source_sha256']
    assert sha(HERE/'observer-sdk-prefetch-screen1.patch')==plan['subject']['candidate']['sdk_increment_sha256']
    assert sha(HERE/'observer-edit-screen1.patch')==plan['subject']['earlier']['v4_increment_sha256']
    hashes={'P':plan['subject']['golden'],'V':plan['subject']['earlier']['cargo_sha256'],'C':plan['subject']['candidate']['cargo_sha256'],
            'rustc':plan['subject']['rustc'],'driver':plan['subject']['compiler_driver']}
    assert study.a.cpus=='0-3'
    assert {**study.digest,'V':sha(study.bins['V'])}==hashes
    subject=json.loads((study.logs/'subject.json').read_text())
    subject.update(plan=PLAN_SHA,sha256=hashes)
    log_json(study.logs/'subject.json',subject)
    normal=subprocess.run
    def threads(cmd,*args,**kwargs):
        if 'trace=execve' in cmd:
            cmd=list(cmd);cmd[cmd.index('trace=execve')]='trace=execve,prctl'
        return normal(cmd,*args,**kwargs)
    subprocess.run=threads
    study.references()
    ron_gold=run(study,prepare_ron(study,'empty-ron',registry,lock),'P','empty-ron',trace=True,ron=True)
    for tag in ('native','audit'):
        trace=tag=='audit'
        synthetic={k:study.init(tag+'-synthetic-'+k) for k in 'VC'}
        ron={k:prepare_ron(study,tag+'-ron-'+k,registry,lock) for k in 'VC'}
        for fixture,stores,flag in [('synthetic',synthetic,False),('ron',ron,True)]:
            for k,store in stores.items():
                for i in range(4):
                    r=run(study,store,k,f'{tag}-training-{fixture}-{k}-{i}',trace=True,ron=flag)
                    if flag: assert r['ron_executable']==ron_gold['ron_executable']
                    else: study.equivalent(r,study.gold[False])
                fresh(study,r,k,ron_gold if flag else study.gold[False],ron=flag,trace=True)
        for block in plan['orders']:
            new=block['edit_direction']=='add'
            for endpoint in ('synthetic_noop','ron_noop','first_edit'):
                for k in block[endpoint]:
                    name=f"{tag}-{block['block']:02}-{endpoint}-{k}"
                    if endpoint=='first_edit': study.edit(synthetic[k],new)
                    flag=endpoint=='ron_noop'
                    record=run(study,ron[k] if flag else synthetic[k],k,name,trace=trace,ron=flag)
                    if endpoint=='first_edit':
                        edited(study,record,study.gold[new],trace=trace)
                    else:
                        fresh(study,record,k,ron_gold if flag else study.gold[not new],ron=flag,trace=trace)
    assert len(study.results)==227
    assert {k:sha(p) for k,p in study.bins.items()}=={k:hashes[k] for k in study.bins}
    log_json(study.logs/'passed.json',{'completed_commands':227,'native_observations':96,'audited_repetitions':96,
                                      'warm_training':32,'independent_empty_references':3})

if __name__=='__main__':
    main()
