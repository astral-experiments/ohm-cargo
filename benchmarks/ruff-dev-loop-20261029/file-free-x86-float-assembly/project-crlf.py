#!/usr/bin/env python3
"""Project authenticated raw process records without publishing host paths."""
import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
def h(f):
    with f.open('rb') as b:return hashlib.file_digest(b,'sha256').hexdigest()
def c(o):return json.dumps(o,sort_keys=True,separators=(',',':')).encode()
def hb(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def safe_module(n,p):
    sp=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def noguess(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def jblob(p):return json.loads(gzip.decompress(p.read_bytes()))
def evidence(d,phase,control_hashes,reader):
    p=d/'reports';arm=next(x.name.split('-',1)[0] for x in p.iterdir() if x.is_dir() and x.name in ('W-'+phase,'F-'+phase));r=p/(arm+'-'+phase);term=read(r/'terminal.json');out={}
    for tag,old in sorted(term['results'].items()):
        x=read(r/(tag+'.json'));physical=reader.executions(r,tag,x)
        header=read(r/(tag+'.status.json'))
        comp=[];links=[]
        for j in x['jobs']:
            a=j['argv'];hashv=hb(b'\0'.join(os.fsencode(q) for q in a)+b'\0');comp.append({'role':j['kind'],'crate':j['name'],'argc':len(a),'argv_sha256':hashv})
        for j in x['wild']:
            a=j['argv'];leaf=Path(a[a.index('-o')+1]).name
            assert re.fullmatch(r'[A-Za-z0-9_.+-]+',leaf),leaf
            links.append({'output_basename':leaf,'argv_sha256':hb(b'\0'.join(os.fsencode(q) for q in a)+b'\0'),'argc':len(a)})
        assert len(comp)+len(links)==physical[1]
        data={'exit':header['exit'],'full':len(old['full']),'link_only':len(old['link_only']),'queries':old['queries'],'Wild':old['wild'],'all_compilers':comp,'all_linkers':links,'libm_full':old['full'].count('libm'),'literal_exec_trace_sha256':h(r/(tag+'.exec.json.gz')),'raw_proc_files':physical[0],'typed_json_sha256':hb(gzip.decompress((r/(tag+'.stdout.gz')).read_bytes())),'cargo_stderr_sha256':hb(gzip.decompress((r/(tag+'.stderr.gz')).read_bytes())),'source':x['state'],'worker_receipt':h(r/(tag+'.json'))}
        if tag=='invalid':
            diagnostics=reader.err(r,tag);ds=[]
            for q in diagnostics:
                spans=[{'line_start':sp['line_start'],'line_end':sp['line_end'],'column_start':sp['column_start'],'column_end':sp['column_end'],'text':sp['text'],'source_basename':Path(sp['file_name']).name} for sp in q['spans'] if sp['is_primary']]
                ds.append({'code':(q['code'] or {}).get('code'),'message':q['message'],'primary':spans})
            assert any(v['code']=='E0425' for v in ds)
            data.update(diagnostics=ds,raw_diagnostics_sha256=hb(c(diagnostics)))
        else:
            select=read(r/(tag+'.source-file-unit.json'));rn=read(r/(tag+'.reader-native.json'));vs=[]
            for item in select['variants']:
                vs.append({k:item[k] for k in ('features','profile','rlib_sha256','rmeta_sha256')} | {'rlib_path_commitment':hb(item['rlib'].encode()),'rmeta_path_commitment':hb(item['rmeta'].encode()),'selected':item['rlib']==select['selected']})
            chosen,=[item for item in vs if item['selected']];assert chosen['features']==['get-size','serde'] and chosen['rlib_sha256']==rn['rlib_sha256'] and rn['opened_selected_pids']
            markers=sorted([sorted(v['markers']) for v in x['libm_markers'].values()]);assert markers
            products=x['products'];assert products==old['product']==control_hashes['edited' if x['state']=='reverse-production-hunk' else 'original']
            observed={k:gzip.decompress((r/(tag+'-'+suffix+'.stdout.gz')).read_bytes()).decode() for k,suffix in [('public_consumer_stdout','reader'),('root_test_inventory','names'),('api_test_inventory','api-names'),('existing_test_stdout','single')]}
            # Rust's failed unit-test output can include the precise source path and is retained by SHA.
            tested=observed.pop('existing_test_stdout');needle='line_index::tests::line_end_exclusive_handles_different_line_endings'
            literal=[line for line in tested.splitlines() if line.startswith('test '+needle+' ... ')];assert len(literal)==1
            observed['existing_test_line']=literal[0];observed['existing_test_entire_stdout_sha256']=hb(tested.encode())
            data.update(typed=x['units'],full_products=products,libm_fresh=x['libm_fresh'],libm_markers=markers,variants=vs,reader_raw_trace=h(r/(tag+'.reader-exec.json.gz')),reader_real_compiler_argv_sha256=hb(b'\0'.join(os.fsencode(y) for y in rn['rustc_argv'])+b'\0'),actual_returned_reader_input_fds=len(rn['opened_selected_pids']),**observed)
        out[tag]=data
    custody=read(d/'private-raw'/phase/'custody.json')
    assert custody['worker_exit']==0 and custody['worker_terminal_sha256']==h(r/'terminal.json')
    return {'arm':arm,'phase':phase,'worker_terminal':h(r/'terminal.json'),'raw_originals':custody['all_originals_sha'],'raw_archive':custody['observation_archive'],'visits':out}
def provider(d):
    par=d/'reports/provider';pp=read(par/'terminal.json');agents={}
    for tag,v in pp['visits'].items():
        z=read(par/(tag+'.native.json'));assert z['receipt']==v['receipt']==h(par/(tag+'.trace.json.gz'))
        plain=jblob(par/(tag+'.trace.json.gz'));assert plain
        by=collections.Counter(n['kind'] for n in z['native'])
        complete=[{'role':j['kind'],'argc':len(j['argv']),'literal_argv_sha':hb(b'\0'.join(os.fsencode(a) for a in j['argv'])+b'\0')} for j in z['native']]
        nonempty={k:len(x) for k,x in v['provider_open_pids'].items()}
        idx={ 'expected_status':v['exit'],'native_trace':v['receipt'],'raw_pid_files':len(plain),'physical_native':complete,'counts':dict(by),'forced':v['forced'],'provider':v['kind'],'stock_Wild_family_successful_opens':nonempty}
        if v['kind']!='bad':idx.update(executable_and_dlopen_exits=v['runtime'],actual_selected_products=v['products'])
        agents[tag]=idx
    a=read(par/'basis.json')
    return {'terminal':h(par/'terminal.json'),'original_stock_gcc_script':a['script_sha256'],'provider_assembly':a['source_sha256'],'provider_object':a['object_sha256'],'valid_script':a['valid'],'malformed_script':a['bad'],'original_ruff_wasm_shared':a['typed_so_sha256'],'restored_public_reader':(par/'restored-public-reader.stdout').read_text().strip(),'original_still_absent':pp['private_provider_absent'],'visits':agents}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('screen',type=Path);ap.add_argument('control',type=Path);ap.add_argument('formal',type=Path);ap.add_argument('out',type=Path);ap.add_argument('--formal',action='store_true',dest='include');arg=ap.parse_args()
    f,w,b=arg.screen,arg.control,arg.formal;lookup=safe_module('raw_parser',f/'ops/compare.py')
    assert h(f/'comparison.json')=='a907ae31b363eaf30e05690ff00880b4879c267b5cdf7d759247354037b394ed' and read(f/'comparison.json')['screen_positive']
    ref=read(f/'verified.json');data={'screening':{},'formal':{},'provider':{}}
    for n,p in [('W',w),('F',f)]:
        data['screening'][n]={phase:evidence(p,phase,ref,lookup) for phase in ('warm','clean')}
    commitments={'control_qualified':h(w/'verified.json'),'candidate_qualified':h(f/'verified.json'),'screen_all':h(f/'comparison.json'),'screen_terminal':h(f/'controller/terminal.json'),'new_registration':h(b/'registration/SHA256SUMS'),'order':h(b/'registration/order.json')}
    if arg.include:
        terminal=read(b/'controller/terminal.json');assert terminal['exit']==0 and h(b/'result.json')==terminal['result']
        formal=read(b/'result.json');assert formal['pairs']==read(b/'registration/order.json')['pairs']
        commitments.update(formal_native_result=h(b/'result.json'),formal_controller=h(b/'controller/terminal.json'))
        for name,pin in formal['ordered_independent_visits'].items():
            d=b/'visits'/name;assert h(d/'verified.json')==pin and read(d/'exit.json')['exit']==0
            data['formal'][name]=evidence(d,'warm',ref,lookup)
            if name.startswith('01-'):data['provider'][name]=provider(d)
        decisions={k:formal[k] for k in ('pairs','paired_delta_F_minus_W','median_delta','statistic_sum','two_sided_balanced_randomization','passes','literal_single_less_libm_every_pair','elapsed_or_instruction_measurements')}
    else:decisions=None
    arg.out.mkdir(mode=0o700)
    with (arg.out/'native.json.gz').open('xb') as fd,gzip.GzipFile(filename='',mode='wb',mtime=0,fileobj=fd) as gz:gz.write(c(data)+b'\n')
    result={'sources':commitments,'data_sha256':h(arg.out/'native.json.gz'),'formal_decision':decisions,'screen_visits':16,'formal_visits':7*len(data['formal'])}
    with (arg.out/'readback.json').open('x') as x:json.dump(result,x,sort_keys=True,indent=2);x.write('\n')
    print(h(arg.out/'readback.json'),h(arg.out/'native.json.gz'))
if __name__=='__main__':main()

