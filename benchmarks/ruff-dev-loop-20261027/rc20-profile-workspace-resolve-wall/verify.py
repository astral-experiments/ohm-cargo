"""Validate scored native rows, off-clock guards, error results, and paired statistics."""

from collections import Counter
import copy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
import runpy
import statistics as st
import subprocess
import sys
import tomllib

HERE = Path(__file__).resolve().parent
NATIVE = runpy.run_path(str(HERE / 'native_execs.py'))
DIRECTIONS = runpy.run_path(str(HERE / 'directions.py'))
ARMS = {'A':'967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9',
        'B':'80356b8237d3089d3360b6de5abfc64a17e4b8d3f0ec1fb64e09254418b5c5e5'}
SOURCES = {'orig':'893b5ff55f23fde170f5079766ebbe20937419a24296394a6dd0f326b8ccba88',
           'edit':'cd6179ed534ae36214b5554461d767080c86a3dad2652f15f304ca31d4da77a2'}
LOCK = 'c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
ORACLES = {'build':['17 29 12','9fd6acb5896e86a2c59526eb0b1c63aa1b5cdd02f8fd0f50e9f7012540a2e53d'],
           'test':[['invalid_range_deserialization','range_serialization','size_serialization'],
                   '3806e14ac4f4fb8745b6d4bd90e98a08d287b01942ee26ee2e1fd87bc22efe1c']}
COUNTS = {'build':(1,1,2),'test':(19,15,24)}
ARGS = {'build':['build','-p','ruff_text_size','--locked','--offline'],
        'test':['test','-p','ruff_text_size','--features','serde','--test','serde','--no-run','--locked','--offline']}
GOOD_SIGNS = [1,-1,-1,1]


def need(value, case):
    if not value:
        raise ValueError(str(case))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    data = (HERE / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith('.gz') else data)


