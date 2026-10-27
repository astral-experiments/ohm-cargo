"""Validate physical job-to-record joins, raw test-program changes and the independent metadata reader."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import re
import runpy

P = Path(__file__).resolve().parent
primary = runpy.run_path(P/'verify.py')
cell = primary['cell']
digest = lambda data: hashlib.sha256(data).hexdigest()
load = lambda name: json.loads((P/name).read_text())
origin = load('supplement-origins.json')
headers = load('changed-rmeta-headers.json')
guards = load('changed-elf-guards.json')
summary = primary['check']()
bound = {'check':(520,71,449,0,6,4,6),'build':(501,68,433,0,15,55,15),'test':(619,162,456,1,110,54,110)}
for mode, (units, count, mtime, obs, links, archives, workspace_elf) in bound.items():
    first = cell(mode,'upgraded','first')
    second = cell(mode,'upgraded','second')
    settled = cell(mode,'seed','noop-2' if mode=='test' else 'noop-1')
    assert first['receipt']['units'] == units and first['receipt']['fresh'] == units-count
    assert primary['quick'](first)=={'rustc-full':count,'rustc-link-only':0,'wild':links,'build-script':5}
    assert second['receipt']['fresh']==units and sum(primary['quick'](second).values())==0
    assert first['wire-records']['rows'] == second['wire-records']['rows']
    assert first['products'] == second['products']
    before = settled['wire-records']['rows']
    after = first['wire-records']['rows']
    assert set(before)==set(after) and len(before)==units
    retrained = {k for k,b in before.items() if b['class']=='legacy-ordinary-checksum-retrain'}
    assert retrained=={k for k in after if before[k]['sha256']!=after[k]['sha256']}
    for k in retrained:
        assert before[k]['version']==2 and after[k]['version']==3 and after[k]['class']=='current-ordinary-checksum'
    jobs = first['compiler-record-joins']['physical']
    dirty_ids = {Path(k).parent.parent.name for k in retrained}
    assert len(dirty_ids)==len(retrained)==len(jobs)==count
    assert {j['id'] for j in jobs}==dirty_ids
    assert all(j['workspace_source'] and j['exit']==0 and j['role']=='rustc-full' and j['id_basis']=='actual-out-dir' for j in jobs)
    all_calls = {c['pid']:c for c in first['all-physical-typed-processes']}
    assert all(all_calls[j['pid']]['arg_sha256']==j['argv_sha256'] and all_calls[j['pid']]['exit']==0 for j in jobs)
    assert first['compiler-record-joins']['seed_capabilities_by_compiler_source']=={'legacy-ordinary-checksum-retrain:workspace':count,'ordinary-mtime:external':mtime,**({'obs1-safe-complete:external':obs} if obs else {})}
    assert sum(v['elf'] and v['workspace'] for v in first['products'].values())==workspace_elf
    diff=first['changed-products']
    assert all(a['before'] and a['after'] and a['before']['workspace'] and a['after']['workspace'] for a in diff.values())
    assert Counter('elf' if z['before']['elf'] else Path(k).suffix for k,z in diff.items())=={'.rmeta':31,'.rlib':archives,**({'elf':3} if mode=='test' else {})}
    hk = {'@cache/'+k:v for k,v in headers[mode]['pairs'].items()}
    assert set(hk)=={k for k in diff if k.endswith('.rmeta')}
    for k, pair in hk.items():
        a,b=pair['original'],pair['retrained']
        assert a['status']==b['status']==0 and a['private']!=b['private']
        assert (a['stable_id'],a['public'])==(b['stable_id'],b['public'])
        assert [a['sha'],b['sha']]==[diff[k]['before']['sha256'],diff[k]['after']['sha256']]
    summary[mode]['first'].update(workspace_elfs=workspace_elf,changed_raw_rmetas=31,changed_raw_rlibs=archives)
assert origin['changed-rmeta-headers.json']==digest((P/'changed-rmeta-headers.json').read_bytes())
assert origin['changed-elf-guards.json']==digest((P/'changed-elf-guards.json').read_bytes())
assert len(origin)==26
test=cell('test','upgraded','first')
elf_diff={Path(k).name:z for k,z in test['changed-products'].items()if z['before']['elf']}
assert set(elf_diff)=={z['artifact']for z in guards.values()}
for unit, cert in guards.items():
    prod=elf_diff[cert['artifact']]
    assert [prod[t]['sha256']for t in ['before','after']]==cert['raw'] and cert['file_sizes'][0]==cert['file_sizes'][1]
    a,b=cert['all_sections']['stock'],cert['all_sections']['retrained']
    assert a.keys()==b.keys()
    assert {k for k in a if a[k]!=b[k]}==set(cert['section_differences'])=={'.rodata','.note.gnu.build-id'}
    assert [a['.rodata']['entsize'],b['.rodata']['entsize']]==cert['rodata_entsize']==[0,8]
    assert a['.text']==b['.text'] and a['.rodata']['bytes']==b['.rodata']['bytes']
    assert cert['only_rodata_entsize_and_gnu_build_id'] and len(set(cert['masked']))==1
    assert cert['build_ids'][0]!=cert['build_ids'][1] and all(len(x)==64 for x in cert['build_ids'])
    rr=cert['raw_ranges'];assert rr['equal_length'] and rr['range_complete'] and rr['total_differing_bytes']==33
    assert rr['differing_byte_ranges'][0]==[896,928] and len(rr['differing_byte_ranges'])==2
    lo,hi=rr['differing_byte_ranges'][1];assert hi-lo==1
    assert cert['list_equal'] and len(cert['filter_results'])==1
    lists=[];normalized=[]
    for arm in ['stock-repeat','upgraded']:
        actual={}
        for action in ['list','filter-0']:
            for ext in ['stdout','stderr']:
                suffix=arm+'-'+action+'.'+ext
                raw=gzip.decompress((P/('harness-'+unit+'-'+suffix+'.gz')).read_bytes())
                assert digest(raw)==origin[f'changed-test-elf/{unit}/{suffix}']
                actual[(action,ext)]=raw
        ls=cert['list_results'][arm];run=cert['filter_results'][0]['arms'][arm]
        assert ls['exit']==run['exit']==0 and run['passed']
        for tag,row in (('list',ls),('filter-0',run)):
            for stream in ['stdout','stderr']:assert digest(actual[(tag,stream)])==row[stream+'_sha256']
        lines=actual[('list','stdout')];lists.append(lines)
        names=[l.rsplit(': ',1)[0] for l in lines.decode().splitlines() if l.endswith(': test')]
        assert ls['names']==names and len(names)=={'09978b48e8f13d6a':4,'8ae260e78382292d':10,'dd9b7f57d7ba4f6b':200}[unit]
        assert cert['filter_results'][0]['name']==min(names)
        assert b'1 passed; 0 failed;' in actual[('filter-0','stdout')]
        adjusted = re.sub(rb'finished in [0-9.]+s',b'finished in <elapsed>',actual[('filter-0','stdout')])
        assert digest(adjusted)==run['normalized_stdout_sha256'];normalized.append(adjusted)
    assert lists[0]==lists[1] and normalized[0]==normalized[1]
print(json.dumps(summary,sort_keys=True,indent=2))
