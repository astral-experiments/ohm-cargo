"""Admit independently audited native products, then run only a separately granted wall series."""
import argparse
import collections
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import analysis
import catalog
import guards as g
import native_registration

RESULT=g.BASE/'early-scheduler-wall-rc17-v3'
ADMISSION=g.BASE/'early-scheduler-wall-admission-v3.json'


def restore_method():
    fs=subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',g.BASE],text=True).strip()
    assert fs==g.P['storage_after_unscored_v1']['filesystem']=='ext4',fs
    with tempfile.TemporaryDirectory(prefix='wall-clone-probe-',dir=g.BASE) as d:
        a,b=(Path(d)/name for name in ('a','b'))
        a.write_bytes(bytes(range(256))*4096)
        with a.open('rb') as src,b.open('w+b') as dst:
            try:
                fcntl.ioctl(dst.fileno(),0x40049409,src.fileno())
            except OSError as err:
                if err.errno != g.P['storage_after_unscored_v1']['errno'] or err.errno != errno.EOPNOTSUPP:
                    raise
                return 'never'
            assert g.sha(b)==g.sha(a) and a.stat().st_ino!=b.stat().st_ino
            dst.seek(0);dst.write(b'X');dst.flush()
            assert g.sha(b)!=g.sha(a)
    raise AssertionError('this ext4 admission requires unsupported FICLONE')


def ci_gate(path):
    assert g.sha(path)==g.P['composed_ci']['qa_sha256']
    q=g.read(path)
    assert set(q)=={'source','observer','composed','tests','build','status'}
    assert q['source']==g.P['source'] and q['status']=='pass' and q['composed']!=q['observer']
    assert q['observer']==g.P['control']
    assert set(q['build'])=={'observer','composed'}
    for role, record in q['build'].items():
        assert record['cargo_sha256']==q[role]
        for key in ('recipe_sha256','profiles_sha256','source_recipe_sha256'):
            assert re.fullmatch('[0-9a-f]{64}',record[key])
        evidence=(path.parent/record['evidence']).resolve()
        assert evidence.is_relative_to(path.parent.resolve()) and g.sha(evidence)==record['receipt_sha256']
        physical=g.read(evidence)['physical'];identity=g.P['composed_ci'][role]
        assert physical['source_records_sha256']==identity['physical_source_sha256'] and physical['files']==3108
        assert physical['cargo']==record['cargo_sha256']
    assert all(q['build']['observer'][key]==q['build']['composed'][key] for key in ('recipe_sha256','profiles_sha256'))
    independent=g.P['independent_baseline_build']
    assert q['build']['observer']['profiles_sha256']==independent['profile_sha256']
    assert g.sha(HERE/'replayed-control-loads.json')==independent['comparison_sha256']
    assert g.read(HERE/'replayed-control-loads.json')['replayed_control']==independent['actual_duplicate_sha256']
    want={'built-library','unused','used','missing-proof','observer-replacement','ordinary-reader','cached-state-migration'}
    assert set(q['tests'])==want
    for record in q['tests'].values():
        assert record['exit']==0
        assert record['subject'] in (q['observer'],q['composed']) and record['evidence']
        witness=(path.parent/record['evidence']).resolve()
        assert witness.is_relative_to(path.parent.resolve()) and witness.is_file()
        assert g.sha(witness)==record['receipt_sha256']
    assert all(q['tests'][case]['subject']==q['composed'] for case in ('built-library','unused','used','missing-proof'))
    return q


def qualified_native(n):
    native=catalog.qualify(n,g)
    native['native_catalog'].update(native_registration.check(g.BASE,g.manifest))
    return native


def admission(n,qa):
    n.source()
    controls=qualified_native(n)
    checked=ci_gate(qa)
    assert checked['composed']==controls['subjects']['C']
    seed=g.tree(n.seed)
    mode=restore_method()
    reserve=g.P['minimum_remaining_bytes']; allowance=g.P['temporary_product_allowance']
    assert shutil.disk_usage(g.BASE).free>seed['unique_file_bytes']+reserve+allowance
    receipt={'worker_manifest':g.manifest(HERE),'native':controls,'seed':seed,'fs':g.P['storage_after_unscored_v1']['filesystem'],'copy':mode,
             'qa_sha256':g.sha(qa),'ci_status':checked['status'],'scored_commands':0,
             'pessimistic_full_copy_bytes_all_48':48*seed['unique_file_bytes']}
    return receipt


