"""Reclassify read fds on the pinned fixture, excluding other files whose data mentions it."""
import collections,hashlib,json,re
from pathlib import Path
d=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/build-script-producer-reuse16-v1')
q=d/'runtime-mdtest-v2';fixture='crates/ty_python_semantic/resources/mdtest/typed_dict.md';f=Path.home()/'code/oss/ruff-ohm-whole-native-20261027'/fixture
def h(p):
    with p.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
result={}
root=json.loads((q/'result.json').read_text())
for phase in ['settled','edit','restore']:
    orig=q/('prime.md' if phase=='settled'else phase+'.md');r=root['stages'][phase]['reader'];events=[];ignored=collections.Counter()
    paths=[str(f),str(orig)]
    opens=[];reads=[]
    for a in sorted((q/(phase+'-reader')).glob('file.*')):
        if not a.suffix[1:].isdigit():continue
        for l in a.read_text(errors='replace').splitlines():
            if 'typed_dict.md' not in l and str(orig) not in l:continue
            if l.startswith('read('):
                m=re.match(r'^read\((\d+)<([^>]+)>,.* = ([0-9]+)$',l)
                if m:
                    if m[2] in paths:reads.append({'sha256':hashlib.sha256(l.encode()).hexdigest(),'path':m[2],'ret':int(m[3]),'fd':int(m[1]),'pid':int(a.suffix[1:])})
                    else:ignored[(m[2].split('/')[-1])]+=int(m[3])
            elif l.startswith('openat('):
                m=re.search(r'= (\d+)<([^>]+)>$',l)
                if m and m[2]in paths:opens.append({'sha256':hashlib.sha256(l.encode()).hexdigest(),'path':m[2],'fd':int(m[1]),'pid':int(a.suffix[1:])})
    total=sum(v['ret']for v in reads);sz=orig.stat().st_size
    assert r['fixture_hash']==h(orig),phase
    assert opens and reads and total>=sz and total%sz==0,(phase,paths,opens,reads[:2],total,sz,ignored)
    ev=[{'kind':'open',**v} for v in opens]+[{'kind':'read',**v} for v in reads]
    for v in ev:v['path']=fixture if v['path']==str(f) else ('fixture-overlay/'+orig.name)
    result[phase]={'fixture':h(orig),'bytes':sz,'sum_actual_read_return_bytes':total,'exact_fd_events':ev,'excluded_nonfixture_reads_that_mention_name':sum(ignored.values()),'reader_sha256':h(q/(phase+'-reader')/'result.json')}
print(json.dumps(result))
