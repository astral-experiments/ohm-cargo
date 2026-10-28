"""Verify the portable native execution and fixed-input replay evidence without a toolchain."""
import collections
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
BASES={'observer':'0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322','composed':'813ba8a480bc6047d2effde2edff5fe5990781904ff453815ddc71aeb5e0e754'}
WILD='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
REG='508c6cee5b0f1962ab784ffbd953dc3b06699f51663633cb279d4e1bb4131d53'
V3='a420c1f388cfd5c42aa21632be89f128133acc42fbbfcb4ce1810d5e65495d18'
WALL='d72ba2931a74d09d83d98e6c7d0829a6ad15fa4c756e8c99b6e1b569294e6917'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(name):
    with gzip.open(HERE/name,mode='rb') as f:return json.load(f)
def check(b):assert len(bytes.fromhex(b))==32 and len(b)==64
def must_reject(fn):
    try:fn()
    except AssertionError:return
    raise ValueError('Accepted a negative control')


def check_body_sets(bodies):
    assert 1<=len(bodies)<=12
    untouched=set()
    for h,x in bodies.items():
        assert x['sha256']==h and len(x['unchanged_ranges'])==3
        check(x['normalized']);bound=x['bytes'];trace=[]
        for a,b,s in x['unchanged_ranges']:
            assert 0<=a<=b<=bound;check(s);trace.append([a,b])
        assert set(x['fields'])=={'build-id','rodata-sh-entsize'}
        for field,(pos,v) in x['fields'].items():
            raw=bytes.fromhex(v);assert len(raw)==(32 if field=='build-id' else 8)
            if field=='rodata-sh-entsize':assert int.from_bytes(raw,'little') in (0,1,2,4,8,16,32,64)
            trace.append([pos,pos+len(raw)])
        trace.sort();assert trace[0][0]==0 and trace[-1][1]==bound and all(end==nxt for (_,end),(nxt,_) in zip(trace,trace[1:]))
        untouched.add(digest([bound,x['unchanged_ranges'],x['normalized'],{f:v[0] for f,v in x['fields'].items()}]))
    assert len(untouched)==1


