"""Check the H3 source selector, independent native replays, raw ELF bounds and execution status."""
from pathlib import Path
import gzip,hashlib,json,re,struct,sys
p=Path(__file__).resolve().parent;h=lambda v:hashlib.sha256(v).hexdigest();load=lambda n:json.loads((p/n).read_bytes());rd=lambda n:(p/n).read_bytes()
records=load('receipts.json')
for name,r in records.items():
    if "public" in r:
        b=rd(r['public']);assert len(b)==r['bytes'] and h(b)==r['sha']
    else:
        assert name.endswith('observed.elf') and r['bytes']==242528
plan=load('receipts/full/design.json');mapping=load('mapping.json')
a=load('independent/complete/result.json');b=load('independent/minimal/result.json');diff=load('independent/whole-elf-deltas.json')
assert plan['linker']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5' and h(rd('layout.ld'))==plan['script'] and h(rd('observer.s'))==plan['assembly']
member=gzip.decompress(rd('selected-object.bin.gz'));assert len(member)==114296
codes=[42,41,41];dist=[496,0,0]
for t,want,ds in zip(('original','edited','restored'),codes,dist):
    mu=mapping[t];roi='receipts/full/'+t+'/';r=load(roi+'result.json');assert h(member)==mu['object'] and mu['index_ordinal']==12 and mu['function_size']==484
    assert r['subject']==mu['full_archive']==a[t]['archive'] and plan['sources'][t]==r['subject']
    assert all(r[k]==plan[k]for k in ('object','linker','script'))
    assert load(roi+'wild.json')['args']==plan['command'] and load(roi+'wild.json')['status']==0
    assert r['exit']==load(roi+'execute.json')['status']==a[t]['code']==b[t]['code']==want
    assert r['distance']==r['bounds']['picked_end']-r['bounds']['picked_start']==a[t]['span']==b[t]['span']==ds
    assert r['name_exists']==(mu['name']==plan['selector'])==(t=='original')
    sample=re.search(rb'\b484 FUNC .*'+re.escape(plan['symbol'].encode())+rb'$',rd(roi+'readelf-symbols.out'),re.M);assert sample
    assert diff[t]['first_host']==r['output'] and diff[t]['second_host']==a[t]['output'] and diff[t]['all_other_bytes_equal']
    assert diff[t]['all_differing_file_offsets'] in ([], [diff[t]['rodata_sh_entsize_offset']])
    mini=gzip.decompress(rd('independent/minimal/'+t+'.elf.gz'));assert h(mini)==b[t]['output']
assert load('receipts/initial/worker-exit.json')['status']==1 and b"True, 496" in rd('receipts/initial/worker-stderr')
if (p/'SHA256SUMS').exists():
    for line in rd('SHA256SUMS').decode().splitlines():
        digest,name=line.split('  ',1);assert h(rd(name))==digest
print('Three complete real Ruff archives on two hosts and three independently assembled single-member controls verified. Exit 42, 41, 41; selected-size 496, 0, 0.')
