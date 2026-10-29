"""Independently check the native timing boundaries, stock widths, ELF pairing and queue-admission counts."""
from pathlib import Path
import collections,gzip,hashlib,importlib.util,json,math,statistics,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import one
from eligibility import one as choices
from saturation import compare,summarize
p=Path(__file__).resolve().parent
def read(n):
    f=p/n; b=f.read_bytes();return json.loads(gzip.decompress(b)if f.suffix=='.gz'else b)
def h(f):return hashlib.sha256(f.read_bytes()).hexdigest()
if (p/'SHA256SUMS').exists():
    for row in (p/'SHA256SUMS').read_text().splitlines():
        digest,file=row.split('  ',1);assert h(p/file)==digest
v=read('retained.json.gz');assert len(v)==12 and len({(r['b'],r['p'],r['a'])for r in v})==12
summ=read('retained-summary.json.gz');assert summ==json.loads(json.dumps([one(r)for r in v]))
s=read('signed-inputs.json'); assert s['wall_packet']=='f7d4068a9779c5206cfeb1bdd6c2554d7121e8433fffd977e0ea36913c2f3266'
for r in v:
    src=s['native_checks'][f"batch-{r['b']}-{r['p']}-{r['a']}.json.gz"];assert src['raw_source']==r['events_sha256']and src['qualification']==r['cert_sha256']
    assert len(r['bins'])==50 and sum(t['explicit_threads']for t in r['bins'].values())==0
    assert all(0<=a<b<=r['cargo'][1]for t in r['bins'].values()for a,b in [t['gcc'],t['rustc'],t['wild']])
    assert max(t['rustc'][1]for t in r['bins'].values())>=r['ron'][1]
tol=lambda a,b:math.isclose(a,b,abs_tol=1e-8)
for i in range(0,12,2):
    assert summ[i]['wild']['after_last_start_s']>summ[i+1]['wild']['after_last_start_s']
    assert summ[i]['wild']['pairwise_top10_overlap_s']<summ[i+1]['wild']['pairwise_top10_overlap_s']
    assert summ[i]['wild']['max_output_gb']<summ[i+1]['wild']['max_output_gb']
sat=read('saturation.json.gz');assert sat['grouped']==compare(v) and sat['summary']==summarize(sat['grouped'])
assert read('queue-fixed-threshold.json')==[choices(p,int(i),True)for i in (1,2,3)]
certs={}
for label in ('A2','B'):
    k=read(f'kernel-{label}.json.gz');certs[label]=cert=read(f'products-{label}.json.gz');meas=read(f'measured-{label}.json.gz');hdr=meas['header']
    assert k['no_lost_events'] and k['raw']==cert['raw_sensor']==meas['raw_sensor_sha']
    assert cert['counts']=={'cargo':1,'collect2':50,'gcc':50,'rustc-full':1,'rustc-link-only':50,'stock-wild':50}
    assert len(cert['rust_args'])==51 and len(cert['native_args'])==150 and len(cert['runtime'])==3
    assert cert['old_proven_rust_match'] and cert['old_proven_native_match']
    wild={int(pid):v for pid,v in k['wild_outputs'].items()};times={int(pid):v for pid,v in k['exec_start'].items()};ends={e[2]:e for e in k['events']if e[0]==4}
    widths={int(pid):rows[0][1]+1 for pid,rows in k['width'].items() if len(rows)==1};assert set(widths)==set(wild)and len(widths)==50
    assert {str(n):c for n,c in collections.Counter(widths.values()).items()}==hdr['total_allocated_by_target']
    assert sorted(widths.values())==([1]*50 if label=='A2'else[1]*49+[2])
    for pid,name in wild.items():
        r=meas['targets'][name];assert r['width']==widths[pid]and r['start_ns']==times[pid]and r['parent_succeeded_ns']==ends[pid][1]
        assert tol(r['cpu_ms'],sum(e[6][0]for e in ends.values()if e[4]==pid)/1e6)and tol(r['runqueue_wait_ms'],sum(e[6][1]for e in ends.values()if e[4]==pid)/1e6)
    last=max(ends[pid][1]for pid in wild);first=min(times[pid]for pid in wild);end=ends[k['root']][1]
    assert tol(hdr['native_span_ms'],(last-first)/1e6)and tol(hdr['last_Wild_to_Cargo_ms'],(end-last)/1e6)
    assert tol(hdr['last_launch_to_last_Wild_done_ms'],(last-max(times[pid]for pid in wild))/1e6)
    sr=[r for r in k['samples']if first<=r['t']<=end and any(times[pid]<=r['t']<ends[pid][1]for pid in wild)]
    assert max(sum(t[2]in wild and t[3]=='R'for t in r['tasks'])for r in sr)==hdr['peak_wild_R']
    assert max(sum(widths[pid]for pid in wild if k['width'][str(pid)][0][0]<=r['t']<ends[pid][1])for r in sr)==hdr['maximum_budget_live']
    assert all(50==len(meas[x]) for x in ['targets'])
    assert hdr['slow_overlapping_Cargo_syscalls_ms']['futex']<=hdr['last_Rust_to_Cargo_ms']+.00001
a,b=certs['A2'],certs['B']
assert a['rust_args']==b['rust_args']and a['native_args']==b['native_args']and a['typed_roster']==b['typed_roster']
assert a['runtime']['listing']==b['runtime']['listing']=='e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316'
assert all(a['outputs'][k]['fields']['normalized']==v['fields']['normalized'] and a['outputs'][k]['bytes']==v['bytes']for k,v in b['outputs'].items())
assert [k for k,v in a['outputs'].items()if v['sha256']!=b['outputs'][k]['sha256']]==['direxist_guard-b52833c6d634e45b']
initial=read('initial-rejection.json');assert (initial['units'],initial['fresh'],initial['counts_by_exe_basename']['ld.bfd'])==(619,548,58)and initial['smoke4_proved_two_workers']==2
delta=read('product-delta.json');assert len(delta)==9 and all(set(x['changed_sections'])=={'.rodata','.note.gnu.build-id'} for x in delta.values())
for label,cv in certs.items():
    assert set(delta)=={s for s,row in cv['outputs'].items()if not row['signed_product_equal']}
if (p/'zip-scope.json').exists():
    z=read('zip-scope.json'); assert z['all_content_and_member_metadata_equal'] and z['old_order']!=z['new_order'] and set(z['sections'])==set(delta)
    assert all(q['whole_ro_reconstructed'] and q['original_ro_sha']==delta[n]['changed_sections']['.rodata']['before'][3] and q['new_ro_sha']==delta[n]['changed_sections']['.rodata']['after'][3] for n,q in z['sections'].items())
streams=read('stream-boundaries.json');assert len(streams)==12
for x,z in zip(streams,v,strict=True):
    assert (x['b'],x['p'],x['a'])==(z['b'],z['p'],z['a'])
    want=max(j['rustc'][1]for j in z['bins'].values());assert x['rustc_ns']==want
    for rr in x['streams'].values():
        assert rr['duration_after_last_rustc_ns']==rr['last_write_ns']-want and rr['duration_before_cargo_exit_ns']==z['cargo'][1]-rr['last_write_ns']
print('PASS: 600 original signed native intervals, 3 queue replays, 100 supplementary native scopes, full argv/stock-width/output and first-copy rejection.')
