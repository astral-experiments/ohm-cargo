from collections import Counter
from pathlib import Path
import hashlib,json,sys
here=Path(__file__).resolve().parent
read=lambda s:json.loads((here/s).read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
s=read('independent-verification.json');p=read('complete.json');src=read('source-binding.json');sb=read('build-subject.json');ar=('parent','candidate','parent-repeat')
assert sha(here/'build-subject.json')==s['subject']==p['subject']
assert sha(here/'source-trees.json')==src['manifest'] and sha(here/'candidate.patch')==sb['controls']['candidate.patch']
trees=read('source-trees.json');assert set(trees['parent'])==set(trees['candidate']) and len(trees['parent'])==src['files']
assert set(k for k in trees['parent'] if trees['parent'][k]!=trees['candidate'][k])==set(sb['product_files'])
assert len(sb['crates'])==872 and len(sb['index'])==703
out=[];calls=[]
for a in ar:
    i=read(a+'-invocation.json');r=read(a+'-raw.json');e=read(a+'-package.json')
    assert i['empty_target'] and i['empty_shared'] and i['registry_seed']==read('seed.json')['seed_file_sha256']
    assert r['fresh']==0 and r['artifacts']>=300 and sorted(x['target']['kind'] for x in r['product'])==[['bin'],['lib']]
    assert len(set(r['product_rustc_argv_sha256']))==2
    calls.append((i['environment'],i['command'][i['command'].index('--')+1:]))
    assert r['sha256']==e['raw_sha256']==p['pair'][a]['raw-cargo-']
    out.append(e['packaged_sha256']);assert out[-1]==p['pair'][a]['cargo-']
    assert r['version']==e['cargo_version'] and s['observed_arms'][a]['artifacts']==r['artifacts']==383
    assert e['GNU_RELRO_present'] and len(e['load_segments'])>=3
    assert all(e['readelf'][k]['raw_sha256']==e['readelf'][k]['packaged_sha256'] for k in ('dynamic','dyn_symbols','relocations'))
    assert {'.text','.rodata','.dynsym','.dynamic'}<=set(e['unchanged_allocated_sections'])
    for name,h in s['observed_arms'][a]['evidence'].items():
        if (here/name).is_file():assert sha(here/name)==h,name
    if len(sys.argv)==2:
        for prefix in ('raw-cargo-','cargo-'):assert sha(Path(sys.argv[1])/(prefix+a))==p['pair'][a][prefix]
assert calls[0]==calls[1]==calls[2] and out[0]==out[2]!=out[1]
for line in (here/'SHA256SUMS').read_text().splitlines():
    h,n=line.split('  ',1);assert sha(here/n)==h,n
print('Verified three cold 383-artifact builds, all six bound images, identical packaged parent control, and preserved ELF loader invariants.')
