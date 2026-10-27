from pathlib import Path
import collections,hashlib,json
p=Path(__file__).resolve().parent
load=lambda n:json.loads((p/n).read_text())
plan=load('md-content-plan.json');r=load('holdout.json');fd=load('holdout-results.json');sdk=load('official16.json');assert hashlib.sha256((p/'md-content.patch').read_bytes()).hexdigest()==plan['patch_hash']
assert r['source']==plan['source'] and r['case']==plan['case'] and r['sdk']=={'rustc':sdk['frontend'],'cargo':sdk['cargo']}
assert min(r['minimum_free_bytes'].values())>r['floor']==25*2**30
assert len(r['depfiles'])==3 and all(v['rust_root_present'] and not v['fixture_present'] for v in r['depfiles'])
hashes={};uids={'build':241,'test':301}
for phase,st in r['stages'].items():
    expected=next(iter(plan['after' if phase=='edit' else 'prior'].values()))
    for m,n in uids.items():
        z=st[m];assert z['status']==0 and z['artifacts'][0]==n and z['fixture']==expected
        out=sorted((v['name'],v['bytes'],v['hash'])for v in z['output']);assert out
        if m in hashes:assert out==hashes[m]
        else:hashes[m]=out
        rs=collections.Counter(v['kind']for v in z['processes'])
        if phase=='prime':
            assert rs['rustc-full']=={'build':243,'test':104}[m] and rs['wild']=={'build':43,'test':10}[m]
        else:
            assert not rs and z['artifacts']==[n,n] and z['raw_exec_files']
        print(phase,m,z['artifacts'],dict(rs))
    if phase!='prime':
        read=st['reader'];f=fd[phase]
        assert read['fixture_hash']==f['fixture']==expected
        assert read['status']==0 and read['matched']==[True,True] and read['filter']=='mdtest::typed_dict.md'
        assert read['exe']=='7c0be27cf8a17d49b1a8230687a9f9dee31e7453d1ef334d7a394fcbfd9e2502'
        assert read['size']==f['sum_actual_read_return_bytes']==f['bytes']
        assert sum(v['ret']for v in f['exact_fd_events'] if v['kind']=='read')==read['size']
        assert all(v['path']==plan['unique_fixture_names'][0]for v in f['exact_fd_events'])
        assert len({(v['pid'],v['fd'])for v in f['exact_fd_events']})==1
assert fd['edit']['bytes']==284757 and fd['settled']['bytes']==fd['restore']['bytes']==286133
