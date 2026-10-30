#!/usr/bin/env python3
"""Verify native work, full source-dependent products, compiler diagnostics and the predeclared count test."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import re
import statistics
HERE=Path(__file__).resolve().parent
CASE='line_index::tests::line_end_exclusive_handles_different_line_endings'
def h(d):return hashlib.sha256(d).hexdigest()
def read(p):return json.loads(p.read_bytes())
def check(data,receipt,schedule):
    rawhex=re.compile(r'[a-f0-9]{64}')
    assert set(data['screening'])=={'W','F'} and receipt['screen_visits']==16
    pins=read(HERE/'prior.json');assert receipt['sources']['screen_all']==pins['W_F_comparison']
    ref=None;overalls={}
    def visit(arm,tag,j,reference=None):
        assert j['exit']==(101 if tag=='invalid' else 0) and j['raw_proc_files']>0
        c=Counter(x['role'] for x in j['all_compilers']);assert j['full']==c['full'] and j['link_only']==c['link_only'] and j['queries']==c['query']
        assert j['Wild']==len(j['all_linkers']) and j['libm_full']==sum(v['role']=='full' and v['crate']=='libm' for v in j['all_compilers'])
        for v in (*j['all_compilers'],*j['all_linkers']):assert v['argc']>0 and rawhex.fullmatch(v['argv_sha256'])
        for k in ('literal_exec_trace_sha256','typed_json_sha256','cargo_stderr_sha256','worker_receipt'):assert rawhex.fullmatch(j[k])
        if tag=='invalid':
            assert any(e['code']=='E0425' and 'ohm_missing_crlf_offset' in e['message'] and any(s['source_basename']=='line_index.rs' for s in e['primary']) for e in j['diagnostics'])
            return
        p=j['full_products'];assert j['typed']==334 and j['libm_markers']
        edited=j['source']=='reverse-production-hunk'
        assert j['public_consumer_stdout'].strip()==p['verdict']==('1 2 1 1' if edited else '1 1 1 0')
        assert j['existing_test_line']=='test '+CASE+(' ... FAILED' if edited else ' ... ok') and p['expected_test_exit']==(101 if edited else 0)
        assert h(j['root_test_inventory'].encode())==p['root_names'] and h(j['api_test_inventory'].encode())==p['api_names']
        assert CASE+': test' in j['root_test_inventory'].splitlines() and len(j['variants'])==2
        selected,=[v for v in j['variants'] if v['selected']];assert selected['features']==['get-size','serde'] and not selected['profile']['test'] and j['actual_returned_reader_input_fds']>0
        for v in j['variants']:
            assert rawhex.fullmatch(v['rlib_sha256']) and rawhex.fullmatch(v['rmeta_sha256'])
        if reference is not None:assert p==reference['edited' if edited else 'original']
    for arm,phases in data['screening'].items():
        warm=phases['warm']['visits'];clean=phases['clean']['visits'];assert len(warm)==7 and set(clean)=={'independent-edited'}
        this={'original':warm['original']['full_products'],'edited':clean['independent-edited']['full_products']}
        if ref is None:ref=this
        assert ref==this and ref['original']['root']!=ref['edited']['root'] and ref['original']['reader']!=ref['edited']['reader']
        for tag,info in {**warm,**clean}.items():visit(arm,tag,info,ref)
    assert data['screening']['W']['warm']['visits']['invalid']['raw_diagnostics_sha256']==data['screening']['F']['warm']['visits']['invalid']['raw_diagnostics_sha256']
    def fullmap(v):return Counter(j['crate'] for j in v['all_compilers'] if j['role']=='full')
    w=data['screening']['W']['warm']['visits']['edited'];f=data['screening']['F']['warm']['visits']['edited']
    assert w['libm_full']==1 and f['libm_full']==0 and f['libm_fresh'] is True and f['full']<w['full'] and f['Wild']<=w['Wild']
    decision=receipt['formal_decision']
    if decision is None:
        assert not data['formal'] and not data['provider'];return
    guards=(HERE/'compiler-guards.json').read_bytes()
    assert h(guards)==pins['upstream_12_asm_archive_arithmetic_native_checks']
    checked=json.loads(guards)
    assert checked['source']==pins['F_compiler'] and len(checked['receipts'])==12
    assert all(checked[k] is True for k in ('local_controls_passed','leaf_warm_clean_equal','both_Cargo_native_controls'))
    assert checked['suites']==[['ohm-checked-dep-info',0,18],['ohm-relink-assembler-inputs',0,7],['rdr-public-hash-proc-macro-utf8-subspan',0,3]]
    assert receipt['formal_visits']==112 and decision['pairs']==schedule and not decision['elapsed_or_instruction_measurements']
    assert len(schedule)==8 and Counter(schedule)==Counter({'WF':4,'FW':4})
    assert set(data['formal'])=={f'{i:02d}-{r}' for i,o in enumerate(schedule,1) for r in o}
    delta=[];chrono=[];narrow=True
    for i,o in enumerate(schedule,1):
        pair={}
        for arm in o:
            tag=f'{i:02d}-{arm}';p=data['formal'][tag]['visits'];assert len(p)==7
            for v,j in p.items():visit(arm,v,j,ref)
            assert p['invalid']['raw_diagnostics_sha256']==data['screening'][arm]['warm']['visits']['invalid']['raw_diagnostics_sha256']
            pair[arm]=p['edited']
        w,f=pair['W'],pair['F'];d=f['full']-w['full'];delta.append(d);chrono.append(d if o=='WF' else -d)
        narrow &= (w['libm_full']==1 and f['libm_full']==0 and f['libm_fresh'] is True and w['Wild']==f['Wild'] and w['link_only']==f['link_only'] and fullmap(w)==fullmap(f)+Counter({'libm':1}))
    assert decision['paired_delta_F_minus_W']==delta and decision['median_delta']==statistics.median(delta) and decision['statistic_sum']==sum(delta)
    null=[sum(n if i in iw else -n for i,n in enumerate(chrono)) for iw in itertools.combinations(range(8),4)]
    n=sum(abs(s)>=abs(sum(delta)) for s in null);assert decision['two_sided_balanced_randomization']==[n,70]
    assert decision['literal_single_less_libm_every_pair']==narrow and decision['passes']==(narrow and all(k<0 for k in delta) and n/70<0.05)
    assert set(data['provider'])=={'01-W','01-F'}
    for v in data['provider'].values():
        assert v['original_stock_gcc_script']=='69a56a9993b7729b29b274e65016031c81f2397f176ed5ad44d59bd50425e0bd' and v['original_still_absent'] and v['restored_public_reader']=='1 1 1 0'
        steps=v['visits'];assert set(steps)=={'valid','forced-valid','malformed','forced-malformed','restored'}
        for name,row in steps.items():
            assert row['counts']==dict(Counter(j['role'] for j in row['physical_native'])) and row['counts']['wild']>=1 and row['forced']==name.startswith('forced-')
            if row['provider']=='good':
                assert row['expected_status']==0 and row['executable_and_dlopen_exits']==[83,83] and all(row['stock_Wild_family_successful_opens'].values())
            elif row['provider']=='bad':assert row['expected_status']==101 and any(row['stock_Wild_family_successful_opens'].values())
            else:assert row['expected_status']==0 and row['executable_and_dlopen_exits']==[0,0]
        assert steps['valid']['actual_selected_products']==steps['forced-valid']['actual_selected_products']!=steps['restored']['actual_selected_products']
        assert steps['restored']['actual_selected_products']['so']==v['original_ruff_wasm_shared']
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--self-test',action='store_true');a=ap.parse_args()
    catalog={}
    for row in (HERE/'SHA256SUMS').read_text().splitlines():
        dig,name=row.split('  ',1);assert re.fullmatch(r'[A-Za-z0-9_.-]+',name) and name not in catalog and h((HERE/name).read_bytes())==dig;catalog[name]=dig
    assert set(catalog)=={p.name for p in HERE.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    receipt=read(HERE/'readback.json');assert receipt['data_sha256']==catalog['native.json.gz'];data=json.loads(gzip.decompress((HERE/'native.json.gz').read_bytes()));order=read(HERE/'order.json')['pairs']
    check(data,receipt,order)
    if a.self_test:
        for bad in ['compile','reader','native','invalid']+(['result','provider'] if receipt['formal_decision'] else []):
            test=deepcopy(data);bound=deepcopy(receipt)
            if bad=='compile':test['screening']['W']['warm']['visits']['edited']['full']+=1
            elif bad=='reader':test['screening']['W']['warm']['visits']['edited']['public_consumer_stdout']='1 1 1 0'
            elif bad=='native':test['screening']['F']['warm']['visits']['original']['all_linkers'].pop()
            elif bad=='invalid':test['screening']['F']['warm']['visits']['invalid']['diagnostics']=[]
            elif bad=='result':bound['formal_decision']['two_sided_balanced_randomization']=[0,70]
            else:test['provider']['01-F']['visits']['malformed']['expected_status']=0
            try:check(test,bound,order)
            except (ValueError,AssertionError,KeyError,TypeError):continue
            raise ValueError('mutated record accepted: '+bad)
    print('Verified screening and',receipt['formal_visits'],'formal ordinary observations.')
if __name__=='__main__':main()

