"""Recalculate every registered endpoint and independently verify the process/ELF gates."""
from collections import Counter,defaultdict
from pathlib import Path
import csv,hashlib,itertools,json,math,re,statistics,sys
D=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
read=lambda name:json.loads((D/name).read_bytes())
def csvrows(name):
    with (D/name).open(newline='') as f:return list(csv.DictReader(f))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
plan=read('sdk-prefetch-registration.json');sub=read('subjects.json');pins=plan['subject']
assert digest(D/'sdk-prefetch-registration.json')==sub['plan']=='628f3f6f7d96baf32b9c95c957c5e3585388235c5da2b24fbe7f0d5d82ed774c'
assert sub['affinity']=='0-3'
assert sub['sha256']=={'P':pins['golden'],'V':pins['earlier']['cargo_sha256'],'C':pins['candidate']['cargo_sha256'],
                         'rustc':pins['rustc'],'driver':pins['compiler_driver']}
assert digest(D/'observer-edit-screen1.patch')==pins['earlier']['v4_increment_sha256']==pins['candidate']['v4_increment_sha256']
assert digest(D/'observer-sdk-prefetch-screen1.patch')==pins['candidate']['sdk_increment_sha256']
assert digest(D/'sdk-prefetch-ron.py')==plan['inputs']['local_ron_fixture_source_sha256']
assert digest(D/'heldout-fixture-sha256.json')==plan['inputs']['synthetic_source_manifest_sha256']
for n,h in read('heldout-fixture-sha256.json').items():assert digest(D/'heldout-fixture'/n)==h
raw=[json.loads(x) for x in (D/'commands.jsonl').read_bytes().splitlines()];rs={r['phase']:r for r in raw}
assert len(rs)==len(raw)==227 and all(r['success'] for r in raw) and read('passed.json')['audited_repetitions']==96
q=read('trace-quality.json')
ex,helpers=csvrows('successful-execs.csv'),csvrows('checksum-workers.csv')
by=defaultdict(list);threaded=Counter()
for x in ex:by[x['phase']].append(x)
for x in helpers:threaded[x['phase']]+=1
assert len(ex)==q['successful_execs'] and len(helpers)==q['helper_starts']
assert len(by)==len([x for x in raw if not x['native']])==q['traced']==131
assert sum(x['native'] for x in raw)==q['ordinary']==96
assert set(q['unknown_unfinished_no_result'])<=set(by)
for r in raw:
    name=r['phase']
    if r['native']:assert name not in by and not r['observed_compiler_jobs'];continue
    calls=by[name]
    assert [int(c['ordinal']) for c in calls]==list(range(1,len(calls)+1))
    assert [(c['image'],c['local_process']) for c in calls[:2]]==[('rustup-cargo-proxy','1'),('cargo','1')]
    roster=sorted([dict(crate=c['crate'],mode=c['rustc_mode'],capture=c['capture']=='True',checksum=c['checksum']=='True')
                  for c in calls if c['crate']],key=lambda c:c['crate'])
    assert roster==r['observed_compiler_jobs'] and threaded[name]==r['worker_starts']
gold={False:rs['empty-0'],True:rs['empty-1']};rg=rs['empty-ron']
assert all(r['arm']=='P' for r in [*gold.values(),rg])
source=(D/'heldout-fixture/hold_shapes/src/types.rs').read_bytes()
assert hashlib.sha256(source).hexdigest()==gold[False]['source_sha256']
assert hashlib.sha256(source.replace(b'/// One private shape\n',b'/// One private shapes\n')).hexdigest()==gold[True]['source_sha256']
for n in ('hold_direct','hold_indirect','hold_plain'):
    assert (gold[False]['native_products'][n]['output']!=gold[True]['native_products'][n]['output'])==(n!='hold_plain')
    assert (gold[False]['native_products'][n]['sha256']!=gold[True]['native_products'][n]['sha256'])==(n!='hold_plain')
