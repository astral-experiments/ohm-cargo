#!/usr/bin/env python3
"""Verify the 40 ordinary source, native shadow, recovery and independently empty visits."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
HERE=Path(__file__).resolve().parent
E2E='ty_server/test/e2e'
INVENTORY='76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52'
STOCK_WILD='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
FRONT='fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512'
CARGO={'K':'e13f1b2aa269918308b14045b60f20871c48d92adee3c421c84debb1a5426e6a','U':'0970956820c02581cfbf2628bf469b6629c2eec31b9e5ebe10837c497aeb1187'}
CASES={'inlay_hints::default_inlay_hints','notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell'}
HEX=re.compile(r'[a-f0-9]{64}')
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def verify(data,binding,roster,pins,plan):
    fixed={'/'.join([r['package'],r['kind'],r['target']]) for r in roster};assert len(fixed)==50 and E2E in fixed
    expected={a+suffix for a in CARGO for suffix in ('','-focus','-edited-clean')}
    assert set(data['lanes'])==expected==set(binding['lanes']) and binding['physical_full_source_qualified'] is True
    assert binding['physical_reopened_native_products']==len(data['bodies']) and all(d['copies']>=1 for d in data['bodies'].values())
    assert binding['num_commands']==sum(map(len,data['lanes'].values()))==40
    assert len({digest((HERE/(n+'.rs')).read_bytes()) for n in ('original','edited','invalid')})==3
    assert pins['source_sha256']=={n:digest((HERE/(n+'.rs')).read_bytes()) for n in ('original','edited','invalid')}
    assert digest((HERE/'historical.patch').read_bytes())==pins['historical_patch_sha256']
    total=0
    for lane,order in data['lanes'].items():
        arm=lane[0];mode='focus' if lane.endswith('-focus') else 'empty' if lane.endswith('-edited-clean') else 'provider50';assert len(order)==len(plan['orders'][mode])
        for v,(label,state,provider,force) in zip(order,plan['orders'][mode]):
            assert (v['case'],v['source'],v['provider'],bool(v['forced']),v['mode'])==(label,state,provider,force,mode)
            assert v['source_SHA256']==pins['source_sha256'][state]
            assert v['arm']==arm and v['raw']['trace_files']>0 and HEX.fullmatch(v['raw']['kernel_commitment'])
            total+=v['raw']['trace_files']
            counter=Counter()
            for role,name,argv,img in v['native']:
                assert HEX.fullmatch(argv) and HEX.fullmatch(img)
                if role in ('full','cached','probe'):assert img==FRONT and (role=='probe' or name is not None)
                if role=='cargo':assert img==CARGO[arm]
                if role=='wild':assert img==STOCK_WILD
                counter[role]+=1
            assert dict(counter)==v['counts'] and counter['cargo']==1
            assert len(v['selected_native'])==len(set(v['selected_native'].values())) and set(v['selected_native'].values())<={row[2] for row in v['native'] if row[0]=='wild'}
            rc=101 if provider=='malformed' or state=='invalid' else 0
            assert v['cargo']==rc and 0<=v['fresh']<=v['typed']
            if rc==101:
                assert not v['outputs']
                if state=='invalid':
                    assert E2E not in v['selected_native'] and v['invalid'] and all(d['code']=='E0308' and any(s['line_start']==s['line_end']==22 for s in d['primary_spans']) for d in v['invalid'])
                else:
                    assert counter['wild']>0 and v['native_diagnostic']=='OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT'
            else:
                assert v['typed']==(619 if mode=='provider50' else 300)
                assert set(v['outputs'])==(fixed if mode=='provider50' else {E2E})
                if mode=='empty' or mode=='focus' and label=='01-original':assert v['fresh']==0
            if v.get('actual_Wild_family_successful_opens'):
                opened=v['actual_Wild_family_successful_opens']
                assert mode=='focus' and label in ('09-valid','11-malformed') and opened['script']>=1 and bool(opened.get('object'))==(provider=='valid')
            for name,row in v['outputs'].items():
                body=data['bodies'][row['body']];assert body['bytes']==row['bytes'] and row['list_exit']==body['returncode'] and row['list']==body['stdout']
                assert bool(row['linked'])==(name in v['selected_native'])
                if provider=='valid':
                    assert row['list_exit']==83 and row['list']==digest(b'') and row['linked']
                else:
                    assert row['list_exit']==0
                    if name==E2E:
                        assert row['list']==INVENTORY and set(row['tests'])==CASES
                        for test,t in row['tests'].items():
                            assert digest(t['stdout'].encode())==t['sha256'] and 'test '+test+' ... ok' in t['stdout'].splitlines()
                            assert '199 filtered out' in t['stdout'] and HEX.fullmatch(t['stderr_sha256'])
                        if mode!='provider50':assert all(HEX.fullmatch(v['same_generation_reader'][g]) for g in ('db','parser','result','stderr_sha256'))
    assert total==binding['native_trace_files']
    for a in CARGO:
        warm={r['case']:r for r in data['lanes'][a+'-focus']};cold,=data['lanes'][a+'-edited-clean']
        body=lambda name:warm[name]['outputs'][E2E]['body']
        assert body('01-original')==body('06-restored')==body('12-remove')==body('14-final-remove')
        assert body('02-edited')==body('03-edited-repeat')==body('05-recovery')==cold['outputs'][E2E]['body']
        assert body('09-valid')==body('10-forced-valid') and len({body('09-valid'),body('02-edited'),body('01-original')})==3
        assert warm['09-valid']['actual_Wild_family_successful_opens']['object'] and warm['11-malformed']['actual_Wild_family_successful_opens']['script']
        whole={r['case']:r for r in data['lanes'][a]}
        for n in fixed:
            b=lambda name:whole[name]['outputs'][n]['body']
            assert b('01-native-valid')==b('03-forced-valid')!=b('02-remove')
            assert b('02-remove')==b('05-remove')==b('07-final-remove')
    for suffix in ('-focus','-edited-clean',''):
        for x,y in zip(data['lanes']['K'+suffix],data['lanes']['U'+suffix]):
            assert x['case']==y['case'] and x['cargo']==y['cargo'] and set(x['outputs'])==set(y['outputs'])
            for n in x['outputs']:
                assert all(x['outputs'][n][q]==y['outputs'][n][q] for q in ('body','bytes','list_exit','list'))
            if x.get('invalid'):assert x['invalid']==y['invalid']
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    files={}
    for line in (HERE/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1);assert n not in files and re.fullmatch(r'[A-Za-z0-9_.-]+',n) and digest((HERE/n).read_bytes())==h;files[n]=h
    assert set(files)=={p.name for p in HERE.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    raw=gzip.decompress((HERE/'observations.json.gz').read_bytes());data=json.loads(raw);binding=read(HERE/'receipt.json')
    assert binding['native_argv_projection']==files['observations.json.gz'];extra=(binding,read(HERE/'fifty-targets.json'),read(HERE/'source.json'),read(HERE/'control-plan.json'))
    verify(data,*extra)
    cwd=read(HERE/'generated-list-cwd-control.json');assert cwd['two_disjoint_cwd_same_memfd_and_env']
    assert cwd['data']['empty']['exit']==101 and not cwd['data']['empty']['matches_original_listing']
    assert cwd['data']['original-package']['exit']==0 and cwd['data']['original-package']['matches_original_listing']
    example=next(v for v in data['lanes']['K'] if v['case']=='02-remove')['outputs']['ruff_mdtest/test/mdtest']
    assert example['body']==cwd['full_original_ELF'] and example['list']==cwd['original_listing_SHA256']
    for item in data['bodies'].values():assert item['package_directories'] and all(not Path(z).is_absolute() and '..' not in Path(z).parts for z in item['package_directories'])
    failures=read(HERE/'reported-native-errors-v1.json')
    errors={scope+'/'+v['case']:v for scope,rows in data['lanes'].items() for v in rows if v['provider']=='malformed'}
    assert set(errors)==set(failures) and len(errors)==8
    for key,v in failures.items():
        row=errors[key]
        assert v['exit']==row['cargo']==101 and v['native_diagnostic']==row['native_diagnostic']
        assert v['original_stdout_sha256']==row['raw']['stdout'] and v['original_stderr_sha256']==row['raw']['stderr']
        assert v['typed_reports'] and v['cargo_error_summaries'] and all(HEX.fullmatch(t['complete_original_diagnostic_sha256']) for t in v['typed_reports'])
        if '-focus/' in key:assert {t['target'] for t in v['typed_reports']}=={'e2e'}
    if args.self_test:
        for attack in ('failed-link','cached-job','source-error','cold-elf','provider-exit'):
            d=deepcopy(data)
            if attack=='failed-link':d['lanes']['K'][3]['cargo']=0
            elif attack=='cached-job':d['lanes']['U'][0]['counts']['cached']=1000
            elif attack=='source-error':d['lanes']['U-focus'][3]['invalid'][0]['primary_spans'][0]['line_start']=23
            elif attack=='cold-elf':d['lanes']['U-edited-clean'][0]['outputs'][E2E]['body']=d['lanes']['U-focus'][0]['outputs'][E2E]['body']
            else:d['lanes']['U'][0]['outputs'][E2E]['list_exit']=0
            try:verify(d,*extra)
            except (AssertionError,ValueError,KeyError,TypeError):continue
            raise ValueError('mutation accepted: '+attack)
    print('Verified',binding['num_commands'],'ordinary Cargo calls,',binding['native_trace_files'],'kernel thread records and',len(data['bodies']),'retained native programs.')
if __name__=='__main__':main()

