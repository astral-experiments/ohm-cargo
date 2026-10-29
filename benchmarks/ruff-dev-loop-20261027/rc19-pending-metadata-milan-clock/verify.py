#!/usr/bin/env python3
"""Check each portable Milan record, then replay the registered block analysis."""
import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import re
import runpy
from statistics import mean, median

ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def c(x):return json.dumps(x,sort_keys=True,separators=(",",":"))
def load(n):
    b=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
def thresholds(rows):
    out={}
    for name,cols in (("loop",(0,1)),("edit",(0,)),("repeat",(1,))):
        vals={k:[sum(row[k][i] for i in cols) for row in rows] for k in "AB"}
        ratios=[1-y/x for x,y in zip(vals["A"],vals["B"])]
        logs=[math.log(x/y) for x,y in zip(vals["A"],vals["B"])]
        blocks=[ratios[i:i+4] for i in range(0,32,4)]
        rng=random.Random(209112)
        boots=sorted(median(sum((blocks[rng.randrange(8)] for _ in range(8)),[])) for _ in range(20000))
        def q(v):
            at=v*(len(boots)-1); i=int(at)
            return boots[i]+(at-i)*(boots[i+1]-boots[i])
        bm=[mean(logs[i:i+4]) for i in range(0,32,4)]
        extreme=0
        for signs in itertools.product((-1,1),repeat=8):
            extreme+=abs(sum(x*y for x,y in zip(signs,bm)))+1e-15>=abs(sum(bm))
        out[name]={"median_saving":median(ratios),"ci95":[q(.025),q(.975)],"block_signflip_p":extreme/256,
                   "pairs_positive":sum(x>0 for x in ratios),"n":32}
    loop,edit=out["loop"],out["edit"]
    out["pass_primary"]=loop["median_saving"]>=.01 and loop["ci95"][0]>0 and loop["block_signflip_p"]<.05
    out["edited_slowdown_gate"]=edit["median_saving"]<-.03 and edit["ci95"][1]<0
    return out

