"""Verify the 48 untraced Ruff commands, paired inference, native call counts and ELF controls."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

base=Path(__file__).resolve().parent
sys.path.insert(0,str(base))
spec=importlib.util.spec_from_file_location('bench_analysis',base/'analyze.py');analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
read=lambda p:json.loads(p.read_bytes())
for line in (base/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1);p=base/name;assert p.resolve().is_relative_to(base)
    with p.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected,name
assert read(base/'complete.json')['source_clean'] and read(base/'complete.json')['matched_subjects']
s=read(base/'subjects.json');plan=read(base/'plan.json');record=read(base/'statistics.json');assert hashlib.sha256((base/'plan.json').read_bytes()).hexdigest()==s['plan']
reports={}
for mode,units,nelf,nexe in [('build',501,15,6),('test',619,110,102)]:
    rr=list(csv.DictReader((base/mode/'observations.csv').read_text().splitlines()));assert len(rr)==24
    orders=plan['cargo_companion_support'][mode]['orders'];times=[];witness={};samples={}
    for arm in ('parent','candidate'):
        witness[arm]=read(base/mode/arm/'witness.json');samples[arm]={v['pair']:v for v in read(base/mode/arm/'samples.json')}
        assert set(samples[arm])==set(range(1,13))
        current=witness[arm];initial=current['preflight']
        for k,r in current.items():
            assert len(r['elf'])==nelf and len(r['executables'])==nexe and set(r['executables'])<=r['elf'].keys()
            assert r['roster_sha256']==initial['roster_sha256'] and r['units']==units and r['successful_executables'].get('cargo',0)>0
            mechanism=record[mode]['mechanism'][arm][k];assert len(r['dirty'])==mechanism['dirty_units']
            assert len(r['linkers'])==mechanism['linkers'] and sum(c[1]=='full' for c in r['crates'])==mechanism['rustc_full'] and sum(c[1]=='link-only' for c in r['crates'])==mechanism['rustc_link_only']
            if k in ('preflight','final','restored-noop') and arm=='candidate':assert not any((r['dirty'],r['crates'],r['linkers'],r['target_processes']))
        for k in ('roster_sha256','compiler_messages_sha256','diagnostics','dirty','crates','linkers','executables'):
            assert initial[k]==current['final'][k]
        assert current['edit']['diagnostics']!=initial['diagnostics'] and initial['diagnostics']==current['restore']['diagnostics']
        assert [d['code'] for d in initial['diagnostics']['dataclass']]==['RUF008','RUF008'] and [d['code'] for d in current['edit']['diagnostics']['dataclass']]==['RUF008']
    def comparable(a,b):
        assert a.keys()==b.keys()
        for p,k in a.items():assert k['size']==b[p]['size'] and k['content_with_two_wild_fields_masked']==b[p]['content_with_two_wild_fields_masked'],p
    for phase in ('preflight','final','edit','restore'):
        comparable(witness['candidate'][phase]['elf'],witness['parent'][phase]['elf'])
    for arm in witness:comparable(witness[arm]['preflight']['elf'],witness[arm]['final']['elf'])
    for i,order in enumerate(orders,1):
        pair=[]
        for j,arm in enumerate(order,1):
            r=rr[(i-1)*2+j-1];v=samples[arm][i];assert [int(r['pair']),int(r['slot']),r['arm']]==[i,j,arm]
            assert v['slot']==j and v['ns']==int(r['elapsed_ns']) and v['command']==['cargo','+ohm',mode]+(['--no-run'] if mode=='test' else [])+['--locked','--offline']
            if arm=='candidate':assert v['elf_stats_unchanged'] and v['compile_status_count']==0
            pair.append(v['ns'])
        times.append(pair)
    reports[mode]=analysis.evaluate(orders,times)
analysis.holm(reports)
for mode,report in reports.items():assert all(v==record[mode][k] for k,v in report.items())
obs={a:read(base/'span-observer'/(a+'.json')) for a in ('candidate','parent')}
for current in obs.values():
    assert current['prime']['value']==current['before']['value']==current['restore']['value']==current['restored-noop']['value']
    assert current['edit']['value']==current['repeat']['value']==current['independent-edit']['value']!=current['before']['value']
assert {p:v['value'] for p,v in obs['candidate'].items()}=={p:v['value'] for p,v in obs['parent'].items()}
print(json.dumps(reports,indent=2))
