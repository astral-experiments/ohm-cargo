"""Recompute the syscall totals, source/output gates and process-window bounds using only this packet."""
from collections import Counter
from pathlib import Path
import gzip, hashlib, json, math, re, statistics
ROOT=Path(__file__).resolve().parent
def read(name):
    b=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
sha=lambda b:hashlib.sha256(b).hexdigest()
for row in (ROOT/'SHA256SUMS').read_text().splitlines():
    digest,_,name=row.partition('  ')
    assert sha((ROOT/name).read_bytes())==digest,name
inputs=read('input-receipts.json')
assert {m:d['groups']['ruff_wasm']['input_bytes']+d['groups']['ty_wasm']['input_bytes'] for m,d in inputs.items()}=={m:d['combined_bytes'] for m,d in inputs.items()}
static=inputs['build']; assert static['distinct_inputs']==752 and static['combined_bytes']==1715773489
runs=read('successful-reads.json.gz');classed=read('successful-read-classes.json')
expect={'B':418654,'C':3417849932}
for k,v in runs.items():
    assert v['complete_trace_shards_sha256']==classed[k]['complete_trace_shards_sha256']
    facts=v['paths'];assert len(facts)==static['distinct_inputs'];assert all(re.fullmatch('[a-f0-9]{64}',a) for a in facts)
    assert sum(p['size']for p in facts.values())==static['distinct_bytes']
    role=v['groups']['cargo']; assert sum(p['bytes']for p in facts.values())==role['transitive_reads']==expect[v['arm']]
    assert sum(p['calls']for p in facts.values())==role['transitive_read_syscalls']
    for n,detail in static['groups'].items():
        assert sum(f['size'] for f in facts.values() if n in f['closures'])==detail['input_bytes']
    for n,group in v['groups'].items():assert not (n=='cargo' and (group.get('copy_file_range_returned_bytes_all',0) or group.get('sendfile_returned_bytes_all',0)))
assert len(set(r['groups']['ld.bfd']['mapped_lengths_transitive'] for r in runs.values()))==1
phases={t['markers'][0]:t['conditional_relative_to_own_sampled_compiler'] for t in runs['C-io-edit']['cargo_threads'].values() if len(t['markers'])==1}
assert len(phases)==2 and not any(x['inside_sampled_compiler'] for x in phases.values())
assert [sum(x[k] for x in phases.values()) for k in ('before_first_sample','after_last_sample')]==[1701661125,1715770153]
inv=read('raw-file-inventory.json.gz')
assert [len(q['probes'])for _,q in sorted(inv.items())]==[6,6,1,6]
for group,q in inv.items():
    assert q['seed_counts'] and set(q['seed_counts'].values())=={922}
    for label,v in q['probes'].items():
        assert v['status']==0 and v['reported_units']==v['fresh']['units']==v['fresh']['fresh']==501
        assert v['fresh']['jobs']==v['fresh']['wild']==0 and v['fresh']['elf_files']==15
        assert v['comparison']['raw_equal']==15 and not v['comparison']['allowed_elf_differences']
        assert v['driver']=='63145e253973980f3786ce562b2342d2590b4a783256e4197e8ffacdf7d110fa'
        assert v['cargo']==q['armed']['arms'][label[0]]['cargo_sha256']
for name,key,src in [('nonptrace-timelines.json.gz','mixed-critical-light-v1','sample_sha'),('per-worker-observations.json.gz','mixed-critical-workers-v2','sample_sha'),('first-physical-worker-edit.json.gz','mixed-critical-workers-v1','sample_sha')]:
    for label,v in read(name).items():
        assert v[src]==inv[key]['probes'][label]['files']['samples.jsonl.gz']['sha256']
        assert len([r for r in v['native'] if r['role']=='rustc'])==9
        assert len({r['target']for r in v['native'] if r['role']=='wild'})==8
for label,r in read('exact-exec.json.gz').items():
    assert r['rustc_count']==9 and r['wild_count']==8
    assert not any(v['sigchld_linux_clock_t_ticks'] and v['sigchld_linux_clock_t_ticks'][0] for v in r['processes'])
    mix=[v for v in r['processes'] if v['kind']=='rustc' and v['target'] in ['ruff_wasm','ty_wasm']]
    assert len(mix)==2 and len(set(q['compiler_kind'] for q in mix))==1
rows=read('per-worker-observations.json.gz');summ=read('attribution.json');assert len(rows)==6
ty=[];latest=[]
for n,r in rows.items():
    assert len(r['cargo_task_flows'])==2
    for z in r['cargo_task_flows']:
        data=z['samples'];bill=z['source_side_certified_post_bytes_for_edit'];lo=next(i for i,x in enumerate(data) if x['rchar_rel']>=bill*.01);hi=next(i for i,x in enumerate(data) if x['rchar_rel']>=bill*.99)
        cycle=[round(data[hi-1]['at']-data[lo]['at'],6),round(data[hi]['at']-data[lo-1]['at'],6)]
        assert z['post_98_coverage_interval_s']==cycle and z['target'] in ('ruff_wasm','ty_wasm')
        assert z['compiler_exit_to_artifact_s']==[round(z['artifact_end']-z[k],6) for k in ('first_without_child','last_with_child')]
        if z['target']=='ty_wasm':
            ty.append(cycle);latest.append(z['compiler_exit_to_artifact_s'])
summary=lambda seq:[round(statistics.median(x[i] for x in seq),6) for i in (0,1)]
assert summary(ty)==summ['descriptive_ty_98pct_median_s'] and summary(latest)==summ['descriptive_compiler_exit_to_artifact_median_s']
registered=read('registered-comparison.json');rows=registered['observations']['build'];assert len(rows)==20
med={arm:statistics.median(r['ns'][arm]/1e9 for r in rows) for arm in 'BC'}
gap=round(med['C']-med['B'],6);assert gap==summ['formal_build_median_difference_s']
assert sum(x[1]<gap for x in latest)==summ['upper_brackets_smaller_than_formal_build_gap']==4
print('Verified 752 input credentials, syscall byte totals, 19 qualified diagnostic commands, 12 native worker samples, and the registered control difference.')