seenrows=[];stats={};readers={'hold_bridge','hold_direct'}
for ep in ('synthetic_noop','ron_noop','first_edit'):
    dirs=[];ratios=[];times={k:[] for k in 'VC'};starts=[];worker_counts={'V':Counter(),'C':Counter()}
    for block in plan['orders']:
        n=block['block'];dirs.append(block['edit_direction']);order=block[ep];starts.append(order)
        assert sorted(order)==['C','V'];state=(block['edit_direction']=='add')==(ep=='first_edit')
        vals={}
        for k in order:
            name=f'{n:02}-{ep}-{k}'
            nat,obs=rs['native-'+name],rs['audit-'+name]
            assert nat['arm']==obs['arm']==k and nat['native'] and not obs['native']
            for rr in (nat,obs):
                if ep=='ron_noop':
                    assert rr['test_executable']==rg['test_executable'] and rr['source_manifest']==rg['source_manifest']
                    assert any(p['name']=='dep-lib-ron' and p['complete'] and p['checksummed'] for p in rr['readers'])
                else:
                    assert rr['native_products']==gold[state]['native_products'] and rr['source_sha256']==gold[state]['source_sha256']
                    assert len(rr['readers'])==2 and all(p['complete'] and p['checksummed'] for p in rr['readers'])
            roster=obs['observed_compiler_jobs'];links=sum(e['image']=='ld.bfd' for e in by[obs['phase']])
            nh=obs['worker_starts'];worker_counts[k][nh]+=1
            if ep=='first_edit':
                assert nh==0 and len(roster)==5 and links==3
                assert {j['crate'] for j in roster if j['mode']=='full'}==readers|{'hold_shapes','hold_indirect'}
                assert {j['crate'] for j in roster if j['mode']=='relink'}=={'hold_plain'}
                assert {j['crate'] for j in roster if j['capture']}==readers
            else:
                assert not roster and links==0 and bool(nh)==(k=='C')
                assert not any(e['image']=='rustc' for e in by[obs['phase']])
            ns=nat['ns'];times[k].append(ns/1e6);vals[k]=ns
            seenrows.append((n,ep,order,k,ns))
        ratios.append(math.log(vals['V']/vals['C']))
    assert len(ratios)==16 and starts.count('VC')==starts.count('CV')==8
    reductions=sorted(-100*math.expm1(-x) for x in ratios)
    score=dict(n=16,v4_median_ms=statistics.median(times['V']),candidate_median_ms=statistics.median(times['C']),
        median_paired_reduction_pct=statistics.median(reductions),favorable=sum(x>0 for x in reductions),
        paired_median_interval_pct=[reductions[3],reductions[12]],checksum_helper_counts={k:dict(v) for k,v in worker_counts.items()})
    if ep=='first_edit':
        assert all(sum(q=='VC' for q,dd in zip(starts,dirs) if dd==direction)==4 for direction in ('add','remove'))
        score['lower_bound_above_minus_five_pct']=reductions[3]>-5
    else:
        chronology=[r if o=='VC' else -r for r,o in zip(ratios,starts)]
        target=sum(ratios);hits=total=0
        for a in itertools.combinations(range(16),8):
            chosen=set(a);stat=sum(x*(1 if i in chosen else -1) for i,x in enumerate(chronology))
            hits+=stat>=target-1e-12;total+=1
        assert total==12870;score.update(exact_one_sided_p=hits/total,upper_tail=hits,assignments=total)
    stats[ep]=score
prior=0
for i,ep in enumerate(sorted(('synthetic_noop','ron_noop'),key=lambda e:stats[e]['exact_one_sided_p'])):
    s=stats[ep];p=min(1,max(prior,(2-i)*s['exact_one_sided_p']));prior=p
    s['holm_p']=p;s['qualified']=p<.05 and s['favorable']>=13 and s['paired_median_interval_pct'][0]>0
from_csv=[(int(r['block']),r['endpoint'],r['order'],r['arm'],int(r['nanoseconds'])) for r in csvrows('native.csv')]
assert sorted(from_csv)==sorted(seenrows)
guard=read('candidate-sdk-mutation.json');assert guard['mtime_equal'] and guard['size_equal'] and guard['warm']==guard['empty']!=guard['before']
assert guard['changed_roster']==[dict(crate='hold_direct',mode='full',capture=True,checksum=True)] and not guard['initial_warm_roster']
sc=read('exploratory-reader-and-jobserver.json');assert sc['helper_counts_inherited_jobserver']=={'empty':0,'one':1} and sc['one_job_helpers']==0
ctrl=read('safety.json');assert ctrl['simultaneous/simultaneous-check']['status']!=0
assert all(r['status']==0 for n,r in ctrl.items() if n!='simultaneous/simultaneous-check')
report=D/'statistics.json'
if report.exists():assert json.loads(json.dumps(stats))==read('statistics.json')
print(json.dumps(stats,indent=2))