def rendered_json(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def metrics(pairs):
    reductions = [100 * (a-b)/a for a,b,_,_ in pairs]
    faster = sum(v>0 for v in reductions)
    slower = sum(v<0 for v in reductions)
    n = faster+slower
    sign_p = min(1.0, sum(math.comb(n,i) for i in range(min(faster,slower)+1)) / 2**(n-1))
    strata = {}
    for value, (_,_,source,order) in zip(reductions,pairs):
        strata.setdefault((source,order), []).append(value)
    need(len(strata)==4 and all(len(v)==8 for v in strata.values()), 'unbalanced strata')
    rnd = random.Random(0x0e398aa5)
    estimates = []
    for _ in range(20_000):
        draws = []
        for group in strata.values():
            draws.extend(rnd.choice(group) for _ in group)
        estimates.append(st.median(draws))
    estimates.sort()
    return {'n':len(pairs), 'parent_median_ms':st.median(a for a,_,_,_ in pairs)/1e6,
            'candidate_median_ms':st.median(b for _,b,_,_ in pairs)/1e6,
            'paired_median_ms':st.median((a-b)/1e6 for a,b,_,_ in pairs),
            'paired_reduction_pct':st.median(reductions),'bootstrap95_pct':[estimates[499],estimates[19499]],
            'sign_test_p_two_sided':sign_p,'faster_pairs':faster,
            'direction_medians_pct':{s:st.median(v for v,r in zip(reductions,pairs) if r[2]==s) for s in ('orig','edit')}}


def check_control(mode, label, item):
    hydration = label == 'C/00-prepare'
    rows = item['reports']
    need(list(map(json.loads,item['stdout'].splitlines()))==rows,'complete native stdout')
    normalized=NATIVE['native_execs'](item['trace'])
    remove_digest=lambda r:{k:v for k,v in r.items() if k!='argv_sha256'}
    need(list(map(remove_digest,normalized))==list(map(remove_digest,item['processes'])),'complete native exec stream and token counts')
    unit_count, artifacts, file_count = COUNTS[mode]
    kinds = Counter(row['reason'] for row in rows)
    expected = Counter({'compiler-artifact':artifacts,'build-finished':1})
    if mode == 'test':
        expected['build-script-executed'] = unit_count - artifacts
    need(kinds==expected and rows[-1]=={'reason':'build-finished','success':True}, (mode,label,kinds))
    apps = [r for r in rows if r['reason']=='compiler-artifact']
    filenames = {p for r in apps for p in r['filenames']}
    enrolled_roster=sorted([r['package_id'],r['target']['name'],r['target']['kind'],r['features']] for r in apps)
    need(enrolled_roster==item['worker_roster'],'all native package IDs, targets, features')
    need(len(filenames)==file_count and filenames=={'<arena>/'+name for name in item['files']}, (label,'output set'))
    need(len(item['files'])==file_count and all(re.fullmatch('[a-f0-9]{64}',v) for v in item['files'].values()), 'file digests')
    need(all(row['fresh'] == (not hydration) for row in apps), (label,'freshness'))
    need(sorted(item['worker_dirty_targets'])==sorted(row['target']['name'] for row in apps if not row['fresh']), (label,'dirty targets'))
    need(item['oracle']==ORACLES[mode], (label,'oracle'))
    if mode=='test':
        exe, = [r['executable'] for r in apps if r.get('executable') and r['target']['kind']==['test']]
        need(item['files'][exe.removeprefix('<arena>/')]==item['oracle'][1], 'tested ELF')
    else:
        need(sorted(item['files'].values())==[
            'af8f228d9e5e76c736b54649f65b2d4089f01edc16ee615df49142e8f373f9a9',
            'bf871a8505ccce290ad2c6afc929ec548017b104858c79d23a40702dc0c4b8e5'],
            'complete rlib and metadata')
    procs = item['processes']
    cmd = ARGS[mode]+['--message-format=json']
    need([(r['program'],r['cargo_args'])for r in procs[:2]]==[('cargo',['+ohm',*cmd]),('cargo',cmd)], 'positive Cargo execs')
    need(all(r['lines'][0]<=r['lines'][1] and re.fullmatch('[0-9a-f]{64}',r['argv_sha256']) for r in procs), 'native argv')
    workers = [sum(NATIVE[f](r) for r in procs) for f in ['is_compile','is_link']]
    need(workers==([artifacts,0 if mode=='build' else 6] if hydration else [0,0]),(mode,label,'native work',workers))
    if not hydration:
        need(len(procs)==2, (label,'extra native child'))
    if hydration and mode=='test':
        need(Counter(r['program'] for r in procs)=={'cargo':2,'rustc':23,'cc':6,'collect2':6,'ld.bfd':6,'build_script_build':4},'serde warm-up')
    stable_rows = []
    for r in apps:
        projected = {k:v for k,v in r.items() if k!='fresh'}
        stable_rows.append(json.dumps(projected,sort_keys=True))
    stable_scripts = sorted(json.dumps(r,sort_keys=True) for r in rows if r['reason']=='build-script-executed')
    return [sorted(stable_rows),stable_scripts,item['files'],item['oracle']]


def validate_mode(mode, item, with_stats=True):
    required_controls = {'C/00-prepare','C/00-frozen'} | {
        arm+'/'+tag for arm in 'AB' for tag in ['00-prepare','01-edited','02-restored','03-settled','99-terminal']}
    need(set(item['controls'])==required_controls, 'control roster')
    controls = [check_control(mode,tag,item['controls'][tag]) for tag in sorted(required_controls)]
    need(all(c==controls[0] for c in controls), 'cross-arm full products, features, scripts and oracle')
    es = item['enrollments'];need(set(es)==set('CAB'),'enrollment roster')
    common = {k:v for k,v in es['C'].items() if k not in ('cargo','raw_sha256')}
    for arm, e in es.items():
        need({k:v for k,v in e.items() if k not in ('cargo','raw_sha256')}==common, 'changed arm enrollment')
        need(e['cargo']==ARMS['A' if arm=='C' else arm] and e['units']==COUNTS[mode][0] and e['argv']==ARGS[mode] and
             (e['orig'],e['edit'],e['lock'])==(SOURCES['orig'],SOURCES['edit'],LOCK),'enrolled inputs')
        need(e['rust']=='5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511' and
             e['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','native tools')
    t=item['terminal']
    need(sha(rendered_json(t))==item['raw_terminal_sha256'] and (t['mode'],t['source'],t['lock'],t['base'],t['candidate'])==
         (mode,SOURCES['orig'],LOCK,ARMS['A'],ARMS['B']),'original terminal')
    need(len(t['events'])==len(item['slots'])==128,'slot count')
    visits={p:[] for p in ['edit','repeat','edit_plus_repeat']}
    for i in range(32):
        sequence='AB' if GOOD_SIGNS[i%4]==1 else 'BA'
        source='edit' if i%2==0 else 'orig'
        group=t['events'][4*i:4*i+4]
        ns={}
        for event,(arm,phase) in zip(group,((a,p) for a in sequence for p in ['edit','repeat'])):
            case=f'{arm}/{i:02}-{phase}'
            need((event['pair'],event['sequence'],event['source'],event['arm'],event['phase'])==(i,sequence,source,arm,phase),case)
            slot=item['slots'][case]; r=slot['native_row']; err=slot['stderr']
            need(type(r['ns']) is int and r['ns']>0 and r['ns']==event['ns'] and r['exit']==0, (case,'clock'))
            need(sha(rendered_json(r))==slot['raw_record_sha256'],'raw native elapsed row')
            need(slot['stdout']=='' and r['stdout']==sha(b'') and sha(err.encode())==slot['normalized_stderr_sha256'],case)
            meter = r'[0-9]+(?:[.][0-9]+)?s'
            if mode=='build':
                need(re.fullmatch(r'    Finished `dev` profile \[optimized \+ debuginfo\] target\(s\) in '+meter+r'\n',err) is not None and
                     sha(err.encode())==r['stderr'],(case,'plain build output'))
            else:
                exe, = [p for p,h in controls[0][2].items() if h==ORACLES['test'][1]]
                need(re.fullmatch(r'    Finished `test` profile \[optimized \+ debuginfo\] target\(s\) in '+meter+r'\n'
                                  +re.escape('  Executable tests/serde.rs (<arena>/'+exe+')\n'),err) is not None, (case,'test output'))
            ns[arm,phase]=r['ns']
        for phase in ['edit','repeat']:
            visits[phase].append((ns['A',phase],ns['B',phase],source,sequence))
        visits['edit_plus_repeat'].append((ns['A','edit']+ns['A','repeat'],ns['B','edit']+ns['B','repeat'],source,sequence))
    return {phase:metrics(v) for phase,v in visits.items()} if with_stats else None


def verify_all():
    data=load('wall-native.json.gz'); reported={r['workload']:r for r in load('reported-statistics.json')}
    subs=load('subjects.json')
    need(set(data['archives'])=={'v1'} and data['archives']['v1']['members']==885 and data['archives']['v1']['sha256']=='8d3d6a9ed202365bd5119a5a6039d3dc8f4b03c6d576610ff5591cc53be68d46','original 885-file archive')
    src=gzip.decompress((HERE/'ruff-Cargo.toml.gz').read_bytes()); lock=gzip.decompress((HERE/'ruff-Cargo.lock.gz').read_bytes())
    hunk=b'debug = "line-tables-only"\n# Avoid the local ThinLTO that Cargo enables at nonzero optimization levels.\nlto = "off"\n'
    section=b'[profile.fast-test]\ninherits = "dev"\nopt-level = 1\n'
    need(src.count(hunk)==2 and src.count(section+hunk)==1 and sha(src)==SOURCES['orig'] and sha(src.replace(section+hunk,section))==SOURCES['edit'],'exact historical profile')
    need(sha(lock)==LOCK and len(lock)==138994 and len(tomllib.loads(lock.decode())['package'])==553,'lockfile')
    need(subs['patch_sha256']==sha((HERE/'historical.patch').read_bytes()) and subs['ruff_license_sha256']==sha((HERE/'RUFF-LICENSE').read_bytes()),'source capture')
    need(sha((HERE/'design.md').read_bytes())==subs['original_design_sha256'] and sha((HERE/'reported-statistics.json').read_bytes())==subs['original_analytical_result_sha256'],'design/analysis')
    need(sha((HERE/'analyze.py').read_bytes())==subs['original_analysis_sha256'] and
         sha((HERE/'consumer.rs').read_bytes())=='0ea9c24d5e734ead9f5857669e17fabedeb582fe349197955056d2e9b7527dd1','original calculator and actual external reader')
    raw=load('raw-file-index.json.gz')
    need(len(raw)==885,'complete raw file manifest')
    counts={}
    for mode,m in data['modes'].items():
        prefix='toml-'+mode+'-v1/'
        for tag,c in m['controls'].items():
            name=prefix+tag+'.exec'
            events=c['processes']
            counts[name]={'count':len(events),'files':len(c['files']),'links':sum(NATIVE['is_link'](r) for r in events),
                'oracle':c['oracle'],'programs':dict(Counter(r['program'] for r in events)),
                'roster':sum(r['reason']=='compiler-artifact' for r in c['reports']),
                'sha256':c['raw_trace_sha256'],'source_rustc':sum(NATIVE['is_compile'](r) for r in events)}
            for suffix,key in (('.exec','raw_trace_sha256'),('.jsonl','raw_stdout_sha256'),('.json','raw_worker_sha256'),('.stderr','raw_stderr_sha256')):
                need(raw[prefix+tag+suffix]['sha256']==c[key], 'native raw-file binding')
        for tag,c in m['slots'].items():
            for extension, expected_sha in (('.json',c['raw_record_sha256']),('.stdout',c['native_row']['stdout']),('.stderr',c['native_row']['stderr'])):
                need(raw[prefix+tag+extension]['sha256']==expected_sha,'ordinary raw-file binding')
        need(raw[prefix+'terminal.json']['sha256']==m['raw_terminal_sha256'],'terminal wire hash')
    need(sha((HERE/'full-native-counts.json').read_bytes())==data['original_complete_exec_capture_sha256']==
         '22651ac8f6222e83e60b970b5ad501c558bf70b75fc3827447857720633a3ce0' and counts==load('full-native-counts.json'),'independent role counts')
    for mode in ['build','test']:
        value=validate_mode(mode,data['modes'][mode])
        r=reported[mode]
        need(value==r['metrics'] and r['data_sha256']==data['modes'][mode]['raw_terminal_sha256'] and
             (r['units_in_plan'],r['artifacts'],r['declared_files'])==COUNTS[mode] and r['oracle']==ORACLES[mode],(mode,'independent calculation',value,r))
    need(DIRECTIONS['describe'](data['modes'])==load('directions.json'), 'all order, direction and extreme values retained')
    need(subs['build']['source']=='97e5acfb7b8eefde1ce07d703fc4849d6d36e37c' and subs['build']['cargo_sha256']==ARMS['B'] and
         subs['build']['literal_compiler_commands_equal'] and (subs['build']['ordered_external_inputs'],subs['build']['independent_native_files'])==(239,335),'authentic matched artifacts')
    for name,r in reported.items():
        e=r['metrics']['edit']
        need(e['faster_pairs']==32 and e['bootstrap95_pct'][0]>0 and e['sign_test_p_two_sided']<0.05,'registered success at edited endpoint')
        ci=r['metrics']['repeat']['bootstrap95_pct']
        need(ci[0]<0<ci[1],'unchanged repeat uncertainty')
    logged=load('native-mechanism.json.gz')
    ref=runpy.run_path(str(HERE/'mechanism.py'))['verify'](logged,data)
    need(ref==load('mechanism-results.json') and logged['archive']['sha256']=='4e1041cdbb131277c357df61d3f8edc5d27446357e5f319718f0dd2e7be5b029','separate post-clock mechanism')
    need(sha((HERE/'mechanism-design.md').read_bytes())==logged['design_sha256']=='76df5ee06877190c555a75184a04e6e4df809c5f51ab9b41659181771b9877df','mechanism enrollment')
    for m,row in ref.items():
        need((row['commands'],row['A_edited_commands'],row['B_edited_commands'],row['A_edited_full'],row['B_edited_full'],row['A_edited_hits'],row['B_edited_hits'])==(20,4,4,4,0,0,4), 'actual independent edit dispositions')
        deltas=list(row['different_product_sha256_between_independent_common_warmups'])
        need(len(deltas)==1 and deltas[0].endswith('.rlib') and 'ruff_text_size' in deltas[0],'genuine observable intermediate inequality')
    with (HERE/'timings.csv').open(newline='') as stream:
        flat=list(csv.DictReader(stream))
    expected=[]
    for mode in ('build','test'):
        m=data['modes'][mode]
        for e in m['terminal']['events']:
            tag=f"{e['arm']}/{e['pair']:02}-{e['phase']}"
            r=m['slots'][tag]['native_row']
            expected.append(dict(workload=mode,pair_zero_based=str(e['pair']),sequence=e['sequence'],root_manifest=e['source'],
                                 arm=e['arm'],phase=e['phase'],elapsed_ns=str(e['ns']),exit=str(r['exit']),
                                 raw_stdout_sha256=r['stdout'],raw_stderr_sha256=r['stderr']))
    need(flat==expected,'all 256 public CSV rows agree with independently verified clock receipts')
    receipt=load('verification.json')
    need(receipt['portable_csv_sha256']==sha((HERE/'timings.csv').read_bytes()) and receipt['reported_native_digest_differences']==ref
         and receipt['matched_product_files']==ARMS and receipt['wall_archive']==data['archives']['v1'] and receipt['logging_archive']==logged['archive'],
         'separate portable verification receipt')
    return data


def self_test(data):
    def mutate(name,mode,op):
        item=copy.deepcopy(data['modes'][mode]);op(item)
        try: validate_mode(mode,item,False)
        except (ValueError,KeyError,AssertionError): return
        raise AssertionError('accepted tampering: '+name)
    mutate('nanosecond mismatch','build',lambda d:d['slots']['B/02-repeat']['native_row'].update(ns=1))
    def wrong_order(d):
        d['terminal']['events'][1].update(sequence='BA')
        d['raw_terminal_sha256']=sha(rendered_json(d['terminal']))
    mutate('wrong order','test',wrong_order)
    def wrong_stderr(d):
        d['slots']['B/00-edit'].update(stderr='success\n',normalized_stderr_sha256=sha(b'success\n'))
    mutate('wrong normalized stderr','test',wrong_stderr)
    mutate('missing final declared file','build',lambda d:d['controls']['A/99-terminal']['files'].pop('products/debug/libruff_text_size.rlib'))
    mutate('false warm oracle','test',lambda d:d['controls']['B/01-edited'].update(oracle=[['wrong'],'0'*64]))
    mutate('native work on a fresh arm','test',lambda d:d['controls']['B/01-edited']['processes'].append(d['controls']['C/00-prepare']['processes'][-1]))
    def erase_row(d):
        event=d['terminal']['events'][82]
        need((event['arm'],event['phase'],event['pair'])==('B','edit',20),'pair identity')
        d['terminal']['events'].pop(82)
        d['raw_terminal_sha256']=sha(rendered_json(d['terminal']))
    mutate('deleted observation','build',erase_row)
    def discard_prefix(d):
        d['controls']['B/03-settled']['trace']=''
    mutate('native stream withheld','build',discard_prefix)
    def wrong_feature(d):
        d['controls']['A/02-restored']['worker_roster'][0][3]=['false-feature']
    mutate('changed selected feature','test',wrong_feature)

    def corrupt_native_log():
        logged=load('native-mechanism.json.gz')
        row=logged['modes']['test']['commands']['A/04-reverse']
        row['stderr']=row['stderr'].replace('resolve_with_registry:resolve_with_previous:register_patch_entries:', 'removed_full:',1)
        try: runpy.run_path(str(HERE/'mechanism.py'))['verify'](logged,data)
        except ValueError: return
        raise AssertionError('accepted altered post-clock resolver trace')
    corrupt_native_log()


if __name__=='__main__':
    data=verify_all()
    if '--self-test' in sys.argv:
        self_test(data)
        print('Rejected ten altered clocks, order, streams, artifacts, oracle, jobs, roster, trace, feature and resolver evidence controls.')
    print('Verified 256 whole-Cargo clocks, 24 off-clock native guards, 40 separate resolver observations, 885 primary archive members, and all six paired intervals.')
