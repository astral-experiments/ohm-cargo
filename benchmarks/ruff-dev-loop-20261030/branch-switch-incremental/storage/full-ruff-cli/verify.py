#!/usr/bin/env python3
"""Verify allocations, original file commitments and the calibrated hardlink case."""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,tempfile
root=Path(__file__).resolve().parent
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(j):
    assert j['arms_measured']==2 and j['pairs_per_role']==1
    assert j['source']['parent']['revision']=='b5dba861cc38e3f7fb4524c9ceba3e01a474ea13'
    assert j['source']['feature']['revision']=='7b13f01ba1569887a25670820764b24c206da8e5'
    g=j['cross_compiler_raw_gate'];assert g['pass'] is False and g['sampled_ordinary_timed_arms']==0
    assert g['all_segments_equal_after_masking_only_gnu_build_id'] and g['distinct_replaced_debug_string_value']==1
    roles=j['roles']
    expected={'parent':(2418098176,1089441792,9451),'guarded':(3513303040,2184646656,11484)}
    for arm,rs in roles.items():
        s=rs['body_storage_as_seen'];assert rs['two_equal_complete_ledgers'] and rs['source_phase']=='parent'
        assert rs['last_reader_witness']=='Expr=64 valid=1 rejected' and rs['observed_last_phase_actual_unchanged']
        assert rs['typed_artifacts_unchanged']==375 and not s['working_directories']
        assert (s['all']['allocated_bytes'],s['all_incremental']['allocated_bytes'],s['path_entries'])==expected[arm]
        for key in ['allocated_bytes','inodes','logical_bytes_unique_inodes']:
            assert s['all'][key]==s['products'][key]+s['shared'][key]-s['both_roots_same_inode'][key]
            assert s['all_incremental'][key]==s['incremental_only'][key]+s['incremental_also_named_outside'][key]
        assert s['incremental_also_named_outside']['allocated_bytes']==42074112
    p,i,_=expected['parent'];q,k,_=expected['guarded']
    assert q-p==k-i==1095204864
    return {'parent_target_plus_build_allocated_bytes':p,'guarded_target_plus_build_allocated_bytes':q,'difference_bytes':q-p,'target_plus_build_ratio':q/p,'parent_incremental_bytes':i,'guarded_incremental_bytes':k,'incremental_ratio':k/i,'complement_bytes_each':p-i}
def toy():
    spec=importlib.util.spec_from_file_location('census',root/'census.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);a=d/'target';b=d/'shared';a.mkdir();b.mkdir();inc=b/'incremental';inc.mkdir()
        src=inc/'a.o';src.write_bytes(bytes(range(256))*80);os.link(src,a/'a.o');(a/'symlink').symlink_to(src);(inc/'independent').write_bytes(b'x'*4096)
        z=mod.census(a,b)
        total=int(subprocess.check_output(['du','-sc','-B1','--',a,b],text=True).splitlines()[-1].split()[0])
        assert z['all']['allocated_bytes']==total and z['both_roots_same_inode']['inodes']==z['incremental_also_named_outside']['inodes']==1
        bad=inc/'s-123-working';bad.mkdir()
        try:mod.census(a,b)
        except AssertionError:pass
        else:raise AssertionError('accepted an active incremental session')
if __name__=='__main__':
    for ln in (root/'SHA256SUMS').read_text().splitlines():
        digest,n=ln.split('  ',1);assert '/' not in n and h(root/n)==digest
    j=json.loads((root/'observations.json').read_bytes());result=check(j);toy()
    j['roles']['parent']['body_storage_as_seen']['all']['allocated_bytes']+=4096
    try:check(j)
    except AssertionError:pass
    else:raise AssertionError('failed to reject changed measured bytes')
    print(json.dumps(result,sort_keys=True))
