"""Untraced, blocked B/C confirmation of the cost of an actual historical Ruff edit."""
from pathlib import Path
import fcntl,json,os,re,shutil,statistics,sys
import fixture as f
def check_flag(r,cpp,fresh):
    tr=r['trace']
    assert r['fresh']==fresh and r['foreign_marker'] is False and r['checksummed_sources']==4
    assert len(tr['jobs'])==int(not fresh) and tr['observer_probes']==int(cpp=='C' and not fresh),tr
    if not fresh: assert tr['jobs'][0]['crate']=='ruff_text_size' and tr['jobs'][0]['depinfo_flag']==(cpp=='C')
def native(r):
    members=[]
    for x in r['members'] or []:
        if x['kind']=='codegen':
            m=re.fullmatch(r'(ruff_text_size-[0-9a-f]{16}\.[0-9a-z]+)\.[0-9a-z]+(\.rcgu\.o)',x['label']);assert m,x['label']
            members.append((m[1]+m[2],x['size'],x['sha']))
        elif x['kind']=='lib.rmeta-link':
            assert x['label']=='lib.rmeta-link';members.append((x['label'],x['size'],x['exact_member_names_folded']))
        else:
            assert x['kind']==x['label']=='lib.rmeta';members.append((x['label'],x['size'],x['sha']))
    assert not members or [x['kind'] for x in r['members']]==['lib.rmeta','lib.rmeta-link','codegen','codegen']
    return dict(meta=r['outputs']['.rmeta'],members=members,api=r['ordinary_api'],source=r['source'],checksums=r['checksummed_sources'],marker=r['foreign_marker'],depinfo=r['depinfo_sha256'])
def refs(controls):
    ref={}
    for kind in ['check','build']:
        for hist in ['edit','restore']:
            variants=[controls['qualified'][kind+'-'+arm][hist] for arm in ('B','B2','C','C2')]
            for arm,records in [(a,controls['qualified'][kind+'-'+a]) for a in ('B','B2','C','C2')]:
                for phase,r in records.items():check_flag(r,arm[:1],phase.startswith('unchanged'))
                for phase in ('edit','restore'):
                    assert records[phase]['outputs']==records['unchanged_'+phase]['outputs']
            assert all(native(r)==native(variants[0]) for r in variants),kind
            ref[kind,hist]=native(variants[0])
    return ref
def run():
    plan=json.loads((f.I/'schedule.json').read_bytes());assert plan['n_per_endpoint']==24 and set(plan['executable_arms'])=={'B','C'}
    f.prepare();inputs=f.qualify();ref=refs(inputs)
    score=[]
    for block in plan['schedule']:
        edit=block['direction']=='edit';assert edit==bool(block['block']%2)
        for kind in block['endpoint_order']:
            for slot,arm in enumerate(block[kind],1):
                state=f.state_dir(kind,arm);f.source(state,edit)
                row=f.observe(state,kind,arm,'wall-%02d-%d'% (block['block'],slot),edit,traced=False)
                assert row['fresh'] is False and row['trace'] is None and native(row)==ref[kind,block['direction']]
                score.append(dict(block=block['block'],slot=slot,arm=arm,kind=kind,direction=block['direction'],receipt=row))
        assert shutil.disk_usage(f.P).free>8*2**30
    assert len(score)==96
    for kind in ('check','build'):
        for arm in 'BC':
            ra=f.observe(f.state_dir(kind,arm),kind,arm,'final-unchanged',False);check_flag(ra,arm,True)
            assert native(ra)==ref[kind,'restore'] and ra['outputs']==[x for x in score if x['kind']==kind and x['arm']==arm][-1]['receipt']['outputs']
    total=sum(x.stat().st_size for x in f.P.rglob('*') if x.is_file() and not x.is_symlink());assert total<2**30
    print(json.dumps(dict(controls=inputs,scored=score,temporary_byte_size=total),separators=(',',':')),flush=True)
if __name__=='__main__':
    with (f.root/'.cache/ohm-hillclimb-release.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run()
