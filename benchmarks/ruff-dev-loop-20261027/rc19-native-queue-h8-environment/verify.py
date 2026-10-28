"""Recheck complete native output counts, cached-file evidence and the A/A ELF comparison."""
from pathlib import Path
from collections import Counter
import json,gzip,hashlib
p=Path(__file__).resolve().parent;read=lambda n:json.loads((p/n).read_bytes());gz=lambda n:json.loads(gzip.decompress((p/n).read_bytes()))
expected={'cargo':1,'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50}
owners=read('normalized-ownership.json');keys=read('authentic-reads.json');names=None
for a in ('shipped-18','A','B'):
    v=owners[a];u=v['namespace'];assert u['real']==u['effective']==1000 and all(x==['0','0','4294967295']for x in u['ids'].values())
    assert u['ancestors']['root']['uid']==u['ancestors']['home_parent']['uid']==0 and all(x['trusted']for x in u['ancestors'].values())
    assert [x['units']for x in v['phases']]==[619]*3 and [x['fresh']for x in v['phases']]==[14,563,563]
    n=gz('native-'+a+'.json.gz');looks=n['names'];assert len(set(looks))==50 and (names is None or looks==names);names=looks
    assert n['full']==['ron']and n['counts']==expected and Counter(e['role']for e in n['events'])==expected and all(e['returncode']==0 for e in n['events'])
    k=keys[a]['actual_sampled_match'];assert len(k)==7 and sum(z['kind']=='registry'for z in k.values())==6
    assert all(x['physical_read']['positive_read_bytes']>=x['physical_read']['len']>0 for x in k.values())
    ps=gz('rss-'+a+'.json.gz');assert ps['sum_pss_peak_bytes']==max(i[3]or 0 for i in ps['samples']) and ps['sum_rss_peak_bytes']==max(i[2]for i in ps['samples'])
    assert all(0<=k[3]<=k[2]*2 for k in ps['samples'] if k[3] is not None)
r=gz('repro-elf.json.gz');a=r['A_A'];assert a['excepted_raw']==['.note.gnu.build-id','.strtab','.symtab']and r['packaged_a_a']['byte_identical']
assert [e['outside_gnu_desc']for e in a['load']if e['outside_gnu_desc']]==[[40]]
assert all(not e['outside_gnu_desc_and_section_pointer']for e in a['load'])and r['raw']['first']['program_headers']==r['raw']['repeat']['program_headers']
assert r['raw']['first']['sections']['.text']['body']==r['raw']['repeat']['sections']['.text']['body']
o=read('repro-origin.json');assert o['equal_diagnostic_stripped_raw']==o['actual_packaged_copy_A2'] and o['raw_A1']!=o['raw_A2']
print('Verified three full-map controls, 21 authentic cache samples, all 150 real native links, and A/A runtime code and ELF exceptions.')
