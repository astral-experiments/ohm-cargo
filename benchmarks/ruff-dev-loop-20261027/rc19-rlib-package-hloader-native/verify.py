"""Derive the stopped admission and validate each native product and historical edit receipt."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
def load(path):return json.loads((ROOT/path).read_bytes())
def sha(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()

def verify(native,routing,members):
    setup=native['setup']
    assert setup['source']=='1e9287d7654f1dbe4943d67ed5ac5363c9ee2161'
    assert setup['parent']=='57d800be552a88751e7ecd06fc87b44714536033'
    assert setup['cargo']=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573'
    assert setup['cap_eff']=='0'and setup['filesystem']=='btrfs'and setup['registry_offline']
    assert not native['mounted_after_all_qualification']
    custody=native['custody'];assert custody['readonly_btrfs_property']=='ro=true'and custody['source']==setup['source']and custody['git_diff_exit']==0
    assert custody['registry_tree']['file_mode_content_tree_sha256']=='7a18b2f43d7894e8d7ca6a07710d5cd0b154aa15816747f2d31a516765297ab3'
    seq=native['training_and_edit']
    assert len(seq)==20 and all(r['target_rows']==248 and len(r['dirty'])<=248 for r in seq.values())
    assert seq['fresh-H']['old_candidate_sha']==custody['seed_top']
    assert not seq['fresh-H']['dirty']and len(seq['cold-H']['dirty'])==248
    cold=seq['independent-empty-edited']
    assert len(cold['dirty'])==248 and not seq['independent-empty-repeat']['dirty']
    assert cold['old_candidate_sha']==custody['active_empty_top']
    normal=['stock-reverse-traced','stock-restored-timestamped']
    assert all(len(seq[k]['dirty'])==10 for k in normal)
    assert all(not seq[k]['dirty'] for k in ['stock-post-reverse','stock-restored-repeat'])
    assert seq['stock-reverse-traced']['old_candidate_sha']!=cold['old_candidate_sha']
    diff=native['original_open_fd_and_hardlink']
    assert diff['same_held_inode'] and diff['old_held_after']==diff['old_fd_after']==custody['seed_top']
    assert diff['current']==seq['stock-reverse-traced']['old_candidate_sha']
    sy=native['stock_syscalls'];sp=native['stock_span']
    assert sy['syscall_counts']==sp['counts']=={'openat':1,'write':540,'close':1,'rename':1}
    assert sy['open_flags']=='O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC' and not sy['seek_count']
    assert sy['write_bytes']==seq[normal[0]]['file_bytes']==sp['write_bytes']==seq[normal[1]]['file_bytes']
    output={'H':'1 SIM222\n','OLD':'2 SIM222\n3 SIM222\n4 SIM222\n'}
    pr=native['programs']
    assert pr['stock-H-cli']['stdout']==pr['stock-restored-cli']['stdout']==output['H']
    assert pr['stock-edited-cli']['stdout']==pr['independent-empty-cli']['stdout']==output['OLD']
    assert pr['stock-edited-cli']['executable']!=pr['independent-empty-cli']['executable']
    assert pr['independent-empty-cli']['linter']==cold['old_candidate_sha']
    assert all(r['exit']==0 and r['input']==pr['stock-H-cli']['input']and r['stderr_sha256']==hashlib.sha256(b'').hexdigest()for r in pr.values())
    selected=native['off_clock_cases']
    assert {k.removeprefix('proof-real-')for k in selected}=={'cow','observe','malformed','restored'}
    for key,result in selected.items():
        case=key.removeprefix('proof-')
        event=result['event'];f=seq[case+'-edited'];after=seq[case+'-repeat'];src=result['source']
        assert result['helper_sha256']==native['software']['archive_probe-v2.so']
        assert f['from_this_cargo']and not after['from_this_cargo']and after['dirty']==[]and len(f['dirty'])==241
        assert f['old_candidate_sha']==after['old_candidate_sha']==result['new']==result['reference']==result['consumer']['linter']
        assert result['old_fd']==seq[case+'-base']['old_candidate_sha'] and result['old_fd']!=result['new']
        assert result['repeat_fresh']and not result['repeat_has_log']and result['consumer']['exit']==0 and result['consumer']['stdout']==output[src]
        assert result['consumer']['executable']==pr['stock-restored-cli'if src=='H'else 'stock-edited-cli']['executable']
        assert event['event']=='exit'and event['closed']==event['publications']==event['found_output']==1
        assert not event['fatal_errno']and not event['reference_errno']and event['alternate']=='none'
        assert event['generated_bytes']==event['position']==f['file_bytes']==event['skipped_bytes']+event['actual_bytes']
        clone=case in ('real-cow','real-restored')
        assert event['did_clone']==int(clone)
        assert event['decision']==('cloned'if clone else 'observe'if case=='real-observe'else 'prior-magic')
        assert event['skipped_bytes']==(10787212 if clone else 0)
    n=native['native_kernel_cases'];controls=n['cases'];assert len(controls)==n['case_count']==22 and n['shared']==native['software']['archive_probe-v2.so']
    for key,r in controls.items():
        assert r['body']==r['required_input_sha256']
        if '-limited' in key:
            assert r['syscall_observation']==[512,0,-1,27,1,0,0]and r['exit']==0
        elif '-rename-error' in key:
            assert r['exit']==11 and r['syscall_observation'][-1]==-1 and r['native']==29
        else:assert r['exit']==0
        if r['reference']:assert r['reference']==r['required_input_sha256']
        if '-sync-'in key:
            before,after=map(int,key.split('-')[-2:]);assert r['native']==before and r['input_after']!=r['required_input_sha256']
    for key,decision in {'wrong-magic':'prior-magic','fifo':'prior-type-identity','directory':'prior-type-identity','missing':'prior-open','symlink':'prior-open'}.items():
        assert controls['cow-'+key]['io']['decision']==decision and controls['cow-'+key]['native']==29
    assert set(native['failed_preflights'])=={'stock-reverse','native-guards'}and all(r['exit']==1 for r in native['failed_preflights'].values())
    roles=routing['relocated'];assert len(roles)==routing['relocated_typed_rows']==185
    assert routing['total']==len(roles)+routing['unchanged_typed_paths']==248
    assert routing['relocated_literal_file_paths']==sum(len(x['stock'])for x in roles.values())==340
    for rec in roles.values():
        assert len(rec['stock'])==len(rec['observe_and_cow'])
        for x,y in zip(rec['stock'],rec['observe_and_cow']):
            assert x.startswith('shared/debug/build/registries/')and y.startswith('target/debug/build/workspaces/')
            assert x.partition('registries/')[2]==y.partition('workspaces/')[2].split('/',1)[1]
    assert routing['counts']['stock-reverse-traced']['rebuilt']==10
    for k in ['real-cow-edited','real-observe-edited','real-malformed-edited','real-restored-edited']:assert routing['counts'][k]['rebuilt']==241
    for name,commit in routing['raw_sha256'].items():assert native['physical_raw_file_sha256'][name+'/cargo.jsonl']==commit
    for k,q in members.items():
        assert len(q['elf'])==256 and q['header_and_payload']==260
        prev=0
        for row in q['elf']:
            assert len(row['sha256'])==64 and row['offset']>=prev and 0<row['size']<=q['archive_length']-row['offset']
            prev=row['offset']+row['size']
    initial=members['H']['elf']
    assert sum(row['size']for row in initial)==77408976
    for tag in ('stock-edited','stock-restored'):
        assert initial==members[tag]['elf']
    for tag in ('real-cow','real-restored'):
        assert all(x['offset']-24==y['offset']and x['size']==y['size']and x['sha256']==y['sha256']for x,y in zip(initial,members[tag]['elf']))
    ar=native['archive_deltas']['H_stock-edited']
    assert ar['equal_names']==0 and ar['equal_offset_and_size']==ar['equal_payloads_in_order']==256
    stable=[(x,y)for x,y in zip(*ar['non_elf'])if x==y]
    assert len(stable)==1 and stable[0][0]['name']=='/'and stable[0][0]['size']==9251912
    return {'ordinary_equal_position_native_payload_bytes':77408976,'ordinary_equal_index_bytes':9251912,
            'ordinary_identified_equal_file_ranges':77408976+9251912,'cow_warm_equal_payloads_shift':-24,
            'units':248,'stock_rebuilt':10,'preload_first_rebuilt':241,'physical_rows_relocated':185,
            'physical_names_relocated':340,'cases':22,'measured_wall_slots':0,
            'matched_work_wall_admission':False}

if __name__=='__main__':
    n=load('native.json');r=load('routing.json');m=load('stock-member-offsets.json')
    source=load('release-cargo-source.json');assert source['commit']==r['source']['cargo']
    a=source['files']['src/compiler/mod.rs'];b=source['files']['src/compiler/build_runner/compilation_files.rs']
    assert a['sha256']=='415cbc48618bbda34eace953b6efd03bb2a1db26b455b6f2073e992e4ba8ae5d'
    assert b['sha256']=='dd90984eb9c1eabe53ad1333ecdfb1f392c6cbeac5ac5be7a63f1e5d7068e263'
    assert any('LD_PRELOAD' in line for v in a['sections'] for line in v['lines'])
    assert any('&& !injected_loader' in line for v in b['sections']for line in v['lines'])
    for name,digest in n['software'].items():
        p=ROOT/'reproduce'/name
        if p.exists():assert sha(p)==digest
    out=verify(n,r,m)
    if '--selftest' in sys.argv:
        for edits in (('incorrect conditional archive',0),('conceal relocated paths',1),('treat shifted native payloads as stock-aligned',2),('wrong independent program',3)):
            n1,r1,m1=map(copy.deepcopy,(n,r,m))
            if edits[1]==0:n1['off_clock_cases']['proof-real-cow']['reference']='0'*64
            elif edits[1]==1:next(iter(r1['relocated'].values()))['stock']=['unexpected']
            elif edits[1]==2:m1['real-cow']['elf'][0]['offset']+=24
            else:n1['programs']['independent-empty-cli']['stdout']='1 SIM222\n'
            try:verify(n1,r1,m1)
            except AssertionError:pass
            else:raise AssertionError(edits[0])
    print(json.dumps(out,indent=2,sort_keys=True))
