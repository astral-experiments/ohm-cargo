"""Verify independent timing, all per-command product-map receipts, and traced endpoint counts."""
from collections import Counter
from pathlib import Path
import gzip, hashlib, json, re, tarfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from statistics_replication import analyze

root = Path(__file__).resolve().parent
H = lambda b: hashlib.sha256(b).hexdigest()
read = lambda name: json.loads((root / name).read_bytes())
plan, summary, states = map(read, ('plan.json', 'complete.json', 'structural.json'))
allowed = read('checked-pairs.json')
assert summary['release'] == read('publication.json')
assert summary['release'] == {'native_commit': 'ac468544eb67449f1a90549d200bb14bcbdeead2',
                               'plan_commit':'8f5f1022ec360e920fcb7119c2fe157ad638a2b6',
                               'manifest':'44767c1a1b333cd5e7febd260011d519916e3df34e5e8232b503b1e1696cc7cf'}
assert summary['pairs'] == H((root / 'all.json').read_bytes())
assert H((root/'structural.json').read_bytes()) == read('amendment.json')['strict_native']
assert (summary['wall_commands'], summary['post_clock_native_controls']) == (24,4)
assert (root/'launch-score-h5-v3--exit').read_bytes() == b'0'
all_samples, end = [], 0
def validate_paths(ref, products, block, arm, changes=None):
    key = f'{block}-{arm}'
    mapping = states['physical_paths'][key]
    assert len(products) == 110 and set(products)==set(mapping.values())
    differed = {path for name,path in mapping.items() if products[path] != ref[name]}
    for name, hashes in allowed.items():
        assert products[mapping[name]] == hashes['BC'.index(arm)]
    if arm == 'C':
        assert not differed
    if changes is not None:
        assert differed == set(changes)
        for old, new, oldid, newid in changes.values():
            assert old != new and min(old,new)==0 and oldid!=newid and len(oldid)==len(newid)==64
def payload(arc, prefix, name):
    return arc.extractfile(prefix+'/'+name).read()
def harness(p, want):
    assert H(p('list.stdout')) == want[0] and H(p('list.stderr'))==want[1]
    assert len(p('list.stdout').splitlines()) == want[2] == 200
    assert b'inlay_hints::default_inlay_hints: test' in p('list.stdout')
for block, orders in enumerate(plan['orders'], 1):
    pairs = []
    with tarfile.open(root/f'clocks-block-{block}.tar.gz') as arc:
        assert len(arc.getnames()) == 12*8
        for idx, order in enumerate(orders, 1):
            observation = {}
            for arm in order:
                key=f'{block}-{arm}'
                base=f'qualified-wall-study-v3/wall/block-{block}/{idx:02}-{arm}'
                p=lambda n:payload(arc,base,n)
                clk,slot=json.loads(p('clock.json')),json.loads(p('verified.json'))
                assert clk['returncode']==0 and clk['argv']==plan['clock'] and clk['start']>end
                assert clk['stop']-clk['start']==clk['elapsed_ns']==slot['ns']>0
                end=clk['stop'];observation[arm]=slot['ns']
                assert not any(p(n)for n in ('outer.stdout','outer.stderr','stdout')) and not slot['stdout_bytes']
                assert H(p('stdout'))==slot['stdout'] and H(p('stderr'))==slot['stderr']
                assert b'Finished' in p('stderr') and b'Blocking waiting' not in p('stderr')
                n=len(re.findall(rb'^\s*Compiling\s+',p('stderr'),re.M))
                assert n==slot['compiler_progress_lines'] and (n>0)==(arm=='B')
                validate_paths(states['all_native_sha256'][key],slot['products'],block,arm,slot['variation'])
                assert slot['harness']==states['states'][key]['harness'];harness(p,slot['harness'])
            pairs.append({'order':order,'ns':observation})
    assert pairs==read(f'ledger-{block}.json');all_samples.append(pairs)
    for arm in 'BC':
        key=f'{block}-{arm}'; base=f'receipts/{key}/post-clock-h5-v3'
        with tarfile.open(root/f'post-clock-{key}.tar.gz') as arc:
            assert len(arc.getnames())==8
            p=lambda n:payload(arc,base,n)
            result, events, binding, roster=map(lambda f:json.loads(p(f)),('result.json','processes.json','binding.json','roster.json'))
            lines=[json.loads(x)for x in p('stdout').splitlines()]
            artifacts=[x for x in lines if x['reason']=='compiler-artifact']
            assert lines[-1]=={'reason':'build-finished','success':True}
            assert result['source']==plan['reference_source'] and result['command']==plan['clock']+['--message-format=json']
            assert result['status']==0 and (result['arm'],result['block'])==(arm,block)
            assert binding['hashes']['bin/cargo']==plan['images'][arm]['cargo_sha']
            assert set(binding['hashes'].values())==set(plan['images'][arm].values()) and 'Ohm SDK' in binding['effective_sdk']
            assert len(artifacts)==len(roster['units'])==result['guards']['units']==619
            assert sum(x['fresh'] for x in artifacts)==result['fresh']
            assert (len(roster['executables']),result['guards']['harness_profile'],result['guards']['nonharness_profile'])==(102,84,18)
            assert len(result['guards']['native_paths'])==110
            counted=Counter(x[0] for x in events['rustc'])
            assert all(x[-1]==0 for x in events['rustc']+events['wild'])
            actual=[counted['full'],counted['link-only'],len(events['wild']),result['fresh']]
            assert actual==states['states'][key]['terminal_counts']==([1,50,50,563] if arm=='B'else[0,0,0,619])
            assert result['rustc_full_names']==(['ron']if arm=='B'else[])
            validate_paths(states['all_native_sha256'][key],result['products'],block,arm)
            harness(p,result['oracle'])
assert all_samples==read('all.json')
assert analyze(all_samples,plan)==read('result.json')
print(json.dumps(read('result.json'),sort_keys=True))