def verify():
    n=read('native.json.gz');v=read('replay.json.gz');g=json.loads((HERE/'h5-frozen-native-guard.json').read_bytes())
    assert n['wall_slots']==v['timing_slots']==g['timed_commands']==0
    assert n['subjects']==BASES and g['subjects']=={'B':BASES['observer'],'C':BASES['composed']} and n['native_manifest']==g['native_protocol']==V3 and g['plan_manifest']==WALL
    assert n['source']=='93526150df078af7dd8fc4226cdcc469539d2001' and n['release']['wild']==v['release_wild']==WILD
    assert n['sdk_archive']=='163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572'
    assert n['release']['rustc']=='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
    assert n['release']['driver']=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
    s=n['steps'];can=Path(n['canonical']);seed=n['v2_seed']
    assert n['seed_receipt']==seed['seed_complete']==n['v3_adoption']['seed']
    phases=[f'{q}-{a}' for q in ('selected','repeat') for a in BASES];seed_phases=['seed-cold','seed-repeat1','seed-repeat2']
    assert set(s)==set(phases+seed_phases)
    for key,r in s.items():
        selected=key in phases;seeded=key in seed_phases
        c=r['command'];assert c['code']==0 and c['edited']==selected
        assert c['binary']==BASES[c['arm']] and c['traced']==(key!='seed-cold')
        cmd=['cargo','+ohm','test','--no-run','--workspace']+(['--exclude','ty_server'] if seeded else [])+['--locked','--offline','-j8','--message-format=json']
        assert c['command']==cmd
        assert r['units']==len(r['rows'])==(619 if selected else 617)
        assert sum(e['fresh'] for e in r['rows'].values())==r['fresh']==(0 if key=='seed-cold' else 563)
        assert len(r['workspace'])==(110 if selected else 108) and len(r['exes'])==(102 if selected else 100)
        assert set(r['exes'])<=set(r['workspace']) and r['groups']==collections.Counter(v['owner'] for v in r['rows'].values())
        assert set(r['exes'])=={v['executable'] for v in r['rows'].values() if v['owner']=='workspace' and v['executable']}
        assert (r['ty_server']['fresh'] and r['ty_server']['sha']==s['seed-repeat2']['ty_server']['sha']) or key=='seed-cold'
        if selected:assert collections.Counter(e['test'] for e in r['rows'].values() if e['executable'])=={True:84,False:18}
        assert not set(r['workspace'])&set(r['registry'])
        assert len(r['registry'])==78 and digest({str(can/k):v for k,v in r['registry'].items()})==g['registry_sha256']==REG
        assert set(r['registry'].items())==set(s['seed-repeat2']['registry'].items())
        if seeded:
            exemplar=seed['commands'][key]
            assert r['receipt_sha256']['products.json']==exemplar['product_receipt'] and r['receipt_sha256']['stdout']==exemplar['stdout']
            assert digest({str(can/k):v for k,v in r['workspace'].items()})==exemplar['workspace_sha']
            assert not r['e2e']
        if key.startswith('selected-'):
            assert r['snapshots']['workspace']['copied']==110 and r['snapshots']['registry']['copied']==78
            assert all(x['private_inodes'] and x['all_bytes_match'] for x in r['snapshots'].values())
        if key!='seed-cold':
            physical=r['physical']
            assert len(physical)==len({p['pid'] for p in physical}) and all(p['exit']==0 for p in physical)
            assert r['counts']==collections.Counter(j['kind'] for j in physical)
            for p in physical:
                check(p['exec_sha256']);check(p['argv_sha256'])
            assert sum(p['kind']=='full' and p['target']=='ron' for p in physical)==1
        else:assert r['physical'] is None
    for tag in seed_phases[1:]:
        assert s[tag]['counts']=={'full':1,'link-only':48,'wild':48}
    for p in phases:
        r=s[p];assert r['e2e']==s[phases[0]]['e2e'] and set(r['rows'])==set(s[phases[0]]['rows'])
        assert r['roster_sha256']==s[phases[0]]['roster_sha256'] and r['diagnostics']==s[phases[0]]['diagnostics']
        assert r['listed']==s[phases[0]]['listed'] and sum(x.endswith(': test') for x in r['listed'])==200
        assert hashlib.sha256(('\n'.join(r['listed'])+'\n').encode()).hexdigest()==g['listing_sha256']
        assert r['counts']==g['counts'][p]
    assert s['selected-observer']['counts']=={'full':4,'link-only':48,'wild':51}
    assert s['selected-composed']['counts']=={'full':3,'link-only':48,'wild':50}
    assert all(s['repeat-'+a]['counts']=={'full':1,'link-only':50,'wild':50} for a in BASES)
    f=s['selected-observer']['e2e'][0]
    def counts(tag):return collections.Counter((e['kind'],e['target']) for e in s[tag]['physical'])
    observed=counts('selected-observer')
    assert observed-counts('selected-composed')=={('full','e2e'):1,('wild',f):1}
    assert not counts('selected-composed')-observed and counts('repeat-observer')==counts('repeat-composed')
    ids=[]
    for arm,width in [('observer',2),('composed',1)]:
        pp=s['selected-'+arm]['physical']
        e2e=[e['argv_sha256'] for e in pp if e['ty_server_e2e_source_and_prior_rlib']]
        assert len(e2e)==width and len(set(e2e))==1 and sum(e['kind']=='wild' and e['target']==f for e in pp)==width
        ids+=e2e
    assert len(set(ids))==1
    before=v['failed_first_replay'];assert before['exit']==1 and not before['successful_widths'] and before['driver_sha256']==sha(HERE/'replay-first-failed.py') and v['corrected_driver_sha256']==sha(HERE/'replay-widths.py')
    assert g['variants_sha256']==v['native_variant_manifest_sha256']
    cases=v['targets'];allow={key:{s[phases[0]]['workspace'][key]} for key in s[phases[0]]['workspace']}
    assert set(cases)==set(v['anticipation']['observed_unstable'])|set(v['anticipation']['earlier_ruff_target_controls'])
    assert len(cases)==len(v['input_files'])==10 and sorted(v['width_order'])==list(range(1,17))
    for name,t in cases.items():
        rows=t['widths'];bodies=t['bodies']
        assert [r['width'] for r in rows]==v['width_order']
        assert {r['raw_sha256'] for r in rows}==set(bodies) and all(r['status']==0 for r in rows)
        check_body_sets(bodies);assert set(t['raw_by_phase'].values())<=set(bodies)
        assert all(s[ph]['workspace'][name]==h for ph,h in t['raw_by_phase'].items())
        if len(bodies)>1:assert set(t['future_allowed'])==set(bodies);allow[name]=set(bodies)
        else:assert not t['future_allowed']
        inputs=v['input_files'][name];assert len(inputs)==t['closure_count']==len({i['path_sha256'] for i in inputs})
        assert t['closure_bytes']==sum(i['bytes'] for i in inputs) and digest(inputs)==t['portable_inputs_sha256']
        for i in inputs:check(i['sha256']);check(i['path_sha256']);check(i['resolved_path_sha256'])
    assert sum(len(h)>1 for h in allow.values())==6
    def accepted(key,raw):assert raw in allow[key]
    for phase in phases:
        assert set(s[phase]['workspace'])==set(allow)
        for k,h in s[phase]['workspace'].items():accepted(k,h)
    a=next(n for n,accepted_hashes in allow.items() if len(accepted_hashes)>1);must_reject(lambda:accepted(a,'f'*64))
    broken=copy.deepcopy(cases[a]['bodies'])
    next(iter(broken.values()))['unchanged_ranges'][0][2]='0'*64
    must_reject(lambda:check_body_sets(broken))
    cross={k:sum(s[k+'-observer']['workspace'][n]==s[k+'-composed']['workspace'][n] for n in allow)for k in ('selected','repeat')}
    return dict(zero_scored_commands=True,excluded_seed_commands=3,selected_full_workspace_commands=4,
                observed_units=619,observed_executables=102,workspace_elf_each=110,registry_elf_each=78,
                first_selection_full_compilers=[4,3],first_selection_link_only=[48,48],first_selection_wild=[51,50],
                unchanged_each={'full':1,'link-only':50,'wild':50},e2e_listing_tests=200,
                first_selection_identical_workspace_elf=cross['selected'],unchanged_identical_workspace_elf=cross['repeat'],
                repeated_native_argv_sha256=ids[0],replay_targets=10,explicit_widths=16,plain_real_wild=160,
                dependency_file_real_wild=160,multivariant_targets=6,fixed_width_raw_alternatives=2,
                unknown_target_hash_rejected=True,unexpected_byte_range_change_rejected=True)


if __name__=='__main__':
    if (HERE/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=HERE,check=True)
    print(json.dumps(verify(),indent=2,sort_keys=True))
