from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent;sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();m={n:h for h,n in (l.split('  ',1) for l in (p/'SHA256SUMS').read_text().splitlines())};assert set(m)=={x.name for x in p.iterdir() if x.is_file() and x.name!='SHA256SUMS'} and all(sha(p/n)==v for n,v in m.items())
a=json.loads((p/'observations.json').read_bytes());orig=json.loads((p/'original-sha256.json').read_bytes());assert len(orig)==194 and a['raw_terminal']==orig['qa-v1/complete.json'] and a['raw_errno_terminal']==orig['kernel-v1/result.json'];assert sha(p/'compiler.patch')==a['patch_sha256']=='2eb0b9bc60164b4646b7c00f259dc84d787d76493f5a16e915a52c11ab1e8315';assert sha(p/'checked_file.rs')==a['standalone']['checked_module'];assert a['scope']==dict(platform='x86_64-unknown-linux-gnu',filesystem='btrfs',uid=1000,build_exit=0,package_exit=0,first_supplemental_read_only_mount_exit=32,supplemental_standard_read_only_mount_exit=0)
rows={r['case']:r for r in a['native_compiles']};assert len(rows)==20 and a['standalone']['two_kernel_success_counts']==[8,8] and sorted(a['standalone']['limit_errno'])==[['limit-false','EFBIG'],['limit-true','EFBIG']];assert a['runtime_tar_bytes']==143789830
for n,r in rows.items():
    assert r['exit']==0 and r['bytes']==798902 and r['archive_sha256']==rows[r['arm']+'-normal'+str(r['value'])]['archive_sha256'];assert r['syscall_trace_sha256']==orig['qa-v1/raw/'+n+'.trace'];assert r['directed_final_output_events']==['IN_MOVED_TO'] and r['successful_renames_of_private_temp_to_output']==1
    assert r['old_fd_still_old_and_distinct_inode']==(n!='base-normal17')
assert {k for k,r in rows.items() if r['clone_successes']}=={'treatment-original-correct','treatment-real-edit-stale','treatment-repeat-valid','treatment-restore-stale','treatment-restored-repeat','treatment-corrupt-backdated'};assert rows['treatment-cross-device']['kernel_clone_op_results']==['EXDEV'];assert rows['treatment-original-correct']['actual_pwrite_bytes_to_tmp_a']==0 and rows['treatment-real-edit-stale']['actual_pwrite_bytes_to_tmp_a']==278460
assert a['same_size_backdated_corrupted_offsets']==[0,65536,798901]
for n,v in a['readers'].items():
    for c,x in v.items():assert x['actual_wild']==1 and x['exit']==0 and x['trace_sha256']==orig['qa-v1/raw/'+n+'-'+c+'.trace']
    assert v['bin']['output']==('17 128\n' if n in {'base17','candidate-original','candidate-restored'} else '29 151\n') and v['test']['output']=='one passed, zero failed'
assert len(a['readers'])==6;print('PASS: 20 whole archives, six compiler FICLONE hits, two 15-case kernel runs, 12 independently linked native readers and harnesses')
