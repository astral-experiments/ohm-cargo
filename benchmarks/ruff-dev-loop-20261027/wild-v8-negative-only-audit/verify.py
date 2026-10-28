"""Check the ordinary native oracle, original shipping controls and real ar-header observations."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/name).read_bytes())
def verify():
    run=read('dynamic-and-file.json');archive=read('archive-headers.json')
    assert run['capabilities']==0 and run['user_id']!=0
    assert read('packaging.json')['binary_sha256']==run['tools']['candidate']=='c813de15da27872ce0a294a321053674fa8e7c08b4443798b831a6da5d37374c'
    assert run['tools']['stock']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    stock=run['dynamic']['stock'];cand=run['dynamic']['candidate']
    assert len(stock)==len(cand)==3 and len({r['identical_dso_sha256'] for r in stock+cand})==1
    assert all(r['link_exit']==0 for r in stock+cand) and stock[0]['program_sha256']==cand[0]['program_sha256']
    assert [s['needed'] for s in stock]==[[s['input']] for s in stock] and all(s['program_exit']==42 for s in stock)
    assert len({j['program_sha256'] for j in stock})==2 and stock[1]['program_sha256']==stock[2]['program_sha256']
    assert cand[0]['program_exit']==42 and cand[0]['cache_events']==['miss']
    assert all(j['needed']==cand[0]['needed'] and j['cache_events']==['hit'] and j['loader_named_old_missing'] and
               j['program_exit']==127 and j['program_sha256']==cand[0]['program_sha256'] for j in cand[1:])
    assert all(set(k['call'] for k in j['calls_on_verified_output_fd'])=={'mmap','utimensat'} and
               not any(k['writable_mapping'] for k in j['calls_on_verified_output_fd']) for j in cand[1:])
    assert all({'ftruncate','fchmod','mmap'}<=set(k['call'] for k in j['calls_on_verified_output_fd']) and
               any(k['writable_mapping'] for k in j['calls_on_verified_output_fd']) for j in stock)
    assert run['file_updates']['utime']==['0o4755','0o4755',True,True]
    for op in ['pwrite','truncate','truncate_and_chmod']:assert run['file_updates'][op]==['0o4755','0o755',True,True]
    capability=read('prior-file-capability.json')
    assert capability['stock']['capability_after'] is False and capability['candidate']['capability_after'] is True
    assert capability['stock']['native_elf']==capability['candidate']['native_elf']
    controls={r['case']:r for r in read('prior-archive-controls.json')}
    assert controls['new earlier archive wins']['exit']==21 and controls['unchosen member gains a symbol']['exit']==17
    assert all(controls[n]['events'][0].startswith('miss\t') for n in ('new earlier archive wins','unchosen member gains a symbol'))
    src=[v for k,v in controls.items() if k.startswith('filename-dependent script')];assert len(src)==2 and all(not v['events'] for v in src) and src[0]['elf']!=src[1]['elf']
    for case in ['pydantic-build','pydantic-test','ty-comment-test']:
        r=archive[case]
        assert r['stable_native_names']==r['original']['raw_native_member_count']==r['changed']['raw_native_member_count']==256
        assert r['original']['read_bytes']==r['changed']['read_bytes']==35576
        assert r['original']['raw_bytes']!=r['changed']['raw_bytes']
        different=len(r['native_size_changes']);assert different==(0 if case=='ty-comment-test' else 2)
        assert (r['original']['stable_name_and_length_vector']!=r['changed']['stable_name_and_length_vector'])==bool(different)
        if different:assert r['patch_sha256']=='467330a56398032bfaed34cca5a89ed7de1a6459ddb95756180b16de69b912b1'
    return dict(commands_using_stock_and_candidate=6,same_byte_dso_rename_stock=[42,42,42],same_byte_dso_rename_v8=[42,127,127],
                owner_setid_probe_only=True,new_capability_probe=False,native_negative_filter_mapped_cost=False,
                parsed_bytes_per_real_archive=35576,cache_product_qualified=False)

if __name__=='__main__':print(json.dumps(verify(),sort_keys=True,indent=2))
