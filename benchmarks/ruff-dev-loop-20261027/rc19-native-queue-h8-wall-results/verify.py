"""Independently check all ordinary solves, off-clock native tools, and registered statistics."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
p=Path(__file__).resolve().parent
def read(f):
    b=(p/f).read_bytes()
    return json.loads(gzip.decompress(b)if f.endswith('.gz')else b)
h=lambda f:hashlib.file_digest((p/f).open('rb'),'sha256').hexdigest()
primary,plain=[read(f+'.json')for f in ('primary','plain')]
term=read('terminal.json');orders=read('order.json')['independent']
assert term['pairs']==96 and term['plain_pairs']==16
assert len(primary)==2 and all(len(x)==48 for x in primary)and len(plain)==16
for i,rows in enumerate(primary):
    assert [x['order']for x in rows]==orders['batches'][i]
    assert all(Counter(x['order']for x in rows[a:a+8])=={'AB':4,'BA':4}for a in range(0,48,8))
assert [x['order']for x in plain]==orders['plain']
for fmt,matrix in [('json',sum(primary,[])),('plain',plain)]:
    for row in matrix:
        for arm in ('A','B'):
            result=row[arm]
            assert result['exit']==0 and result['format']==fmt and result['wall_ns']>0
            assert len(result['cargo_stdout_sha256'])==len(result['cargo_stderr_sha256'])==64
            if fmt=='json':assert result['units']==619 and result['fresh']==563
native={'cargo':1,'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50}
for b in (1,2):
    m=read(f'batch-{b}-machines.json.gz');assert len(m)==56
    observed=read(f'batch-{b}-checks.json')
    for pos,row in enumerate(m):
        assert row['order']==(orders['batches'][b-1]+orders['plain'][8*(b-1):8*b])[pos]
        for s in (row['host_before'],row['host_after']):
            assert not s['other_tools'] and s['online']==list(range(32)) and s['free_bytes']>25*2**30
        before,after=[row['host_'+k]['cgroups']for k in ('before','after')]
        for u,v in zip(before,after,strict=True):
            for key in ('oom','oom_kill','oom_group_kill'):
                get=lambda a:dict(z.split()for z in a['cgroup'].get('memory.events','').splitlines()).get(key)
                assert get(u)==get(v)
    for phase in ('preclock-native','post-primary-pre-plain','post-plain'):
        a,v=[read(f'batch-{b}-{phase}-{arm}.json.gz')for arm in ('A','B')];out=observed['qualified'][phase]
        for c in (a,v):
            assert c['counts']==native and c['units']==619 and c['fresh']==563 and c['exit']==0
            assert len(c['output_files'])==50 and len(c['rust'])==51 and len(c['native_argv'])==150
            assert sum(x['role']=='rustc-link-only'for x in c['rust'])==50 and all(z['flag']=='-Zthreads=8'for z in c['rust'])
            assert c['programs']['listing']['listing_entries']==200 and all(z['exit']==0 for z in c['programs'].values())
        assert a['native_argv']==v['native_argv'] and a['rust']==v['rust'] and a['typed_roster_sha256']==v['typed_roster_sha256']
        exact=0
        for x,y in zip(a['output_files'],v['output_files'],strict=True):
            assert x['target']==y['target']and x['fields']['normalized']==y['fields']['normalized']and x['bytes']==y['bytes']
            exact+=x['sha256']==y['sha256']
        assert exact==out['stock_outputs_exact']
assert h('analysis.py')=='b76ab9cf870c25b7ddbe20efe8dbe6ba09b34fe4e6e6e95777d441228816ebdf' and h('order.json')=='db9a7dff6e92e03349af00832b6693e7d1d6d844a750d709f79ebe0925186ed4'
actual=json.loads(subprocess.check_output([sys.executable,'-IB',str(p/'analysis.py'),'independent',str(p/'primary.json')]))
reported=read('statistics.json');assert reported['primary']==actual
expected=1-math.exp(statistics.fmean(math.log(x['B']['wall_ns']/x['A']['wall_ns'])for x in plain))
assert math.isclose(reported['plain_paired_reduction'],expected,abs_tol=1e-15)and reported['plain_pass']==(expected>0)
print(json.dumps({'primary':actual,'plain_reduction':expected,'all_224_exit_zero':True,'off_clock_native_qualifications':12},sort_keys=True))
