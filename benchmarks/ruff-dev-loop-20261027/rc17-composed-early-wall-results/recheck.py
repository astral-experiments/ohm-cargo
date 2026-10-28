"""Verify the preserved fourth-slot products and first exception; compute no performance statistics."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PACKET='6b53d6de8973d5e55a3f294980901e9dde9ef64de26685a8f98e63db9860ea7d'
REFS={
    'ruff_python_formatter-519c0544e58f942c':('88aca52cf9db0204d5f0a0edae063e8e05ade0c183b8ec5614e1f70fc63c03b0','f56d2f9441e7bae586e8ed95bcbaf58b6753337347afb26da1f2a05a305a4701'),
    'ty_project-30613778192a6cff':('2cd957cc60a4a64447f662c5dfed044241e22034cf828f69dc15eebc657c15ed','a2c3105ef595009ea24961751977d80eca44cca3f7c989d2e3c323ae3428670a')}
def sha(b):return hashlib.sha256(b).hexdigest()
def run():
    raw=(ROOT/'results.json.gz').read_bytes();assert sha(raw)==PACKET
    q=json.loads(gzip.decompress(raw));fs=q['files'];bodies=q['bodies']
    def text(name):
        rec=fs[name];out=bodies[rec['sha256']];assert len(out.encode())==rec['bytes'] and sha(out.encode())==rec['sha256'];return out
    def obj(name):return json.loads(text(name))
    v=json.loads((ROOT/'verified.json').read_bytes())
    assert v['terminal']==q['status']=='score-failed' and v['statistics'] is None and not v['qualified']
    assert v['launcher']=={'admit':0,'score':1,'verify':None} and v['observed_clocks']==4 and v['verified_slots']==3 and v['complete_pair_checkpoints']==1
    assert v['retained_private_states']==['02-2-B'] and set(q['slots'])=={'01-1-B','01-2-C','02-1-C','02-2-B'}
    assert not any(k in fs for k in ('result/result.json','result/complete.json','launcher/verify.exit','02-2-B/verified.json'))
    assert fs['result/first-failure.txt']['sha256']=='3305c7c3ae493d875cd2dd2261796a67e39a90cdfb84a710bc6752b362b61436'
    trace=text('result/first-failure.txt')
    assert 'g.check_raw(products[\'native\'],controls[\'allowed\'])' in trace
    exception=json.loads(trace.split('ValueError: Unadmitted raw ELF hashes: ',1)[1]);assert len(exception)==2
    m=obj('admission.json')['native'];prefix='02-2-B/';post=prefix+'unchanged/'
    full=obj(post+'command.json');assert full['code']==0 and full['arm']=='observer' and full['command'][-1]=='--message-format=json'
    first=obj(prefix+'first-110.json');follow=obj(post+'products.json');final=q['slots']['02-2-B']['terminal_retained_outputs']
    assert len(first)==len(follow['native'])==110 and len(follow['exes'])==102 and follow['units']==619 and follow['fresh']==563
    assert all(h in m['allowed'][p] for p,h in first.items())
    assert fs[prefix+'ordinary/e2e-list']['sha256']==fs[post+'e2e-list']['sha256']==m['listing_sha256']
    assert text(post+'e2e-list').count(': test\n')==200
    assert obj(prefix+'first-78-registry.json')==obj(post+'registry-native.json')==m['registry']
    allout=follow['native']|m['registry'];assert len(allout)==188 and set(allout)==set(final)
    assert all(final[p] and final[p]['sha256']==h for p,h in allout.items())
    jobs=q['slots']['02-2-B']['jobs'];assert len({p['pid'] for p in jobs})==len(jobs) and all(p['exit']==0 for p in jobs)
    assert dict(collections.Counter(p['kind'] for p in jobs))==follow['counts']=={'full':1,'link-only':50,'wild':50}
    assert [p['target'] for p in jobs if p['kind']=='full']==['ron']
    misses={p:h for p,h in follow['native'].items() if h not in m['allowed'][p]}
    assert misses==exception and set(REFS)=={Path(p).name for p in misses}
    out={}
    for path,h in sorted(misses.items()):
        name=Path(path).name
        assert m['allowed'][path]==[first[path]] and (first[path],h)==REFS[name]
        assert path in follow['exes'] and [p['target'] for p in jobs if p['kind']=='wild'].count(path)==1
        out[name]={'first_selection_sha256':first[path],'unchanged_follow_up_sha256':h,'retained_file_sha256':final[path]['sha256'],'retained_bytes':final[path]['bytes'],'physical_wild_on_follow_up':1}
    return dict(terminal='score-failed',failed_block=2,failed_slot=2,failed_arm='B (#261)',failed_phase='untimed unchanged follow-up after the timed first selection',native_test_products=102,
                first_selection_workspace_admitted=110,follow_up_workspace_admitted=108,exact_registry_both_times=78,retained_outputs_matching_recaptured_bytes=188,
                exited_follow_up_processes=follow['counts'],physical_full_crate='ron',unadmitted=out,clocks=4,complete_pairs=1,timing_statistics=None,
                raw_receipts=len(fs),raw_commitment_only_privacy_exclusions=v['commitment_only_text'])
if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
