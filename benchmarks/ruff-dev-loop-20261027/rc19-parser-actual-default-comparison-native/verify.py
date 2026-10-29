from pathlib import Path
import gzip,hashlib,json
p=Path(__file__).resolve().parent
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def load(f):return json.loads(f.read_bytes())
for l in (p/'SHA256SUMS').read_text().splitlines():
    h,n=l.split('  ',1);assert sha(p/n)==h
x=json.loads(gzip.decompress((p/'native.json.gz').read_bytes()));b=load(p/'binding.json');plan=load(p/'plan.json');assert len(x)==20 and sha(p/'plan.json')==b['plan']
for k,r in x.items():
    role=r['route']['physical_arm'];source='R' if role in ('R','X') else 'F';n=r['counts']
    assert r['route']['affinity']==[24,25,26,27] and r['route']['uid_map']==['0','0','4294967295'] and r['route']['euid']==1000
    assert r['route']['cargo']==b['subjects'][source]['sha256'] and all(v['sha']==b['compiler'] for v in r['rustc']) and all(v['linker_sha256']==plan['wild'] for v in r['native'])
    if 'invalid' in k:assert r['status']==101 and 'E0308' in r['errors'] and not r['native'];continue
    assert r['status']==0 and n['total']==len(r['typed'])==147 and r['products']['fixtures']['listed']==(557 if r['mode']=='P' else 558) and r['products']['generate_inline_tests']['listed']==1
    assert r['caller']['verdict']==('accepted' if r['mode']=='P' else 'rejected: Star import cannot be parenthesized')
    if 'unchanged' in k:assert n['fresh']==147 and not r['rustc'] and not r['native']
    if k.startswith(('01-original','08-independent-edit')):
        assert n['fresh']==0
        for target in ('fixtures','generate_inline_tests'):
            ev,=[v for v in r['rustc'] if v['unit']==target and not v['probe']]
            assert 'emit-rlink' in ev['args'] and any('unused-extern' in a for a in ev['args'])
    if k.startswith('03-edit'):
        assert (n['full'],n['link'],n['wild'],n['fresh'])==((1,2,2,144) if source=='R' else (3,0,2,144))
        assert sorted((v['unit'],v['link']) for v in r['rustc'] if not v['probe'])==[('fixtures',source=='R'),('generate_inline_tests',source=='R'),('ruff_python_parser',False)]
for l,r in [('01-original-R','01-original-F'),('03-edit-R','03-edit-F'),('06-original-restore-R','06-original-restore-F'),('03-edit-R','08-independent-edit-X'),('03-edit-F','08-independent-edit-Y')]:
    for name in ('fixtures','generate_inline_tests'):
        a,other=x[l]['products'][name],x[r]['products'][name]
        assert a['width_neutral']==other['width_neutral'] and a['list_sha']==other['list_sha']
print('20 native observations, 147-unit no-ops, two independently empty edited references, real selected tests, parser behaviors and E0308 checked')
