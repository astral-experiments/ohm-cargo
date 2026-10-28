"""Read native receipts for the three excluded selections and both full-selection arms."""
import collections
import gzip
import hashlib
import importlib.util
import json
import re
import socket
import sys
from pathlib import Path

P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
K=P/'protocol-v3';W=P/'ruff-evaluation-v2';CAN=W/'canonical'
assert socket.gethostname()=='charlie-ohm-c5-check-1025'
def file_sha(path):
    with path.open('rb') as src:return hashlib.file_digest(src,'sha256').hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(obj):return sha(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())
def read(path):return json.loads(path.read_bytes())
def relative(name):
    out=str(Path(name).relative_to(CAN))
    assert out.startswith(('target/','shared/')) and re.fullmatch('[A-Za-z0-9_./+-]+',out)
    return out
spec=importlib.util.spec_from_file_location('native',K/'ruff_worker.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
assert file_sha(K/'ruff_worker.py')=='9c2e4138072679b8ffff20d417fffad8f6bcd3cba1b0dd15309e2d935cbc0813'
assert all((K/(role+'.exit')).read_text()=='0' for role in ('seed','observer','composed'))
subjects={role:n.sealed_file(role)[1] for role in ('observer','composed')}
assert subjects=={'observer':'0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322','composed':'813ba8a480bc6047d2effde2edff5fe5990781904ff453815ddc71aeb5e0e754'}
native_kinds=('full','link-only','wild');schema=('package_id','manifest_path','target','profile','features','filenames','executable')
steps={}
for tag in ('seed-cold','seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed'):
    d=W/tag;r=read(d/'products.json');c=read(d/'command.json');events=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines()]
    assert events[-1]=={'reason':'build-finished','success':True}
    rows=[e for e in events if e['reason']=='compiler-artifact']
    encoded=[json.dumps({k:e[k] for k in schema},sort_keys=True) for e in rows]
    assert digest(sorted(encoded))==r['roster'] and len(rows)==r['units'] and sum(x['fresh'] for x in rows)==r['fresh']
    groups=collections.Counter()
    typed={}
    for e,s in zip(rows,encoded):
        label=Path(e['manifest_path']).parent.name
        code=('workspace' if e['package_id'].startswith('path+') else 'registry')
        groups[code]+=1
        key=sha(s.encode());assert key not in typed
        typed[key]={'owner':code,'package':label,'target':e['target']['name'],'kind':e['target']['kind'],'test':e['profile']['test'],
                    'fresh':e['fresh'],'executable':relative(e['executable']) if e['executable'] else None}
    owned={f for e in rows if e['package_id'].startswith('path+') for f in [*e['filenames'],e['executable']] if f}
    workspace={relative(f):h for f,h in r['native'].items() if f in owned}
    reg=read(d/'registry-native.json') if (d/'registry-native.json').exists() else {f:h for f,h in r['native'].items() if f not in owned}
    assert len(reg)==78 and digest(reg)=='508c6cee5b0f1962ab784ffbd953dc3b06699f51663633cb279d4e1bb4131d53'
    registry={relative(f):h for f,h in reg.items()}
    exes=sorted(relative(f) for f in r['exes'])
    assert set(exes)<=set(workspace)
    snap={}
    if tag.startswith('selected-'):
        state=W/('state-'+tag.split('-',1)[1])
        for key,which,folder,expected in (('workspace','preserved-native.json','native-files',workspace),('registry','preserved-registry.json','registry-files',registry)):
            saved=read(d/which);assert len(saved)==len(expected)
            for f,v in saved.items():
                artifact=d/folder/v['file'];original=n.actual(f,state)
                assert file_sha(artifact)==expected[relative(f)]==v['sha256'] and not artifact.samefile(original)
            snap[key]={'copied':len(saved),'manifest':file_sha(d/which),'all_bytes_match':True,'private_inodes':True}
    elif tag.startswith('repeat-'):
        state=W/('state-'+tag.split('-',1)[1])
        for data in (workspace,registry):
            for f,h in data.items():assert file_sha(n.actual(str(CAN/f),state))==h
    diag=[[Path(e['manifest_path']).parent.name,e['message']['level'],e['message']['message'],digest(e['message'])] for e in events if e['reason']=='compiler-message']
    dproducts=[[e['package_id'],e['message']] for e in events if e['reason']=='compiler-message']
    assert sorted(dproducts,key=digest)==sorted(r['diagnostics'],key=digest)
    physical=None
    if (d/'physical.json').is_file():
        calls=read(d/'physical.json');assert n.trace_jobs(d/'trace')==calls
        physical=[]
        for j in calls:
            assert j['kind'] in native_kinds and j['exit']==0
            cmd=j['argv'];t=relative(j['target']) if j['kind']=='wild' else j['target']
            role=j['kind']=='full' and j['target']=='e2e' and '--test' in cmd and any(v=='crates/ty_server/tests/e2e/main.rs' or v.endswith('/crates/ty_server/tests/e2e/main.rs') for v in cmd)
            if role:assert 'ty_server='+r['ty_server']['file'] in cmd
            physical.append({'pid':j['pid'],'kind':j['kind'],'target':t,'exit':j['exit'],'exec_sha256':j['raw'],'argv_sha256':digest(cmd),
                            'ty_server_e2e_source_and_prior_rlib':role})
        assert len({j['pid'] for j in physical})==len(physical)
    keyfiles=('command.json','products.json','physical.json','stdout','stderr','e2e-list','registry-native.json','preserved-native.json','preserved-registry.json')
    record={f:file_sha(d/f) for f in keyfiles if (d/f).exists()}
    steps[tag]={'command':c,'units':r['units'],'fresh':r['fresh'],'roster_sha256':r['roster'],'rows':typed,'groups':groups,'exes':exes,
                'workspace':workspace,'registry':registry,'snapshots':snap,'e2e':[relative(x) for x in r['e2e']],
                'ty_server':dict(file=relative(r['ty_server']['file']),sha=r['ty_server']['sha'],fresh=r['ty_server']['fresh']),
                'physical':physical,'diagnostics':sorted(diag),'receipt_sha256':record,'counts':r['counts'],
                'listed':(d/'e2e-list').read_text().splitlines() if (d/'e2e-list').is_file() else None}
packet={'steps':steps,'subjects':subjects,'release':read(P/'sdk.json')['tools'],'sdk_archive':read(P/'sdk.json')['archive'],
        'canonical':str(CAN),'native_manifest':file_sha(K/'SHA256SUMS'),'v2_seed':read(K/'adopted-seed.json'),
        'seed_receipt':file_sha(W/'seed-complete.json'),'actual_phase_receipts':{r:file_sha(W/(r+'-complete.json')) for r in ('seed','observer','composed')},
        'v3_adoption':read(K/'adopted.json'),'root':n.src.name,'source':read(P/'ruff.json')['pin'],'wall_slots':0}
sys.stdout.buffer.write(gzip.compress(json.dumps(packet,separators=(',',':'),sort_keys=True).encode(),mtime=0))