def verify():
    recons=runpy.run_path(str(ROOT/'reconstruct.py'))
    bindings=load('bindings.json'); members=load('archive-members.json.gz')
    assert len(members)==1234 and len({r[0] for r in members})==1234
    files={r[0]:r for r in members if r[1]=='file'}
    assert len(files)==880 and all(len(r)==5 and re.fullmatch('[0-9a-f]{64}',r[4]) for r in files.values())
    assert sum(r[1]=='dir' and r[2]==0 and len(r)==4 for r in members)==354
    assert bindings['archive']==recons['ARCHIVE'] and bindings['archive_bytes']==8974029
    assert bindings['protocol']==recons['PLAN']==sha((ROOT/'protocol/SHA256SUMS').read_bytes())
    for row in (ROOT/'protocol/SHA256SUMS').read_text().splitlines():
        h,n=row.split();assert files['protocol/'+n][4]==sha((ROOT/'protocol'/n).read_bytes())==h
    plan=runpy.run_path(str(ROOT/'protocol/paired.py'))
    roster=load('protocol/milan.json')
    assert plan['roster']('milan')==roster
    for start in range(0,32,4):
        block=roster[start:start+4]
        assert {b['block'] for b in block}=={start//4}
        assert {(b['direction'],b['order']) for b in block}==set(itertools.product(('parent-to-child','child-to-parent'),('AB','BA')))
    src=load('source-revisions.json'); att=load('build-attestation.json')
    assert att['qualified'] and att['same_cargo_version'] and not att['historical_control_byte_identical']
    assert src['cargo']['attestation']==sha((ROOT/'build-attestation.json').read_bytes())
    assert att['old_independent_candidate']['excluded']
    assert att['roles']['A']['commit']=='235f9228651b74c591e6f62cae4c9b761448dd2d'
    assert att['roles']['B']['commit']=='b3360c5eda186845b9a2ba6e5330a97c07d4acf2'
    b=bindings['donors']; grant=bindings['grant']; physical=bindings['physical']; nqual=bindings['qualification']
    assert grant['protocol']==bindings['protocol'] and grant['images']==recons['CARGOS']
    assert grant['common']==files['physical-common/complete.json'][4] and grant['qualification']==files['qualification/complete.json'][4]
    assert {k:x['binary_sha256'] for k,x in att['roles'].items()}==grant['images']
    assert physical['images']=={'driver':'a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de','rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}
    for direction in ['parent','child']:
        a,d=b['A'][direction],b['B'][direction]
        assert {k:v for k,v in a.items() if k not in ('arm','cargo')}=={k:v for k,v in d.items() if k not in ('arm','cargo')}
        assert a['revision']==src['ruff']['old' if direction=='parent' else 'new']==recons['REVISIONS'][direction]
        assert len(a['source_times'])==30 and set(a['source_times'])==set(src['ruff']['files'])-{'Cargo.lock'}
        assert a['products597']==physical['cross_arm_597']['A-'+direction]==physical['cross_arm_597']['B-'+direction]
        assert a['state']['entries']=={'dir':2283,'file':6560}
    assert b['A']['parent']['products597']!=b['A']['child']['products597'] and len(set(physical['within_A_changed']))==41
    for path, versions in src['ruff']['files'].items():
        assert (versions['parent']==versions['child'])==(path=='Cargo.lock')
    for arm in 'AB':
        for direction in ('parent-to-child','child-to-parent'):
            gate=nqual[arm][direction]
            assert [m['roles']['rustc-full'] for m in gate]==grant['native'][arm+':'+direction]==([51,12,1] if arm=='A' else [52,1,1])
            assert [m['roles'].get('stock-wild',0) for m in gate]==[1,0,0]
            assert all(len(m['target'])==m['roles']['rustc-full'] and m['roles']['cargo']==1 for m in gate)
        assert [m['roles']['rustc-full'] for m in nqual[arm]['one-file-method-edit']]==[2,1]
    units=load('typed-units.json.gz'); catalog=units['catalog']; lines=units['cargo_lines']
    assert len(catalog)==500 and len(set(c(x['unit']) for x in catalog))==500
    assert len(lines)==660 and len(set(l[0] for l in lines))==660
    for entry in catalog:
        assert re.fullmatch('[0-9a-f]{64}',entry['raw_typed_sha256']) and len(entry['unit'])==8
    for k,iv in units['inventories'].items():
        assert len(iv['nodes'])==510 and len(set(iv['nodes']))==471
        assert sha('\n'.join(sorted(c(catalog[j-1]['unit']) for j in iv['nodes'])).encode())==iv['portable']
    before,after=(Counter(units['inventories'][b['A'][x]['identity']]['nodes']) for x in ['parent','child'])
    def except_flags(rows):
        return Counter(c(catalog[i-1]['unit'][:4]+catalog[i-1]['unit'][6:]) for i in rows.elements())
    assert sum((before-after).values())==sum((after-before).values())==30 and except_flags(before)==except_flags(after)
    commands=load('commands.json.gz'); by={(r['pair'],r['arm'],r['phase']):r for r in commands}
    visits=load('visits.json.gz'); visit={(v['pair'],v['arm']):v for v in visits}
    pairs=load('observations.json'); assert len(commands)==len(by)==256 and len(visits)==len(visit)==64 and len(pairs)==32
    ntypes=Counter();dirty_counts={arm:Counter() for arm in 'AB'};prev=0
    for j,(p,reg) in enumerate(zip(pairs,roster)):
        assert {k:p[k] for k in reg}==reg and p['pair']==j
        fr,to=p['direction'].split('-to-')
        for arm in p['order']:
            v=visit[j,arm];prefix=f'scored/pair-{j:02}/{arm}'
            assert (v['source_before'],v['source_after'])==(b[arm][fr]['revision'],b[arm][to]['revision'])
            assert v['timing_ns']==p[arm] and v['cargo']==grant['images'][arm] and v['order']==p['direction'] and v['between_ns']>=0
            assert prev<files[prefix+'/visit.json'][3];prev=files[prefix+'/visit.json'][3]
            for phase in recons['PHASES']:
                row=by[j,arm,phase]; rec=row['receipt']; base=b[arm][fr if phase=='preflight' else to]
                phasepath=prefix+'/'+phase
                assert rec['source']==base['revision'] and rec['inventory']==base['identity']
                assert row['receipt_sha']==files[phasepath+'/receipt.json'][4] and rec['json']==files[phasepath+'/cargo.jsonl'][4] and rec['stderr']==files[phasepath+'/stderr'][4]
                order=[lines[x] for x in row['json_line_order']]
                reasons=Counter(x[1] for x in order);ntypes.update(reasons)
                assert reasons==row['message_types'] and reasons['compiler-artifact']==510 and reasons['build-finished']==1 and order[-1][1]=='build-finished'
                assert Counter(x[2] for x in order if x[1]=='compiler-message')==row['diagnostics'] and 'error' not in row['diagnostics']
                ids=[x[2] for x in order if x[1]=='compiler-artifact']; assert ids==row['artifact_order']
                assert sorted(map(abs,ids))==units['inventories'][rec['inventory']]['nodes'] and rec['dirty']==sum(x<0 for x in ids)
                if phase in ('preflight','after'):
                    assert rec['rc']==0 and rec['wall_ns']>0 and rec['typed']==510 and rec['dirty']==12
                    assert rec['images']==base['images'] and rec['fresh']=={k:True for k in recons['PROBES']}
                    matched={catalog[abs(i)-1]['unit'][1]:i>0 for i in ids if catalog[abs(i)-1]['unit'][1] in recons['PROBES']}
                    assert matched==rec['fresh']
                else:
                    assert rec['units']==510 and rec['wall_ns']==p[arm][phase=='repeat']>0
                    if phase=='edit': assert rec['dirty']==56
                    else: dirty_counts[arm][rec['dirty']]+=1
    assert dirty_counts=={'A':{12:4,21:25,24:3},'B':{12:32}}
    assert ntypes=={'compiler-artifact':130560,'build-script-executed':12544,'compiler-message':512,'build-finished':256}
    scores=plan['analyze']('milan',pairs)
    assert scores==load('original-analysis.json')==thresholds(pairs)
    assert scores['pass_primary'] and not scores['edited_slowdown_gate']
    return {name:{'A_median_ns':median([sum(p['A'][i] for i in cols) for p in pairs]),
                  'B_median_ns':median([sum(p['B'][i] for i in cols) for p in pairs]),**scores[name]}
            for name,cols in [('loop',(0,1)),('edit',(0,)),('repeat',(1,))]}

if __name__=='__main__':
    cli=argparse.ArgumentParser(); cli.add_argument('--archive',type=Path); args=cli.parse_args()
    res=verify()
    if args.archive:
        r=runpy.run_path(str(ROOT/'reconstruct.py')); outputs,protocol=r['collect'](args.archive)
        for name,value in outputs.items(): assert r['encode'](name,value)==(ROOT/name).read_bytes(),name
        for name,value in protocol.items(): assert value==(ROOT/'protocol'/name).read_bytes(),name
    print(json.dumps(res,indent=2))
    print('Verified 32 Milan pairs, 64 restored visits, 256 Cargo streams and 130,560 typed artifacts.')

