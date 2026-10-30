"""Recount the on/off parser check and test-build endpoints, typed outputs, and complete disk use."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parent
PHASES=('empty-A','first-B','return-A','return-B','unchanged-B')


def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)


def inspect(data, raw, infer):
    plan=data['recipe'];n=plan['pairs'];mode=plan['workflow']
    assert mode in ('check','test-no-run') and n in (2,12)
    assert data['filesystem']=='tmpfs' and plan['same_sdk'] and plan['enable'] and plan['hold_sdk_identity']
    assert plan['commit']==raw['source']=='08d49cba6aacb0cac27a96eea335ed1c7439f483'
    assert not plan['instructions'] and raw['mode']==mode and raw['pairs']==n
    assert len(data['sdk_identities'])==4+2*n and all(s['files']==data['sdk_identities'][0]['files'] for s in data['sdk_identities'])
    assert plan['orders'].count('PQ')==plan['orders'].count('QP')==n//2
    expected = {f'{slot}/{phase}': phase[-1] for slot in data['samples'] for phase in PHASES}
    expected.update({f'reference-{arm}-{rev}/empty': branch for arm in 'PQ'
                     for rev, branch in [('b5dba861','A'), ('7b13f01b','B')]})
    expected.update({f'pair-01-{arm}/recovery': 'B' for arm in 'PQ'})
    assert len(expected)==10*n+6 and set(raw['samples'])==set(expected)
    assert set(raw['physical'])==set(data['samples'])
    for name,verdict in raw['samples'].items():
        assert verdict['branch']==expected[name]
        if mode=='check':
            correct='64' if verdict['branch']=='A' else '56'
            assert set(verdict['sizes'])=={'64','56'}
            for size,value in verdict['sizes'].items():
                assert value['exit']==int(size!=correct) and value['E0308']==(size!=correct)
        else:
            assert verdict['listed_tests']==245 and len(set(verdict['representative_tests']))==3
    if mode=='test-no-run':
        assert len({v['inventory'] for v in raw['samples'].values()})==1
        refs=data['references']
        assert set(refs)=={'PA','PB','QA','QB'} and refs['PA']!=refs['PB'] and refs['QA']!=refs['QB']
    else:
        assert data['references']=={}
    for slot,observations in data['samples'].items():
        arm=slot[-1];assert set(observations)==set(PHASES)
        for phase,obs in observations.items():
            disk=raw['physical'][slot][phase]
            assert obs['bytes']==disk['bytes']==sum(int(line.split()[0]) for line in disk['du'])
            count=sum(n.startswith('ohm-packed-') for t in disk['tables'].values() for n in t['files'])
            assert count==disk['packed_tables']==obs['packed_tables']
            if arm=='P' or phase=='empty-A':assert obs['older']==0 and count==0
            elif phase.startswith('return-'):assert obs['older']==2 and len(disk['tables'])==4 and count==8
            if mode=='test-no-run':assert obs['ELF']==data['references'][arm+phase[-1]]
    out={}
    for phase in (*PHASES,'first-B+return-A'):
        names=phase.split('+')
        def get(i, arm):return [data['samples'][f'pair-{i:02}-{arm}'][k] for k in names]
        pairs=[(get(i,'P'),get(i,'Q')) for i in range(1,n+1)]
        totals=[(sum(z['wall'] for z in p),sum(z['wall'] for z in q)) for p,q in pairs]
        ratios=[a/b for a,b in totals];stat=infer(ratios,plan['orders']);stat.update(parent_median=median(a for a,b in totals),candidate_median=median(b for a,b in totals))
        if len(names)==1:
            sizes=[q[0]['bytes']/p[0]['bytes'] for p,q in pairs];assert sizes==data['summary'][phase]['bytes_ratio'] and ratios==data['summary'][phase]['ratios']
            stat.update(parent_bytes=median(p[0]['bytes'] for p,q in pairs),candidate_bytes=median(q[0]['bytes'] for p,q in pairs),max_storage_ratio=max(sizes),cpu_ratio=median(p[0]['cpu']/q[0]['cpu'] for p,q in pairs))
        out[phase]=stat
    return out


def verify(root, common):
    spec=importlib.util.spec_from_file_location('compact_metrics',common);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    files=sorted(root.glob('verb-*-sample.json.gz'));assert files
    for file in files:
        key=file.name.removesuffix('-sample.json.gz');data=load(file);raw=load(root/(key+'-verified.json.gz'))
        assert raw['raw_verified']==hashlib.sha256(gzip.decompress(file.read_bytes())).hexdigest()
        calculated=inspect(data,raw,mod.infer);assert calculated==load(root/(key+'-summary.json'))
        print(key,[(k,round(calculated[k]['paired_median'],3),round(calculated[k]['max_storage_ratio'],4)) for k in ('return-A','return-B')])


if __name__=='__main__':
    verify(ROOT,ROOT.parent/'native-compact/verify.py')