def readonly_seed_inodes(seed,state):
    def ids(root):
        return {(s.st_dev,s.st_ino) for f in root.rglob('*') if (s:=f.lstat()).st_nlink>0 and f.is_file() and not f.is_symlink()}
    assert ids(seed).isdisjoint(ids(state))


def namespace(n, state, role, directory):
    argv,env,h=n.invocation(state,role,True,directory)
    assert not set(env).intersection({'RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS',
            'CARGO_LOG','CARGO_INCREMENTAL','LD_PRELOAD','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'})
    assert sorted(os.sched_getaffinity(0))==g.P['cpu']
    for f,want in ((n.sdk/'bin/cargo',h),(n.src/n.scope,n.hash1)):
        assert subprocess.check_output(argv+['sha256sum',f],env=env).split()[0].decode()==want
    assert subprocess.check_output(argv+['rustc','+ohm','--print','sysroot'],env=env,text=True).strip()==str(n.sdk)
    return argv,env


def top_diagnostics(stder,products):
    """Rust's rendered first lines must match, while Cargo may print per-target warning totals."""
    strip=lambda t: re.sub(r'\x1b\[[0-9;]*m','',t)
    header=re.compile(r'^(?:warning|error)(?:\[[A-Z0-9]+\])?:')
    lines=[strip(l) for l in stder.splitlines()]
    def cargo_total(line):
        return bool(re.match(r'^warning: `.+`.* generated (?:[0-9]+ warnings?|[0-9]+ warnings? \([^)]+\))',line))
    actual=collections.Counter(l for l in lines if header.match(l) and not cargo_total(l))
    wanted=collections.Counter()
    for _,d in products['diagnostics']:
        if d['level'] in ('warning','error'):
            rendered=strip(d['rendered']).splitlines()
            assert rendered and header.match(rendered[0])
            if not cargo_total(rendered[0]):wanted[rendered[0]]+=1
    assert actual==wanted,(actual,wanted)
    return dict(actual)


def slot(n, frozen, arm, block, position):
    role=g.ROLES[arm];seed=frozen['seed'];controls=frozen['native']
    out=RESULT/f'{block:02d}-{position}-{arm}';out.mkdir()
    state=out/'private-state'
    assert seed['unique_file_bytes']+g.P['temporary_product_allowance']+g.P['minimum_remaining_bytes']<shutil.disk_usage(g.BASE).free
    subprocess.run(['cp','-a','--reflink='+frozen['copy'],'--',n.seed,state],check=True)
    assert state.stat().st_dev==n.seed.stat().st_dev and g.tree(state)==seed
    readonly_seed_inodes(n.seed,state)
    critical=controls['typed_seed_rlib']
    reference=g.read(n.w/('selected-'+role)/'products.json')
    target,=reference['e2e']
    assert g.sha(n.actual(critical['file'],state))==critical['sha']
    assert not n.actual(target,state).exists() and not n.actual(target,n.seed).exists()
    subprocess.run(['sync','-f',state],check=True)
    assert shutil.disk_usage(g.BASE).free>g.P['minimum_remaining_bytes']+g.P['temporary_product_allowance']
    command=out/'ordinary';command.mkdir()
    argv,env=namespace(n,state,role,command)
    g.save(out/'start.json',{'block':block,'slot':position,'arm':arm,'image':controls['subjects'][arm],
        'seed':seed['digest'],'native_binding':g.sha(ADMISSION),'copy':frozen['copy'],
        'free':shutil.disk_usage(g.BASE).free,'loadavg':os.getloadavg(),'cpu':sorted(os.sched_getaffinity(0))})
    # The child starts its clock after bwrap and stops on Cargo's process exit.
    subprocess.run(argv+['/usr/bin/python3','-B',HERE/'clock.py',command,*g.P['command']],env=env,check=True)
    clock=g.read(command/'clock.json')
    assert clock['argv']==g.P['command'] and clock['elapsed_ns']==clock['stop']-clock['start']>0 and clock['returncode']==0
    stdout=(command/'stdout').read_bytes();stder=(command/'stderr').read_text()
    assert not stdout and 'Finished' in stder and 'Blocking waiting' not in stder
    diagnostics=top_diagnostics(stder,reference)
    hashes={key:g.sha(n.actual(key,state)) for key in sorted(controls['allowed'])}
    g.save(out/'first-110.json',hashes)
    g.check_raw(hashes,controls['allowed'])
    registry={key:g.sha(n.actual(key,state)) for key in sorted(controls['registry'])}
    g.save(out/'first-78-registry.json',registry)
    assert registry==controls['registry'] and g.digest(registry)==controls['registry_sha256']
    assert g.sha(n.actual(critical['file'],state))==critical['sha']
    with (command/'e2e-list').open('xb') as so,(command/'e2e-list.stderr').open('xb') as se:
        subprocess.run(argv+[target,'--list'],env=env,stdout=so,stderr=se,check=True)
    assert not (command/'e2e-list.stderr').read_bytes() and g.sha(command/'e2e-list')==controls['listing_sha256']
    later=out/'unchanged'
    products=n.build(state,role,n.selected,True,later,True)
    g.check_raw(products['native'],controls['allowed'])
    assert g.read(later/'registry-native.json')==registry
    assert g.summary(products)==controls['roster'] and g.sha(later/'e2e-list')==controls['listing_sha256']
    jobs=g.row_roster(g.read(later/'physical.json'))
    assert g.digest(sorted(jobs.items()))==controls['repeat_roster']
    assert products['fresh']==g.read(n.w/('repeat-'+role)/'products.json')['fresh']
    summary=dict(block=block,slot=position,arm=arm,elapsed_ns=clock['elapsed_ns'],image=controls['subjects'][arm],
                 registry_78=g.sha(out/'first-78-registry.json'),first_110=g.sha(out/'first-110.json'),follow_110=g.digest(products['native']),follow_roster=g.summary(products),
                 follow_counts=products['counts'],follow_fresh=products['fresh'],diagnostics=diagnostics,
                 stdout=g.sha(command/'stdout'),stderr=g.sha(command/'stderr'),e2e_list=g.sha(command/'e2e-list'))
    g.save(out/'verified.json',summary)
    # Delete only this new successful, verified slot's private copy. Keep all first failure states.
    assert state.parent==out and not state.is_symlink() and state.is_dir() and n.seed.resolve() not in state.resolve().parents
    shutil.rmtree(state)
    return summary,hashes


def main():
    args=argparse.ArgumentParser();args.add_argument('mode',choices=('admit','score'));args.add_argument('authorization',type=Path)
    a=args.parse_args()
    assert socket.gethostname()==g.P['host']
    lock=(g.BASE/'combined-native-measure.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.sched_setaffinity(0,set(g.P['cpu']))
    n=g.worker()
    if a.mode=='admit':
        failure=ADMISSION.with_suffix('.failure')
        assert not ADMISSION.exists() and not failure.exists() and not RESULT.exists()
        try:
            g.save(ADMISSION,admission(n,a.authorization))
        except BaseException:
            with failure.open('x') as f:f.write(traceback.format_exc())
            raise
        print('zero-clock binding',g.sha(ADMISSION))
        return
    assert ADMISSION.is_file() and not RESULT.exists()
    grant=g.read(a.authorization);frozen=g.read(ADMISSION)
    assert frozen['worker_manifest']==g.manifest(HERE)
    published=g.read(g.BASE/'wall-launch-v3/admission-publication.json')
    native_registration.publication_grant(grant,published,frozen['native'],frozen['worker_manifest'],g.sha(ADMISSION),g.P['stopped_v2'])
    assert qualified_native(n)==frozen['native'] and g.tree(n.seed)==frozen['seed'] and restore_method()==frozen['copy']
    RESULT.mkdir(mode=0o700)
    g.save(RESULT/'grant.json',grant);g.save(RESULT/'admission-publication.json',published);rows=[]
    try:
        for i,order in enumerate(g.P['order'],1):
            readings={}
            for j,arm in enumerate(order,1):
                readings[arm]=slot(n,frozen,arm,i,j)
            b,c=(readings[a][1] for a in ('B','C'))
            assert len(b)==len(c)==110
            row=dict(block=i,order=order,ns={a:readings[a][0]['elapsed_ns'] for a in 'BC'},
                     matching_raw=sum(b[k]==c[k] for k in b),
                     raw_differences={k:[b[k],c[k]] for k in b if b[k]!=c[k]})
            rows.append(row);g.save(RESULT/'pairs.json',rows)
            print(f'{i}/24 guarded pairs',flush=True)
        assert g.tree(n.seed)==frozen['seed'] and qualified_native(n)==frozen['native']
        g.save(RESULT/'result.json',analysis.evaluate(g.P,rows))
        g.save(RESULT/'complete.json',{'pairs':24,'slots':48,'analysis':g.sha(RESULT/'result.json'),
               'rows':g.sha(RESULT/'pairs.json'),'admission':g.sha(ADMISSION),'plan':g.manifest(HERE)})
    except BaseException:
        (RESULT/'first-failure.txt').write_text(traceback.format_exc())
        raise


if __name__=='__main__':
    main()
